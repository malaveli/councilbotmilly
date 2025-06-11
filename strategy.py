import logging
from dataclasses import dataclass
from typing import List, Optional
from models import TradeSignal, TradeDirection, MarketData
from mentalism.decision_tree import MentalistDecisionTree


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

    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        self.log.debug("MentalistStrategy analyzing market data")
        try:
            bias = "long" if market_data.close >= market_data.open else "short"
        except Exception:  # Fallback if OHLC not provided
            bias = None

        tree = MentalistDecisionTree(
            bias=bias,
            liquidity_sweep=market_data.indicators.get("liquidity_sweep", False),
            delta_confirmation=market_data.indicators.get("delta_confirmation", False),
            time_window_ok=True,
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
