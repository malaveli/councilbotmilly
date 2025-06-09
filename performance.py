# performance.py

import logging
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd # Ensure pandas is installed: pip install pandas
import numpy as np # For standard deviation (Sharpe calculation)

# Import consolidated models
from models import TradeRecord, StrategyPerformance, TradeDirection

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """
    Tracks and monitors the performance of individual trades and overall strategy.
    Accumulates trade records and generates key performance indicators (KPIs).
    """
    def __init__(self):
        self.trade_records: List[TradeRecord] = [] # Stores all completed TradeRecord objects
        self.equity_curve_data: List[Dict[str, Any]] = [] # Stores {timestamp, value} for equity curve
        
        # Initial equity for the curve (can be set to starting account balance)
        self.initial_equity_value = 0.0 # This will be set by gui_main or updated by account_manager
        self._is_initial_equity_set = False

        logger.info("PerformanceMonitor initialized.")

    def set_initial_equity(self, equity_value: float):
        """Sets the starting equity value for the equity curve."""
        if not self._is_initial_equity_set:
            self.initial_equity_value = equity_value
            self.equity_curve_data.append({
                'timestamp': datetime.utcnow(),
                'value': self.initial_equity_value
            })
            self._is_initial_equity_set = True
            logger.info(f"PerformanceMonitor: Initial equity set to ${self.initial_equity_value:.2f}.")

    def record_trade(self, trade_record: TradeRecord):
        """
        Stores a completed TradeRecord and updates the equity curve.
        This method will be called by the ExecutionEngine when a trade closes.
        """
        if not isinstance(trade_record, TradeRecord):
            raise TypeError("Expected a TradeRecord object.")
            
        self.trade_records.append(trade_record)
        self._update_equity_curve(trade_record.pnl)
        logger.info(f"PerformanceMonitor: Recorded trade {trade_record.trade_id} (PnL: ${trade_record.pnl:.2f}).")
        
    def _update_equity_curve(self, pnl: float):
        """Updates the running equity curve based on the latest trade PnL."""
        if not self._is_initial_equity_set and not self.equity_curve_data:
            # If initial equity wasn't set explicitly, use 0 or first trade PnL
            self.initial_equity_value = 0.0 # Default starting point
            self.equity_curve_data.append({'timestamp': datetime.utcnow(), 'value': self.initial_equity_value})
            self._is_initial_equity_set = True # Ensure it's marked as set

        last_equity = self.equity_curve_data[-1]['value'] if self.equity_curve_data else self.initial_equity_value
        current_equity = last_equity + pnl
        self.equity_curve_data.append({
            'timestamp': datetime.utcnow(),
            'value': current_equity
        })
        logger.debug(f"PerformanceMonitor: Equity updated to ${current_equity:.2f} after trade PnL ${pnl:.2f}.")

    def get_overall_metrics(self) -> Dict[str, Any]:
        """Calculates key performance indicators for all trades."""
        if not self.trade_records:
            return {
                'total_pnl': 0.0, 'trade_count': 0, 'win_rate': 0.0,
                'avg_win': 0.0, 'avg_loss': 0.0, 'sharpe_ratio': 0.0,
                'max_drawdown': 0.0, 'num_wins': 0, 'num_losses': 0
            }
            
        df = pd.DataFrame([tr.__dict__ for tr in self.trade_records])
        
        total_pnl = df['pnl'].sum()
        trade_count = len(df)
        
        wins_df = df[df['pnl'] > 0]
        losses_df = df[df['pnl'] <= 0]
        
        num_wins = len(wins_df)
        num_losses = len(losses_df)

        win_rate = (num_wins / trade_count) * 100 if trade_count > 0 else 0.0
        avg_win = wins_df['pnl'].mean() if num_wins > 0 else 0.0
        avg_loss = losses_df['pnl'].mean() if num_losses > 0 else 0.0

        # Calculate Sharpe Ratio (requires more than one trade for std dev)
        # Using daily returns for Sharpe, for simplicity using per-trade PnL directly here.
        # For true Sharpe, you need a series of returns over time.
        sharpe_ratio = 0.0
        if trade_count > 1 and df['pnl'].std() > 0:
            sharpe_ratio = df['pnl'].mean() / df['pnl'].std() # Simple Sharpe-like ratio per trade

        # Calculate Max Drawdown
        equity_df = pd.DataFrame(self.equity_curve_data)
        if len(equity_df) > 1:
            equity_values = equity_df['value']
            peak = equity_values.expanding(min_periods=1).max()
            drawdown = (equity_values - peak) / peak
            max_drawdown = drawdown.min() * 100 if len(drawdown) > 0 else 0.0
        else:
            max_drawdown = 0.0


        metrics = {
            'total_pnl': total_pnl,
            'trade_count': trade_count,
            'num_wins': num_wins,
            'num_losses': num_losses,
            'win_rate': round(win_rate, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'sharpe_ratio': round(sharpe_ratio, 4),
            'max_drawdown': round(max_drawdown, 2),
            # Add other metrics like Sortino, expectancy if needed
        }
        logger.debug(f"PerformanceMonitor: Overall metrics: {metrics}")
        return metrics

    def get_strategy_metrics(self) -> Dict[str, StrategyPerformance]:
        """
        Calculates and returns performance metrics for each strategy as a dictionary
        of StrategyPerformance objects.
        """
        strategy_stats: Dict[str, StrategyPerformance] = {}
        if not self.trade_records:
            return {}

        df = pd.DataFrame([tr.__dict__ for tr in self.trade_records])
        
        for strategy_name in df['strategy'].unique():
            strategy_df = df[df['strategy'] == strategy_name]
            
            total_pnl = strategy_df['pnl'].sum()
            trade_count = len(strategy_df)
            
            wins_df = strategy_df[strategy_df['pnl'] > 0]
            losses_df = strategy_df[strategy_df['pnl'] <= 0]
            
            num_wins = len(wins_df)
            num_losses = len(losses_df)

            # Recalculate win_rate explicitly in StrategyPerformance constructor
            
            # Simple Sharpe-like ratio for strategy
            sharpe_ratio = 0.0
            if trade_count > 1 and strategy_df['pnl'].std() > 0:
                sharpe_ratio = strategy_df['pnl'].mean() / strategy_df['pnl'].std()
            
            # Max Drawdown for strategy (simpler version based on PnL stream, not equity curve)
            # For accurate drawdown, you'd need per-strategy equity curves.
            # Here, let's just use the main max_drawdown from overall metrics for now, or simplify.
            # Let's approximate max drawdown for the strategy as 0 for simplicity if not a real equity curve.
            max_drawdown = 0.0 # Placeholder for now.

            strategy_stats[strategy_name] = StrategyPerformance(
                strategy_name=strategy_name,
                total_pnl=round(total_pnl, 2),
                trade_count=trade_count,
                win_count=num_wins,
                loss_count=num_losses,
                sharpe_ratio=round(sharpe_ratio, 4),
                max_drawdown=round(max_drawdown, 2), # Placeholder
                sortino_ratio=0.0 # Placeholder
            )
        logger.debug(f"PerformanceMonitor: Strategy metrics: {strategy_stats}")
        return strategy_stats

    def get_equity_curve(self) -> List[Dict[str, Any]]:
        """Returns the raw equity curve data."""
        return self.equity_curve_data

    def reset_performance_data(self):
        """Clears all recorded trade and equity data."""
        self.trade_records.clear()
        self.equity_curve_data.clear()
        self._is_initial_equity_set = False # Reset initial equity flag
        logger.info("PerformanceMonitor: All performance data reset.")