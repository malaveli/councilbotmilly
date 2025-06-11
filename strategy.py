import logging
from dataclasses import dataclass
from typing import List, Optional
from collections import deque
from models import TradeSignal, TradeDirection, MarketData
from mentalism.decision_tree import MentalistDecisionTree
from mentalism.signal_model import SignalModel


@dataclass
class StrategyConfig:
    min_confidence: float = 0.5


class TradeStrategy:
    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()
        self.log = logging.getLogger(self.__class__.__name__)

    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        raise NotImplementedError


class ICTStrategy(TradeStrategy):
    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        self.log.debug("ICTStrategy analyzing market data")
        if market_data.volume and market_data.volume > 0:
            return TradeSignal(
                strategy="ICT",
                direction=TradeDirection.BUY,
                confidence=0.6,
                entry_price=market_data.last,
            )
        return None


class DeltaStrategy(TradeStrategy):
    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        self.log.debug("DeltaStrategy analyzing market data")
        if market_data.bid and market_data.ask and market_data.bid > market_data.ask:
            return TradeSignal(
                strategy="Delta",
                direction=TradeDirection.SELL,
                confidence=0.6,
                entry_price=market_data.last,
            )
        return None


class MentalistStrategy(TradeStrategy):
    """Strategy leveraging the Mentalist decision tree."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config)
        self.price_history: deque[float] = deque(maxlen=20)
        self.volume_history: deque[int] = deque(maxlen=20)

    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        self.log.debug("MentalistStrategy analyzing market data")
        self.price_history.append(market_data.last)
        self.volume_history.append(market_data.volume)
        model = SignalModel(market_data, self.price_history, self.volume_history)
        signals = model.generate_signals()

        tree = MentalistDecisionTree(
            bias=signals["bias"],
            liquidity_sweep=signals["liquidity_sweep"],
            delta_confirmation=signals["delta_confirmation"],
            time_window_ok=signals["time_window_ok"],
        )
        result = tree.evaluate()
        if result["valid_setup"]:
            direction = TradeDirection.BUY if result["bias"] == "long" else TradeDirection.SELL
            return TradeSignal(
                strategy="Mentalist",
                direction=direction,
                confidence=result.get("confidence_score", 0.5),
                entry_price=market_data.last,
                reason=result["reason"],
            )
        return None


class StrategyManager:
    def __init__(self, strategies: List[TradeStrategy]) -> None:
        self.strategies = strategies
        self.log = logging.getLogger(self.__class__.__name__)

    async def evaluate(self, market_data: MarketData) -> Optional[TradeSignal]:
        for strat in self.strategies:
            try:
                signal = await strat.analyze(market_data)
                if signal and signal.confidence >= strat.config.min_confidence:
                    self.log.info(
                        "Strategy %s produced signal %s", strat.__class__.__name__, signal.direction
                    )
                    return signal
            except Exception as exc:  # pragma: no cover
                self.log.exception("Strategy error: %s", exc)
        return None
