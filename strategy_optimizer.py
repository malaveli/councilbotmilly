# strategy_optimizer.py

import logging
import asyncio
from typing import Dict, List, Any

# Import consolidated models
from models import StrategyPerformance, TradeSignal

# Import facades/managers needed for optimization
from topstep_client_facade import TopstepClientFacade # For API calls (if needed for historical data)
from performance import PerformanceMonitor # To get performance data
from strategies import StrategyManager # To potentially adjust strategy parameters

logger = logging.getLogger(__name__)

class StrategyOptimizer:
    """
    Optimizes trading strategies based on historical and live performance data.
    It works by interacting with PerformanceMonitor and StrategyManager.
    """

    def __init__(self,
                 api_client: TopstepClientFacade, # For any API calls if needed for optimization
                 performance_monitor: PerformanceMonitor,
                 strategy_manager: StrategyManager,
                 diagnostics_log_signal: Any): # For logging to GUI
        
        self.api_client = api_client
        self.performance_monitor = performance_monitor
        self.strategy_manager = strategy_manager
        self.diagnostics_log_signal = diagnostics_log_signal

        self.optimization_interval_sec = 3600 # Run optimization every hour (example)
        self.last_optimization_time = None
        self.optimization_task: Optional[asyncio.Task] = None

        logger.info("StrategyOptimizer initialized.")

    async def _periodic_optimization_task(self):
        """Periodically runs optimization checks."""
        while True:
            try:
                current_time = datetime.utcnow()
                if self.last_optimization_time is None or \
                   (current_time - self.last_optimization_time).total_seconds() >= self.optimization_interval_sec:
                    
                    self.diagnostics_log_signal.emit("Optimizer: Running periodic strategy optimization.")
                    logger.info("StrategyOptimizer: Running periodic optimization.")
                    await self.track_strategy_performance()
                    # Example: adjust strategies that are underperforming
                    await self.adjust_strategy_parameters_based_on_performance()
                    self.last_optimization_time = current_time
                
            except Exception as e:
                logger.error(f"StrategyOptimizer: Error during periodic optimization: {e}", exc_info=True)
                self.diagnostics_log_signal.emit(f"OPTIMIZER ERROR: {e}")
            
            await asyncio.sleep(self.optimization_interval_sec / 4) # Check more frequently than optimize


    async def start_optimization_loop(self):
        """Starts the periodic optimization task."""
        if self.optimization_task is None or self.optimization_task.done():
            self.optimization_task = asyncio.create_task(self._periodic_optimization_task())
            logger.info("StrategyOptimizer: Started periodic optimization loop.")
        else:
            logger.info("StrategyOptimizer: Optimization loop already running.")

    async def stop_optimization_loop(self):
        """Stops the periodic optimization task."""
        if self.optimization_task:
            self.optimization_task.cancel()
            await self.optimization_task # Await for task to finish canceling
            logger.info("StrategyOptimizer: Stopped periodic optimization loop.")
            self.diagnostics_log_signal.emit("Optimizer: Optimization loop stopped.")


    async def track_strategy_performance(self):
        """
        Retrieves and logs the performance of each strategy from PerformanceMonitor.
        This updates the internal view of strategy performance.
        """
        # PerformanceMonitor already calculates these, we just retrieve them.
        strategy_metrics = self.performance_monitor.get_strategy_metrics()

        if not strategy_metrics:
            logger.info("StrategyOptimizer: No strategy performance data to track yet.")
            self.diagnostics_log_signal.emit("Optimizer: No strategy performance data.")
            return

        self.strategy_performance: Dict[str, StrategyPerformance] = strategy_metrics # Store the metrics
        
        for strategy_name, stats in self.strategy_performance.items():
            log_msg = (f"📊 Optimizer | Strategy {strategy_name}: "
                       f"Trades: {stats.trade_count}, Wins: {stats.win_count}, Losses: {stats.loss_count}, "
                       f"Win Rate: {stats.win_rate:.2f}%, Total PnL: ${stats.total_pnl:.2f}, "
                       f"Sharpe: {stats.sharpe_ratio:.4f}")
            logger.info(log_msg)
            self.diagnostics_log_signal.emit(log_msg)

    async def adjust_strategy_parameters_based_on_performance(self):
        """
        Dynamically fine-tunes strategy parameters based on performance data.
        This is a placeholder for actual optimization logic.
        """
        if not self.strategy_performance:
            logger.debug("StrategyOptimizer: No strategy performance data to adjust.")
            return

        for strategy_name, stats in self.strategy_performance.items():
            # Example adjustment logic:
            if stats.trade_count > 10: # Only adjust if sufficient trade data
                if stats.win_rate < 40 and stats.total_pnl < 0: # Underperforming
                    logger.warning(f"Optimizer: Strategy {strategy_name} is underperforming (Win Rate: {stats.win_rate:.2f}%, PnL: ${stats.total_pnl:.2f}). Considering adjustment.")
                    self.diagnostics_log_signal.emit(f"OPTIMIZER: {strategy_name} underperforming. Adjusting parameters.")
                    
                    # Example: Increase cooldown for a losing strategy to reduce frequency
                    if strategy_name == "ICT":
                        self.strategy_manager.ict_strategy.config.fvg_min_size_ticks *= 1.1 # Make FVG criteria stricter
                        logger.info(f"Optimizer: Adjusted ICT FVG min size to {self.strategy_manager.ict_strategy.config.fvg_min_size_ticks:.2f}")
                    elif strategy_name == "Delta":
                        self.strategy_manager.delta_strategy.config.ratio_threshold *= 1.1 # Make delta ratio stricter
                        logger.info(f"Optimizer: Adjusted Delta ratio threshold to {self.strategy_manager.delta_strategy.config.ratio_threshold:.2f}")

                elif stats.win_rate > 60 and stats.total_pnl > 0: # Outperforming
                    logger.info(f"Optimizer: Strategy {strategy_name} is outperforming (Win Rate: {stats.win_rate:.2f}%, PnL: ${stats.total_pnl:.2f}).")
                    self.diagnostics_log_signal.emit(f"OPTIMIZER: {strategy_name} outperforming. May loosen parameters.")
                    # Example: Slightly reduce cooldown or make criteria less strict
                    # For example, reduce FVG min size or delta threshold carefully
                    if strategy_name == "ICT" and self.strategy_manager.ict_strategy.config.fvg_min_size_ticks > 1.0:
                        self.strategy_manager.ict_strategy.config.fvg_min_size_ticks *= 0.95
                        logger.info(f"Optimizer: Adjusted ICT FVG min size to {self.strategy_manager.ict_strategy.config.fvg_min_size_ticks:.2f}")
                    elif strategy_name == "Delta" and self.strategy_manager.delta_strategy.config.ratio_threshold > 0.1:
                        self.strategy_manager.delta_strategy.config.ratio_threshold *= 0.95
                        logger.info(f"Optimizer: Adjusted Delta ratio threshold to {self.strategy_manager.delta_strategy.config.ratio_threshold:.2f}")
            else:
                logger.debug(f"Optimizer: Not enough trades ({stats.trade_count}) for {strategy_name} to optimize.")

    async def analyze_historical_patterns(self):
        """Placeholder for analyzing historical trade patterns (e.g., from CSV log)."""
        logger.debug("StrategyOptimizer: Analyzing historical patterns (placeholder).")
        # This would typically read from `self.performance_monitor.trade_records`
        # or load from a saved CSV file.
        pass

    async def optimize_strategy_execution(self, trade_signal: TradeSignal):
        """Refine trade execution based on market conditions (e.g., volatility)."""
        # This would interact with `ExecutionEngine` to adjust order parameters.
        # For example, if volatility is high, place a wider limit order or wait for less volatile times.
        if trade_signal.volatility is not None and trade_signal.volatility > 2.5: # Example threshold
            logger.warning(f"Optimizer: High volatility detected for signal {trade_signal.strategy}. May adjust execution.")
            self.diagnostics_log_signal.emit(f"OPTIMIZER: High Volatility for {trade_signal.strategy}.")
            # This logic would then be used by the ExecutionEngine
        pass

    async def log_strategy_adjustments(self, strategy_name: str, old_params: Dict[str, Any], new_params: Dict[str, Any]):
        """Records modifications made to strategies for auditing."""
        logger.info(f"📜 Optimizer Log | Strategy {strategy_name} Adjusted: Old: {old_params}, New: {new_params}")
        self.diagnostics_log_signal.emit(f"OPTIMIZER: {strategy_name} params adjusted.")
