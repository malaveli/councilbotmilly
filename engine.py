# engine.py

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable # NEW: Added Callable import
import csv
import os
import uuid # For generating unique IDs

# Import consolidated models
from models import Order, Position, TradeSignal, OrderType, OrderStatus, TradeDirection, TradeRecord


logger = logging.getLogger(__name__)

class ExecutionEngine:
    """
    Manages all trade execution, active order/position tracking,
    and real-time updates from the TopstepX platform via direct API calls.
    Handles both live and simulated execution internally.
    """
    def __init__(self, auth_token_provider: Callable[[], Optional[str]], api_base_url: str,
                 account_manager: Any, diagnostics_log_signal: Any,
                 virtual_sl_ticks: int, virtual_tp_ticks: int): # Pass virtual SL/TP ticks
        
        # Core API client dependencies (extracted from old RealTradeManager)
        self.auth_token_provider = auth_token_provider
        self.api_base_url = api_base_url
        self.account_manager = account_manager # To get account ID and monitor balance

        self.diagnostics_log_signal = diagnostics_log_signal

        self.active_orders: Dict[str, Order] = {} # {orderId: Order_object} - for live orders
        self.live_positions: Dict[str, Position] = {} # {contract_id: Position_object}
        
        # Track simulated trades separately for total PnL display and logging
        self.active_simulated_trade: Optional[Dict[str, Any]] = None
        self.total_simulated_pnl = 0.0
        self._pending_sim_log_updates = [] # Stores completed simulated trades for GUI

        # Configuration for simulated trades
        self.virtual_sl_ticks = virtual_sl_ticks
        self.virtual_tp_ticks = virtual_tp_ticks
        self.tick_size = 0.25 # Assuming ES futures tick size
        self.tick_value = 12.50 # Assuming ES futures tick value ($12.50 per tick)

        # Trade logging
        self.trade_log_file = "trade_log.csv" # Combined log for live and sim
        self._trade_log_headers = [
            "Timestamp", "TradeID", "Symbol", "Direction", "Size",
            "EntryPrice", "ExitPrice", "PnL_USD", "TradeType", "ExitReason",
            "EntryOrderID", "ExitOrderID"
        ]
        self._ensure_trade_log_file()
        
        self._pending_live_log_updates: List[TradeRecord] = [] # Accumulate completed live trades for GUI.
        self._pending_trade_records_for_live_total_pnl: List[TradeRecord] = [] # For tracking total PnL from trades by this bot.


        logger.info("ExecutionEngine initialized for live and simulated trading.")

    def _ensure_trade_log_file(self):
        """Ensures the CSV trade log file exists with headers."""
        if not os.path.exists(self.trade_log_file):
            with open(self.trade_log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self._trade_log_headers)
            logger.info(f"Created new trade log file: {self.trade_log_file}")
        else:
            logger.info(f"Using existing live trade log file: {self.trade_log_file}")

    def _append_to_trade_log_csv(self, trade_record: TradeRecord):
        """Appends a completed trade record to the CSV log file."""
        with open(self.trade_log_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self._trade_log_headers)
            writer.writerow({
                "Timestamp": trade_record.timestamp.isoformat(),
                "TradeID": trade_record.trade_id,
                "Symbol": trade_record.symbol,
                "Direction": trade_record.direction.value,
                "Size": trade_record.size,
                "EntryPrice": trade_record.entry_price,
                "ExitPrice": trade_record.exit_price,
                "PnL_USD": trade_record.pnl,
                "TradeType": trade_record.strategy, # Using strategy as trade_type for log
                "ExitReason": trade_record.exit_reason,
                "EntryOrderID": trade_record.entry_time.isoformat() if trade_record.entry_time else "",
                "ExitOrderID": trade_record.exit_time.isoformat() if trade_record.exit_time else ""
            })
        self.diagnostics_log_signal.emit(f"Engine: Trade logged to CSV: {trade_record.symbol} {trade_record.pnl:.2f}")

    # --- Public Execution Methods (for higher-level managers like StrategyManager) ---
    async def execute_trade(self, trade_signal: TradeSignal, live_mode: bool, contract_size: int):
        """
        Initiates a trade based on a signal, supporting both live and simulated modes.
        This is the method called by GUIConnector or OrderScheduler.
        """
        if live_mode:
            await self._initiate_live_trade(trade_signal, contract_size)
        else:
            self._initiate_simulated_trade(trade_signal, contract_size)

    async def _initiate_live_trade(self, trade_signal: TradeSignal, size: int):
        """
        Initiates a live trade by placing a market order and setting up for SL/TP management.
        This is separate from the `place_order` which is a low-level API call wrapper.
        """
        if self.get_active_trade(live_mode=True):
            logger.warning("Engine: Already has an active live trade. Skipping new execution.")
            self.diagnostics_log_signal.emit("Engine: Live trade already active, new execution skipped.")
            return

        contract_id = trade_signal.contract_id
        # Assuming direction in TradeSignal is TradeDirection.BUY/SELL
        
        self.diagnostics_log_signal.emit(f"Engine: Placing LIVE {trade_signal.direction.value} market order for {size} contracts of {contract_id}...")
        logger.info(f"Engine: Placing LIVE {trade_signal.direction.value} market order for {size} contracts of {contract_id}...")

        order_id = await self.place_order_to_topstep( # Call the low-level API method
            contract_id=contract_id,
            order_type=OrderType.MARKET,
            direction=trade_signal.direction,
            size=size,
            price=None # Market order
        )

        if order_id:
            # Create an Order object for tracking
            order = Order(
                order_id=order_id,
                contract_id=contract_id,
                order_type=OrderType.MARKET,
                direction=trade_signal.direction,
                size=size,
                status=OrderStatus.PENDING,
                signal_data=trade_signal.__dict__ # Store signal data for context
            )
            self.active_orders[order_id] = order # Track active orders
            logger.info(f"Engine: Live market order {order_id} placed. Awaiting fill.")
            self.diagnostics_log_signal.emit(f"Engine: Live Order {order_id} placed. Awaiting fill.")

            # Calculate SL/TP prices from signal's ticks based on expected entry price
            expected_entry_price = trade_signal.entry_price
            if expected_entry_price is None: # Fallback if signal doesn't provide
                snapshot = self.account_manager.get_current_market_snapshot() # Access MarketStateEngine data
                expected_entry_price = snapshot.get("quotes", {}).get("mid_price", snapshot.get("quotes", {}).get("last", 0.0))
                logger.warning(f"Engine: Trade signal missing entry_price. Using live market price {expected_entry_price:.2f} for SL/TP calculation.")

            if expected_entry_price > 0 and trade_signal.stop_loss_ticks is not None and trade_signal.take_profit_ticks is not None:
                direction_multiplier = 1 if trade_signal.direction == TradeDirection.BUY else -1
                stop_loss_price = expected_entry_price - (trade_signal.stop_loss_ticks * self.tick_size * direction_multiplier)
                take_profit_price = expected_entry_price + (trade_signal.take_profit_ticks * self.tick_size * direction_multiplier)
                
                # Create a temporary 'active_live_trade_tracking' structure to track for client-side SL/TP
                self.active_live_trade_tracking = {
                    "contract_id": contract_id,
                    "entry_order_id": order_id, # Entry order ID
                    "direction": trade_signal.direction,
                    "size": size,
                    "entry_price": None, # Will be set on first fill by position update
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
                    "status": "PENDING_ENTRY_FILL",
                    "open_time": datetime.utcnow(),
                    "realized_pnl": 0.0, # Track current realized PnL
                    "strategy": trade_signal.strategy # For logging
                }
                logger.debug(f"Engine: Live trade client-side SL/TP set. SL: {stop_loss_price:.2f}, TP: {take_profit_price:.2f}")
            else:
                logger.error("Engine: Cannot calculate SL/TP for live trade, entry price or ticks are zero/None.")
                self.diagnostics_log_signal.emit("Engine: ERROR: Live SL/TP not set (price/ticks invalid).")

        else:
            logger.error(f"Engine: Failed to place live market order (no order_id returned).")
            self.diagnostics_log_signal.emit(f"Engine: Live Order Failed: No order ID returned.")
            trade_signal.rejection_reason = f"Live order failed: No order ID returned."


    def _initiate_simulated_trade(self, trade_signal: TradeSignal, size: int):
        """
        Initiates a simulated trade.
        """
        if self.get_active_trade(live_mode=False):
            logger.warning("Engine: Already has an active simulated trade. Skipping new execution.")
            return

        trade_id = str(uuid.uuid4())
        
        # The `trade_signal.entry_price` might be None. Use current market price from snapshot.
        entry_price = trade_signal.entry_price
        if entry_price is None:
            snapshot = self.account_manager.get_current_market_snapshot() # Access MarketStateEngine data via account_manager
            entry_price = snapshot.get("quotes", {}).get("mid_price", snapshot.get("quotes", {}).get("last", 0.0))
            if entry_price == 0.0: # Fallback if market data isn't ready
                entry_price = 1.0 # Avoid division by zero, but this is a critical state.
                logger.error("Engine: No valid entry price from snapshot for simulated trade! Using dummy 1.0.")
            logger.warning(f"Engine: Trade signal missing entry_price for simulated trade. Using market price {entry_price:.2f}.")

        direction_multiplier = 1 if trade_signal.direction == TradeDirection.BUY else -1
        stop_price = entry_price - (self.virtual_sl_ticks * self.tick_size * direction_multiplier)
        target_price = entry_price + (self.virtual_tp_ticks * self.tick_size * direction_multiplier)

        self.active_simulated_trade = {
            "id": trade_id,
            "contract_id": trade_signal.contract_id,
            "direction": trade_signal.direction,
            "size": size,
            "entry_price": entry_price,
            "open_time": datetime.utcnow(),
            "status": "OPEN",
            "stop_price": stop_price,
            "target_price": target_price,
            "pnl_value": 0.0, # Unrealized PnL (in USD)
            "closed_pnl": 0.0, # Realized PnL (in USD)
            "exit_price": None,
            "exit_time": None,
            "strategy": trade_signal.strategy # Store strategy name
        }
        logger.info(f"Engine: Entered SIM {trade_signal.direction.value} trade at {entry_price:.2f} with {size} contracts. SL: {stop_price:.2f}, TP: {target_price:.2f}")
        self.diagnostics_log_signal.emit(f"Engine: SIM Trade Entered: {trade_signal.direction.value} {size} @ {entry_price:.2f}")


    # --- Price Update & Client-Side SL/TP Enforcement (Called by GUIConnector) ---
    def update_price(self, current_price: float, live_mode: bool):
        """
        Called by GUIConnector's main loop to update prices for SL/TP enforcement.
        """
        if live_mode:
            self._update_live_trade_price(current_price)
        else:
            self._update_simulated_trade_price(current_price)

    def _update_live_trade_price(self, current_price: float):
        """
        Updates current price for the active live trade and checks client-side SL/TP.
        """
        if not hasattr(self, 'active_live_trade_tracking') or self.active_live_trade_tracking is None or \
           self.active_live_trade_tracking["status"] not in ["OPEN", "PARTIAL_FILL"]:
            return

        trade = self.active_live_trade_tracking
        
        # Ensure entry_price is set, if not, wait for position update
        if trade["entry_price"] is None:
            logger.debug("Engine: Live trade entry price not set yet. Waiting for position update.")
            return

        direction_multiplier = 1 if trade["direction"] == TradeDirection.BUY else -1
        entry_price = trade["entry_price"]
        
        # Update current Position object (if exists) for display (ExecutionEngine.live_positions)
        if trade["contract_id"] in self.live_positions:
            self.live_positions[trade["contract_id"]].current_market_price = current_price
            self.live_positions[trade["contract_id"]].update_unrealized_pnl(current_price, self.tick_size, self.tick_value)


        stop_triggered = False
        take_profit_triggered = False
        exit_reason = None

        if trade["direction"] == TradeDirection.BUY: # Long trade
            if current_price >= trade["take_profit_price"]:
                take_profit_triggered = True
                exit_reason = "TP Hit"
            elif current_price <= trade["stop_loss_price"]:
                stop_triggered = True
                exit_reason = "SL Hit"
        else: # Short trade
            if current_price <= trade["take_profit_price"]:
                take_profit_triggered = True
                exit_reason = "TP Hit"
            elif current_price >= trade["stop_loss_price"]:
                stop_triggered = True
                exit_reason = "SL Hit"

        if stop_triggered or take_profit_triggered:
            self.diagnostics_log_signal.emit(f"Engine: Live trade client-side exit triggered ({exit_reason}).")
            logger.info(f"Engine: Live trade exit triggered ({exit_reason}). Sending market order to close position.")
            
            # Send market order to close position
            close_direction = TradeDirection.SELL if trade["direction"] == TradeDirection.BUY else TradeDirection.BUY
            
            # Use asyncio.create_task to run the closing order in the background
            asyncio.create_task(self._send_exit_order_to_topstep(
                trade["contract_id"], close_direction, trade["size"], exit_reason
            ))
            
            # Mark trade as CLOSING_PENDING to prevent re-triggering and new trades
            trade["status"] = "CLOSING_PENDING"


    def _update_simulated_trade_price(self, current_price: float):
        """
        Updates current price for the active simulated trade and checks for SL/TP hits.
        """
        if not self.active_simulated_trade or self.active_simulated_trade["status"] != "OPEN":
            return

        trade = self.active_simulated_trade
        direction_multiplier = 1 if trade["direction"] == TradeDirection.BUY else -1
        entry_price = trade["entry_price"]
        
        # Calculate current unrealized PnL for display
        unrealized_pnl_points = (current_price - entry_price) * direction_multiplier
        unrealized_pnl_usd = unrealized_pnl_points * self.tick_value / self.tick_size * trade["size"]
        trade["pnl_value"] = unrealized_pnl_usd

        trade_closed = False
        exit_reason = None

        if trade["direction"] == TradeDirection.BUY: # Long trade
            if current_price >= trade["target_price"]:
                trade_closed = True
                exit_reason = "TP Hit"
            elif current_price <= trade["stop_price"]:
                trade_closed = True
                exit_reason = "SL Hit"
        else: # Short trade
            if current_price <= trade["target_price"]:
                trade_closed = True
                exit_reason = "TP Hit"
            elif current_price >= trade["stop_price"]:
                trade_closed = True
                exit_reason = "SL Hit"

        if trade_closed:
            closed_pnl_usd = (current_price - entry_price) * direction_multiplier * self.tick_value / self.tick_size * trade["size"]
            
            trade["closed_pnl"] = closed_pnl_usd
            trade["exit_price"] = current_price # Set exit price to the trigger price
            trade["exit_time"] = datetime.utcnow()
            trade["status"] = "CLOSED"
            trade["exit_reason"] = exit_reason

            self.total_simulated_pnl += closed_pnl_usd
            logger.info(f"Engine: SIM trade {trade['id']} closed. PnL: ${closed_pnl_usd:.2f} ({exit_reason}). Total Sim PnL: ${self.total_simulated_pnl:.2f}")
            self.diagnostics_log_signal.emit(f"Engine: SIM Trade Closed: {trade['direction'].value} {trade['size']} PnL: ${closed_pnl_usd:.2f} ({exit_reason})")
            
            # Prepare TradeRecord for logging
            trade_record = TradeRecord(
                symbol=trade['contract_id'],
                entry_price=trade['entry_price'],
                exit_price=trade['exit_price'],
                size=trade['size'],
                direction=trade['direction'], # Use actual TradeDirection enum
                pnl=trade['closed_pnl'],
                strategy=trade['strategy'],
                exit_reason=trade['exit_reason'],
                entry_time=trade['open_time'],
                exit_time=trade['exit_time']
            )
            self._pending_sim_log_updates.append(trade_record) # Add to pending list for GUI update
            self._append_to_trade_log_csv(trade_record) # Log to CSV
            self.active_simulated_trade = None # Clear active simulated trade


    async def _send_exit_order_to_topstep(self, contract_id: str, direction: TradeDirection, size: int, exit_reason: str):
        """Sends a market order to close a live position."""
        logger.info(f"Engine: Sending market order to close position for {contract_id} (Reason: {exit_reason})...")
        order_id = await self.place_order_to_topstep( # Call the low-level API method
            contract_id=contract_id,
            order_type=OrderType.MARKET,
            direction=direction, # Direction to close (opposite of trade direction)
            size=size,
            price=None # Market order
        )
        
        if order_id:
            logger.info(f"Engine: Close order {order_id} placed for {contract_id}.")
            self.diagnostics_log_signal.emit(f"Engine: Close Order {order_id} placed for {contract_id}.")
            
            # Update the tracking for the current active live trade
            if hasattr(self, 'active_live_trade_tracking') and self.active_live_trade_tracking:
                self.active_live_trade_tracking["exit_order_id"] = order_id
                self.active_live_trade_tracking["exit_reason"] = exit_reason
                self.active_live_trade_tracking["status"] = "CLOSING_ORDER_SENT"
        else:
            logger.error(f"Engine: FAILED to place close order for {contract_id}: No order ID returned.")
            self.diagnostics_log_signal.emit(f"Engine: ERROR: Failed to close {contract_id}: No order ID returned.")
            if hasattr(self, 'active_live_trade_tracking') and self.active_live_trade_tracking:
                self.active_live_trade_tracking["status"] = "EXIT_ORDER_FAILED"


    # --- Low-level API Interaction Methods (to be called by TopstepClientFacade) ---
    # These methods are designed to be wrapped by TopstepClientFacade
    async def place_order_to_topstep(self, contract_id: str, order_type: OrderType, direction: TradeDirection, size: int, price: Optional[float] = None) -> Optional[str]:
        """
        Places an order to TopstepX via REST API.
        This method is exposed for TopstepClientFacade to use.
        Returns order_id on success, None on failure.
        """
        account_id = self.account_manager.get_current_account_id()
        token = self.auth_token_provider()
        if not account_id or not token:
            self.diagnostics_log_signal.emit("Engine API: Cannot place order, missing account ID or token.")
            logger.warning("Engine API: Cannot place order, missing account ID or token.")
            return None

        try:
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            url = f"{self.api_base_url}/api/Order/place"
            
            payload = {
                "accountId": account_id,
                "contractId": contract_id,
                "type": 2 if order_type == OrderType.MARKET else (1 if order_type == OrderType.LIMIT else 0), # Map to TopstepX types
                "side": 0 if direction == TradeDirection.BUY else 1, # 0 = Buy, 1 = Sell
                "size": size
            }
            if price is not None and order_type != OrderType.MARKET:
                payload["price"] = price

            self.diagnostics_log_signal.emit(f"Engine API: Placing order: {payload}")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    data = await response.json()
                    order_id = data.get("orderId")
                    if order_id:
                        logger.info(f"Engine API: Order placed, Order ID: {order_id}")
                    else:
                        logger.warning(f"Engine API: Order placed but no orderId returned: {data}")
                    return order_id

        except aiohttp.ClientResponseError as e:
            response_text = await e.response.text()
            self.diagnostics_log_signal.emit(f"Engine API: Failed to place order - HTTP Error {e.status}: {e.message}. Response: {response_text}")
            logger.error(f"Engine API: Failed to place order - HTTP Error {e.status}: {e.message}. Response: {response_text}")
        except Exception as e:
            self.diagnostics_log_signal.emit(f"Engine API: Error placing order: {e}")
            logger.error(f"Engine API: Error placing order: {e}")
        return None

    async def cancel_order_to_topstep(self, order_id: str) -> bool:
        """Cancels an order on TopstepX via REST API."""
        account_id = self.account_manager.get_current_account_id()
        token = self.auth_token_provider()
        if not account_id or not token:
            self.diagnostics_log_signal.emit("Engine API: Cannot cancel order, missing account ID or token.")
            logger.warning("Engine API: Cannot cancel order, missing account ID or token.")
            return False
        try:
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            url = f"{self.api_base_url}/api/Order/cancel"
            payload = {
                "accountId": account_id,
                "orderId": order_id
            }
            self.diagnostics_log_signal.emit(f"Engine API: Cancelling order: {order_id}")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    logger.info(f"Engine API: Order {order_id} cancelled successfully.")
                    return True
        except aiohttp.ClientResponseError as e:
            response_text = await e.response.text()
            self.diagnostics_log_signal.emit(f"Engine API: Failed to cancel order - HTTP Error {e.status}: {e.message}. Response: {response_text}")
            logger.error(f"Engine API: Failed to cancel order - HTTP Error {e.status}: {e.message}")
        except Exception as e:
            self.diagnostics_log_signal.emit(f"Engine API: Error cancelling order {order_id}: {e}")
            logger.error(f"Engine API: Error cancelling order {order_id}: {e}")
        return False

    async def close_position_to_topstep(self, contract_id: str, size: int) -> bool:
        """
        Closes a specific size of an open position for a contract via REST API.
        This method is exposed for TopstepClientFacade to use.
        """
        account_id = self.account_manager.get_current_account_id()
        token = self.auth_token_provider()
        if not account_id or not token:
            self.diagnostics_log_signal.emit("Engine API: Cannot close position, missing account ID or token.")
            logger.warning("Engine API: Cannot close position, missing account ID or token.")
            return False
        
        # Determine direction needed to close the position
        current_position = self.live_positions.get(contract_id)
        if not current_position or current_position.quantity == 0:
            logger.warning(f"Engine API: No active position for {contract_id} to close.")
            return True # Effectively closed

        # Close with opposite side
        close_direction_enum = TradeDirection.SELL if current_position.direction == TradeDirection.LONG else TradeDirection.BUY
        
        # Use `/api/Position/closeContract` or `partialCloseContract` if available.
        # For simplicity, using `Order/place` as a market order to flatten.
        
        order_id = await self.place_order_to_topstep(contract_id, OrderType.MARKET, close_direction_enum, size)

        if order_id:
            logger.info(f"Engine API: Close order {order_id} placed for {contract_id} size {size}.")
            self.diagnostics_log_signal.emit(f"Engine API: Close order {order_id} placed for {contract_id} size {size}.")
            return True
        else:
            logger.error(f"Engine API: Failed to place close order for {contract_id}.")
            self.diagnostics_log_signal.emit(f"Engine API: Failed to place close order for {contract_id}.")
            return False

    # --- Utility Methods ---
    def get_active_trade(self, live_mode: bool) -> Optional[Dict[str, Any]]:
        """
        Returns the currently active trade for GUI display.
        For live, it combines tracking info with live_positions data.
        For simulated, it returns the active_simulated_trade.
        """
        if live_mode:
            if hasattr(self, 'active_live_trade_tracking') and self.active_live_trade_tracking and \
               self.active_live_trade_tracking["status"] not in ["CLOSING_PENDING", "CLOSING_ORDER_SENT", "EXIT_FILLED_AWAITING_POSITION", "EXIT_FAILED"]: # Ensure it's truly an active state
                contract_id = self.active_live_trade_tracking['contract_id']
                position = self.live_positions.get(contract_id)
                if position and position.quantity != 0:
                    # Return a composite view for the GUI
                    return {
                        "contract_id": contract_id,
                        "direction": position.direction, # Use position's actual direction
                        "entry_price": position.avg_price,
                        "size": abs(position.quantity), # Absolute size
                        "open_time": position.timestamp,
                        "status": position.status,
                        "stop_price": self.active_live_trade_tracking.get("stop_loss_price"),
                        "target_price": self.active_live_trade_tracking.get("take_profit_price"),
                        "pnl_value": position.unrealized_pnl # Unrealized PnL for display
                    }
            return None # No active live trade
        else:
            if self.active_simulated_trade and self.active_simulated_trade["status"] == "OPEN":
                return self.active_simulated_trade
            return None

    def get_total_pnl(self, live_mode: bool) -> float:
        """Returns the accumulated total PnL (live or simulated)."""
        if live_mode:
            return sum(tr.pnl for tr in self._pending_trade_records_for_live_total_pnl)
        else:
            return self.total_simulated_pnl

    def get_trade_log_and_clear(self, live_mode: bool) -> List[Dict[str, Any]]:
        """
        Returns completed trades that are ready to be reported to the GUI and clears internal buffer.
        """
        if live_mode:
            updates = list(self._pending_live_log_updates)
            self._pending_live_log_updates.clear()
            return [tr.__dict__ for tr in updates] # Convert TradeRecord to dict for GUI
        else:
            updates = list(self._pending_sim_log_updates)
            self._pending_sim_log_updates.clear()
            return [tr.__dict__ for tr in updates] # Convert TradeRecord to dict for GUI


    def reset_pnl_and_trades(self, live_mode: bool):
        """Resets accumulated PnL and active trade state for the given mode."""
        if live_mode:
            self.live_positions.clear()
            self.active_orders.clear()
            if hasattr(self, 'active_live_trade_tracking'):
                del self.active_live_trade_tracking # Remove the tracking dict
            self._pending_live_log_updates = []
            self._pending_trade_records_for_live_total_pnl = []
            logger.info("ExecutionEngine: Live PnL and trade state reset.")
            self.diagnostics_log_signal.emit("Engine: Live PnL and trade state reset.")
        else:
            self.total_simulated_pnl = 0.0
            self.active_simulated_trade = None
            self._pending_sim_log_updates = []
            logger.info("ExecutionEngine: Simulated PnL and trade state reset.")
            self.diagnostics_log_signal.emit("Engine: Simulated PnL and trade state reset.")