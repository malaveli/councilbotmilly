import logging
from dataclasses import dataclass
from typing import List, Optional
from models import TradeSignal, TradeDirection, MarketData


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
