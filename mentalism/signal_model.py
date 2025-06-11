from datetime import datetime
from collections import deque
from statistics import mean
import logging

class SignalModel:
    """Generate Mentalist signals from real market data."""

    def __init__(self, market_data, price_history: deque, volume_history: deque):
        self.market_data = market_data
        self.price_history = price_history
        self.volume_history = volume_history
        self.log = logging.getLogger(self.__class__.__name__)

    def get_bias(self) -> str | None:
        """Determine high timeframe bias using moving averages."""
        if len(self.price_history) < 10:
            self.log.debug("Not enough history for bias calculation")
            return None
        short_sma = mean(list(self.price_history)[-5:])
        long_sma = mean(list(self.price_history)[-10:])
        return "long" if short_sma > long_sma else "short"

    def detect_liquidity_sweep(self) -> bool:
        """Detect sharp moves relative to recent range and volume."""
        if len(self.price_history) < 2:
            return False
        recent_range = max(self.price_history) - min(self.price_history)
        if recent_range == 0:
            return False
        last_move = abs(self.price_history[-1] - self.price_history[-2])
        avg_vol = mean(self.volume_history) if self.volume_history else 0
        return last_move > recent_range * 0.5 and self.market_data.volume > avg_vol * 1.5

    def delta_confirmed(self) -> bool:
        """Confirm order flow imbalance using bid/ask sizes."""
        if self.market_data.bid and self.market_data.ask:
            return self.market_data.bid > self.market_data.ask
        return False

    def valid_time(self) -> bool:
        """Allow trading only during a predefined time window."""
        now = datetime.now()
        return (
            (now.hour == 9 and now.minute >= 30)
            or now.hour == 10
            or (now.hour == 11 and now.minute < 30)
        )

    def generate_signals(self) -> dict:
        """Return all signal components needed for the decision tree."""
        return {
            "bias": self.get_bias(),
            "liquidity_sweep": self.detect_liquidity_sweep(),
            "delta_confirmation": self.delta_confirmed(),
            "time_window_ok": self.valid_time(),
        }
