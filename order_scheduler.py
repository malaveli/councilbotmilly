# order_scheduler.py

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import uuid # For unique order IDs

# Import consolidated models
from models import ScheduledOrder, TradeSignal, OrderType, TradeDirection

# Import the facade client and the execution engine
from topstep_client_facade import TopstepClientFacade
from engine import ExecutionEngine # To execute the trade

logger = logging.getLogger(__name__)

class OrderScheduler:
    """
    Automates trade execution timing and precision.
    It holds orders and releases them to the ExecutionEngine at the scheduled time.
    """

    def __init__(self, api_client: TopstepClientFacade, execution_engine: ExecutionEngine, diagnostics_log_signal: Any):
        self.api_client = api_client
        self.execution_engine = execution_engine # The engine that actually places orders
        self.diagnostics_log_signal = diagnostics_log_signal
        self.scheduled_orders: Dict[str, ScheduledOrder] = {} # {schedule_id: ScheduledOrder_object}
        self.scheduling_tasks: Dict[str, asyncio.Task] = {} # {schedule_id: asyncio.Task}

        self.polling_interval_sec = 0.5 # How often to check for due orders
        self.scheduler_task: Optional[asyncio.Task] = None

        logger.info("OrderScheduler initialized.")

    async def start_scheduler_loop(self):
        """Starts the periodic loop to check for due orders."""
        if self.scheduler_task is None or self.scheduler_task.done():
            self.scheduler_task = asyncio.create_task(self._periodic_check_for_due_orders())
            logger.info("OrderScheduler: Started periodic check for due orders.")
            self.diagnostics_log_signal.emit("Scheduler: Periodic check started.")
        else:
            logger.info("OrderScheduler: Scheduler loop already running.")

    async def stop_scheduler_loop(self):
        """Stops the periodic scheduler loop."""
        if self.scheduler_task:
            self.scheduler_task.cancel()
            await self.scheduler_task # Await for task to finish canceling
            logger.info("OrderScheduler: Stopped periodic check for due orders.")
            self.diagnostics_log_signal.emit("Scheduler: Periodic check stopped.")

    async def _periodic_check_for_due_orders(self):
        """Internal loop to check if any scheduled orders are due for execution."""
        while True:
            try:
                current_time = datetime.utcnow()
                due_orders_to_execute = []
                for schedule_id, scheduled_order in list(self.scheduled_orders.items()): # Iterate on a copy
                    if scheduled_order.execution_time <= current_time:
                        due_orders_to_execute.append(schedule_id)

                for schedule_id in due_orders_to_execute:
                    scheduled_order = self.scheduled_orders.pop(schedule_id)
                    if schedule_id in self.scheduling_tasks:
                        # Cancel its individual scheduling task if it still exists (shouldn't if passed due)
                        task = self.scheduling_tasks.pop(schedule_id)
                        if not task.done(): task.cancel()
                    
                    logger.info(f"OrderScheduler: Scheduled order {scheduled_order.contract_id} is due. Executing now.")
                    self.diagnostics_log_signal.emit(f"Scheduler: Executing due order {scheduled_order.contract_id}.")
                    
                    # Execute the trade via the ExecutionEngine
                    # ExecutionEngine expects TradeSignal and live_mode, contract_size
                    # We need to reconstruct a TradeSignal or pass original if available
                    original_signal = scheduled_order.original_trade_signal
                    if original_signal:
                        # Assuming strategy_optimizer adjusted contract_size, use that, otherwise from scheduled_order
                        # The ExecutionEngine will adjust size dynamically, so we can use scheduled_order.size
                        asyncio.create_task(self.execution_engine.execute_trade(
                            trade_signal=original_signal, # Use the original signal
                            live_mode=True, # Assuming scheduled orders are for live execution
                            contract_size=scheduled_order.size # Use the size from scheduled order
                        ))
                    else:
                        logger.error(f"OrderScheduler: Cannot execute scheduled order {scheduled_order.contract_id}, original TradeSignal missing.")
                        self.diagnostics_log_signal.emit(f"Scheduler ERROR: Signal missing for {scheduled_order.contract_id}.")

            except Exception as e:
                logger.error(f"OrderScheduler: Error in periodic check for due orders: {e}", exc_info=True)
                self.diagnostics_log_signal.emit(f"SCHEDULER ERROR: {e}")
            
            await asyncio.sleep(self.polling_interval_sec)

    async def schedule_trade_execution(self, trade_signal: TradeSignal, size: int, execution_time: Optional[datetime] = None):
        """
        Schedules a trade for future execution or executes immediately if no time specified.
        :param trade_signal: The TradeSignal that generated this order.
        :param size: The determined contract size for the trade.
        :param execution_time: The specific UTC datetime when the trade should be executed.
                               If None, execute immediately.
        """
        schedule_id = str(uuid.uuid4())
        
        # If execution_time is not provided or is in the past, execute immediately
        if execution_time is None or execution_time <= datetime.utcnow():
            logger.info(f"OrderScheduler: Trade for {trade_signal.contract_id} not scheduled, executing immediately.")
            self.diagnostics_log_signal.emit(f"Scheduler: Executing {trade_signal.contract_id} immediately.")
            await self.execution_engine.execute_trade(trade_signal=trade_signal, live_mode=True, contract_size=size) # Assuming live mode
            return

        scheduled_order = ScheduledOrder(
            contract_id=trade_signal.contract_id,
            order_type=OrderType.MARKET, # Assuming scheduled orders are Market orders
            direction=trade_signal.direction,
            size=size,
            execution_time=execution_time,
            original_trade_signal=trade_signal # Store the original signal
        )
        self.scheduled_orders[schedule_id] = scheduled_order
        self.diagnostics_log_signal.emit(f"Scheduler: Trade {trade_signal.contract_id} scheduled for {execution_time} UTC (Size: {size}).")
        logger.info(f"OrderScheduler: Trade for {trade_signal.contract_id} scheduled at {execution_time} UTC with size {size}.")

        # Individual task for precision if needed, but periodic check handles it.
        # This can be used for very specific high-precision timing, but simple loop is fine.
        # self.scheduling_tasks[schedule_id] = asyncio.create_task(self._wait_and_execute(schedule_id, scheduled_order))


    async def _wait_and_execute(self, schedule_id: str, scheduled_order: ScheduledOrder):
        """Individual task to wait for a specific scheduled order's time."""
        wait_seconds = (scheduled_order.execution_time - datetime.utcnow()).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        
        if schedule_id in self.scheduled_orders: # Ensure it hasn't been cancelled/removed
            self.scheduled_orders.pop(schedule_id)
            self.scheduling_tasks.pop(schedule_id)
            logger.info(f"OrderScheduler: Individual task executing scheduled order {scheduled_order.contract_id}.")
            self.diagnostics_log_signal.emit(f"Scheduler: Executing scheduled order {scheduled_order.contract_id}.")
            await self.execution_engine.execute_trade(trade_signal=scheduled_order.original_trade_signal, live_mode=True, contract_size=scheduled_order.size)
        else:
            logger.info(f"OrderScheduler: Scheduled order {schedule_id} was already handled or cancelled.")


    async def cancel_scheduled_trade(self, contract_id: str):
        """Cancels a scheduled trade by its contract ID."""
        scheduled_to_cancel = [sid for sid, order in self.scheduled_orders.items() if order.contract_id == contract_id]
        if scheduled_to_cancel:
            for schedule_id in scheduled_to_cancel:
                self.scheduled_orders.pop(schedule_id, None)
                if schedule_id in self.scheduling_tasks:
                    self.scheduling_tasks[schedule_id].cancel()
                    self.scheduling_tasks.pop(schedule_id, None)
                logger.info(f"OrderScheduler: Cancelled scheduled trade for {contract_id}.")
                self.diagnostics_log_signal.emit(f"Scheduler: Cancelled scheduled trade for {contract_id}.")
        else:
            logger.info(f"OrderScheduler: No scheduled trade found for {contract_id}.")

    async def prevent_over_trading(self, contract_id: str) -> bool:
        """Enforce limits to avoid excessive scheduled trading."""
        scheduled_count = len([order for order in self.scheduled_orders.values() if order.contract_id == contract_id])

        if scheduled_count >= 1: # Example: Only one scheduled trade per contract at a time
            logger.warning(f"OrderScheduler: Too many ({scheduled_count}) scheduled trades for {contract_id}. Execution paused.")
            self.diagnostics_log_signal.emit(f"Scheduler: Too many scheduled for {contract_id}.")
            return False
        return True