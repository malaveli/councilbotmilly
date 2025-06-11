from datetime import datetime
import random

class SignalModel:
    """Simulates input signals for Mentalist logic."""

    def __init__(self, market_data):
        self.market_data = market_data

    def get_bias(self) -> str | None:
        """Determine market bias. Placeholder using random."""
        return "long" if random.random() > 0.5 else "short"

    def detect_liquidity_sweep(self) -> bool:
        """Detect engineered liquidity moves. Placeholder implementation."""
        return random.random() > 0.4

    def delta_confirmed(self) -> bool:
        """Check for delta confirmation. Placeholder implementation."""
        return random.random() > 0.6

    def valid_time(self) -> bool:
        """Only trade during a predefined time window."""
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
