# strategies.py

import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Deque, Any
from datetime import datetime, time, timedelta
from collections import deque
import numpy as np

# Import new consolidated models
from models import TradeSignal, TradeDirection, MarketData, OHLCV, CumulativeDeltaData

# Import configuration
import config # NEW: Added config import
import config

logger = logging.getLogger(__name__)

# --- Configuration DataClasses for Strategies ---
# These can be tuned in a settings UI later if exposed
@dataclass
class ICTConfig:
    # Kill Zones in EST hours (24-hour format)
    # Example: London Kill Zone (2-5 AM EST), NY Kill Zone (9-12 PM EST)
    kill_zones_est: List[Tuple[int, int]] = field(default_factory=lambda: [(2, 5), (9, 12)])
    fvg_min_size_ticks: float = 2.0  # Minimum Fair Value Gap size in ticks
    liquidity_threshold_contracts: int = 150  # Minimum liquidity at relevant levels
    fvg_min_size_ticks: float = 2.0
    liquidity_threshold_contracts: int = 150

@dataclass
class DeltaConfig:
    lookback_bars: int = 20  # Number of bars for delta analysis
    ratio_threshold: float = 0.3 # Minimum delta ratio for signal generation
    lookback_bars: int = 20
    ratio_threshold: float = 0.3

# --- Base Strategy Class (for common interface) ---
# --- Base Strategy Class ---
class BaseStrategy:
    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        raise NotImplementedError("analyze method must be implemented by subclasses")
        raise NotImplementedError

# --- ICT Strategy Implementation ---
class ICTStrategy(BaseStrategy):
    """Inner Circle Trader (ICT) Strategy Implementation"""
    

    def __init__(self, config: Optional[ICTConfig] = None):
        self.config = config or ICTConfig()
        # EST timezone for kill zone calculations
        self.est_tz = None
        try:
            from zoneinfo import ZoneInfo
You are absolutely correct. My apologies once again for the repeated missing import. This is a clear `NameError` because `strategies.py` needs to import `config` to access `STRATEGY_COOLDOWN_SECONDS`.

---

**Let's fix this immediately.**
            self.est_tz = ZoneInfo("America/New_York")
        except Exception:
            logger.warning(
                "ZoneInfo not found (Python < 3.9). EST kill zones may not be accurate." 
            )

### **1. `strategies.py` (Add `config            self.est_tz = ZoneInfo("America/New_York")
        except ImportError:
            logger.warning("ZoneInfo not found (Python < 3.9). EST kill zones may not be accurate.")
            # Fallback to pytz if needed, or rely on system's default timezone
            # For this context, assuming ZoneInfo is available as per gui_main.py's usage.
        
    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        """Analyze market data using ICT concepts to find a signal."""
        try:
            # Requires market_data to have 'candles' and 'order_book'
            if not market_data.order_book or 'bid' not in market_data.order_book or 'ask' not in market_data.order_book:
                logger.debug("ICTStrategy: Missing order book data for analysis.")
                return None
            
            # Assuming market_data contains candles or they can be derived from it
            # For a real bot, candles would be from MarketStateEngine.bars
            candles = market_data.indicators.get('ohlcv_history', []) # Expect OHLCV history in indicators
            if len(candles) < 3: # Need at least 3 candles for FVG (current, prev, prev_prev)
                 logger.debug("ICTStrategy: Insufficient candle data for FVG detection.")
                 return None

            # 1. Kill Zone Check
            in_kill_zone, current_hour_est = self._check_kill_zone_timing(market_data.timestamp)
            
            # 2. FVG Detection (checks for both bullish and bearish FVGs)
            bullish_fvgs, bearish_fvgs = self._find_fvgs(candles)
            
            # 3. Liquidity Levels Check
            # Assuming liquidity is derived from order book depth in MarketStateEngine.
            # For simplicity, let's assume it's in MarketData.indicators.get('liquidity_level')
            liquidity_level = market_data.indicators.get('liquidity_level', 0)
            
            # Determine overall signal based on ICT confluence
            direction = TradeDirection.NEUTRAL
            confidence = 0.0
            reason = []

            # Example ICT Confluence Logic (simplified)
            # Bullish ICT Setup: In Kill Zone + Bullish FVG + Sufficient Liquidity
            if in_kill_zone and bullish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.BUY
                confidence = 0.90 # High confidence
                reason.append("In Kill Zone")
                reason.append(f"Bullish FVG detected (count: {len(bullish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level} >= {self.config.liquidity_threshold_contracts})")
            # Bearish ICT Setup: In Kill Zone + Bearish FVG + Sufficient Liquidity (could be below price, e.g. for sell stop liquidity)
            elif in_kill_zone and bearish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.SELL
                confidence = 0.90 # High confidence
                reason.append("In Kill Zone")
                reason.append(f"Bearish FVG detected (count: {len` import)**

Replace the entire content of your existing `strategies.py` file with the following. Pay close attention to the import section at the top.

```python
# strategies.py

import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Deque, Any
from datetime import datetime, time, timedelta
from collections import deque
import numpy as np

# Import new consolidated models
from models import TradeSignal, TradeDirection, MarketData, OHLCV, CumulativeDeltaData

# Import configuration (NEW: Added config import)
import config


logger = logging.getLogger(__name__)

# --- Configuration DataClasses for Strategies ---
# These can be tuned in a settings UI later if exposed
@dataclass
class ICTConfig:
    # Kill Zones in EST hours (24-hour format)
    # Example: London Kill Zone (2-5 AM EST), NY Kill Zone (9-12 PM EST)
    kill_zones_est: List[Tuple[int, int]] = field(default_factory=lambda: [(2, 5), (9, 12)])
    fvg_min_size_ticks: float = 2.0  # Minimum Fair Value Gap size in ticks
    liquidity_threshold_contracts: int = 150  # Minimum liquidity at relevant levels

@dataclass
class DeltaConfig:
    lookback_bars: int = 20  # Number of bars for delta analysis
    ratio_threshold: float = 0.3 # Minimum delta ratio for signal generation

# --- Base Strategy Class (for common interface) ---
class BaseStrategy:
    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        raise NotImplementedError("analyze method must be implemented by subclasses")

# --- ICT Strategy Implementation ---
class ICTStrategy(BaseStrategy):
    """Inner Circle Trader (ICT) Strategy Implementation"""
    
    def __init__(self, config: Optional[ICTConfig] = None):
        self.config = config or ICTConfig()
        # EST timezone for kill zone calculations
        self.est_tz = None
        try:
            from zoneinfo import ZoneInfo
            self.est_tz = ZoneInfo("America/New_York")
        except ImportError:
            logger.warning("ZoneInfo not found (Python < 3.9). EST kill zones may not be accurate.")
            # Fallback to pytz if needed, or rely on system's default timezone
            # For this context, assuming ZoneInfo is available as per gui_main.py's usage.
        
    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        """Analyze market data using ICT concepts to find a signal."""
        try:
            # Requires market_data to have 'candles' and 'order_book'
            if not market_data.order_book or 'bid' not in market_data.order_book or 'ask' not in market_data.order_book:
                logger.debug("ICTStrategy: Missing order book data for analysis.")
            candles = market_data.indicators.get('ohlcv_history', [])
            if len(candles) < 3:
                logger.debug("ICTStrategy: Insufficient candle data for FVG detection.")
                return None
            
            # Assuming market_data contains candles or they can be derived from it
            # For a real bot, candles would be from MarketStateEngine.bars
            candles = market_data.indicators.get('ohlcv_history', []) # Expect OHLCV history in indicators
            if len(candles) < 3: # Need at least 3 candles for FVG (current, prev, prev_prev)
                 logger.debug("ICTStrategy: Insufficient candle data for FVG detection.")
                 return None

            # 1. Kill Zone Check
            in_kill_zone, current_hour_est = self._check_kill_zone_timing(market_data.timestamp)
            
            # 2. FVG Detection (checks for both bullish and bearish FVGs)

            in_kill_zone, _ = self._check_kill_zone_timing(market_data.timestamp)
            bullish_fvgs, bearish_fvgs = self._find_fvgs(candles)
            
            # 3. Liquidity Levels Check
            # Assuming liquidity is derived from order book depth in MarketStateEngine.
            # For simplicity, let's assume it's in MarketData.indicators.get('liquidity_level')
            liquidity_level = market_data.indicators.get('liquidity_level', 0)
            
            # Determine overall signal based on ICT confluence

            direction = TradeDirection.NEUTRAL
            confidence = 0.0
            reason = []

            # Example ICT Confluence Logic (simplified)
            # Bullish ICT Setup: In Kill Zone + Bullish FVG + Sufficient Liquidity
            if in_kill_zone and bullish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.BUY
                confidence = 0.90 # High confidence
                confidence = 0.9
                reason.append("In Kill Zone")
                reason.append(f"Bullish FVG detected (count: {len(bullish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level} >= {self.config.liquidity_threshold_contracts})")
            # Bearish ICT Setup: In Kill Zone + Bearish FVG + Sufficient Liquidity (could be below price, e.g. for sell stop liquidity)
                reason.append(
                    f"Sufficient Liquidity ({liquidity_level} >= {self.config.liquidity_threshold_contracts})"
                )
            elif in_kill_zone and bearish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.SELL
                confidence = 0.90 # High confidence
                confidence = 0.9
                reason.append("In Kill Zone")
                reason.append(f"Bearish FVG detected (count: {len(bearish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level} >= {self.config.liquidity_threshold_contracts})")
            
            elif bullish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.BUY
                confidence = 0.75 # Medium confidence without kill zone
                reason.append(f"Bullish FVG detected (count: {len(bullish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level})")
            elif bearish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.SELL
                confidence = 0.75 # Medium confidence without kill zone
                reason.append(f"Bearish FVG detected (count: {len(bearish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level})")
            
            if direction != TradeDirection.NEUTRAL:
                return TradeSignal(
                    strategy='ICT',
                    direction=direction,
                    confidence=confidence,
                    timestamp=market_data.timestamp,
                    contract_id=market_data.symbol,
                    reason=" | ".join(reason)
                reason.append(
                    f"Sufficient Liquidity ({liquidity_level} >= {self.config.liquidity_threshold_contracts})"
                )
            return None # No signal
        
        except Exception as e:
            logger.error(f"ICT analysis failed: {e}", exc_info=True)
            return None

    def _check_kill_zone_timing(self, timestamp_utc: datetime) -> Tuple[bool, Optional[int]]:
        """Check if current time is within any defined kill zone (EST)."""
        if not self.est_tz:
            return False, None # Cannot check without EST timezone
        
        current_time_est = timestamp_utc.astimezone(self.est_tz).time()
        current_hour_est = current_time_est.hour
        
        for start_hour, end_hour in self.config.kill_zones_est:
            # Simple hour-based check. For more precision, check minutes too.
            if start_hour <= current_hour_est < end_hour:
                logger.debug(f"ICTStrategy: In kill zone {start_hour}-{end_hour} EST (current hour: {current_hour_est}).")
                return True, current_hour_est
        
        logger.debug(f"ICTStrategy: Not in any kill zone (current hour: {current_hour_est}).")
        return False, current_hour_est

    def _find_fvgs(self, candles: List[OHLCV]) -> Tuple[List[Dict], List[Dict]]:
        """Fair Value Gap detection (Bullish and Bearish)."""
        bullish_fvgs = []
        bearish_fvgs = []
        
        # Need at least 3 candles to detect an FVG (candle i-1, i, i+1)
        if len(candles) < 3:
            return [], []

        # Iterate from the third to last candle (index 1 is previous, index 0 is previous-previous)
        # to ensure we always have 3 candles for the pattern.
        # It should be (index: i, i+1, i+2) looking at the current candle and two subsequent.
        # Or more commonly, (index: i-2, i-1, i) looking at three most recent.
        
        # Let's use the most common definition: Gap between high/low of (i-2) and (i)
        # where (i-1) doesn't fill the gap.
        
        # Iterating through the provided `candles` list which represents historical OHLCV data.
        # A common FVG is detected by checking current candle ((bearish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level} >= {self.config.liquidity_threshold_contracts})")
            
            elif bullish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.BUY
                confidence = 0.75 # Medium confidence without kill zone
                confidence = 0.75
                reason.append(f"Bullish FVG detected (count: {len(bullish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level})")
            elif bearish_fvgs and liquidity_level >= self.config.liquidity_threshold_contracts:
                direction = TradeDirection.SELL
                confidence = 0.75 # Medium confidence without kill zone
                confidence = 0.75
                reason.append(f"Bearish FVG detected (count: {len(bearish_fvgs)})")
                reason.append(f"Sufficient Liquidity ({liquidity_level})")
            

            if direction != TradeDirection.NEUTRAL:
                return TradeSignal(
                    strategy='ICT',
                    direction=direction,
                    confidence=confidence,
                    timestamp=market_data.timestamp,
                    contract_id=market_data.symbol,
                    reason=" | ".join(reason)
                    reason=" | ".join(reason),
                )
            return None # No signal
        
            return None
        except Exception as e:
            logger.error(f"ICT analysis failed: {e}", exc_info=True)
            return None

    def _check_kill_zone_timing(self, timestamp_utc: datetime) -> Tuple[bool, Optional[int]]:
        """Check if current time is within any defined kill zone (EST)."""
        if not self.est_tz:
            return False, None # Cannot check without EST timezone
        
            return False, None

        current_time_est = timestamp_utc.astimezone(self.est_tz).time()
        current_hour_est = current_time_est.hour
        

        for start_hour, end_hour in self.config.kill_zones_est:
            # Simple hour-based check. For more precision, check minutes too.
            if start_hour <= current_hour_est < end_hour:
                logger.debug(f"ICTStrategy: In kill zone {start_hour}-{end_hour} EST (current hour: {current_hour_est}).")
                logger.debug(
                    f"ICTStrategy: In kill zone {start_hour}-{end_hour} EST (current hour: {current_hour_est})."
                )
                return True, current_hour_est
        
        logger.debug(f"ICTStrategy: Not in any kill zone (current hour: {current_hour_est}).")
        logger.debug(
            f"ICTStrategy: Not in any kill zone (current hour: {current_hour_est})."
        )
        return False, current_hour_est

    def _find_fvgs(self, candles: List[OHLCV]) -> Tuple[List[Dict], List[Dict]]:
        """Fair Value Gap detection (Bullish and Bearish)."""
        bullish_fvgs = []
        bearish_fvgs = []
        
        # Need at least 3 candles to detect an FVG (candle i-1, i, i+1)
        if len(candles) < 3:
            return [], []

        # Iterate from the third to last candle (index 1 is previous, index 0 is previous-previous)
        # to ensure we always have 3 candles for the pattern.
        # It should be (index: i, i+1, i+2) looking at the current candle and two subsequent.
        # Or more commonly, (index: i-2, i-1, i) looking at three most recent.
        
        # Let's use the most common definition: Gap between high/low of (i-2) and (i)
        # where (i-1) doesn't fill the gap.
        
        # Iterating through the provided `candles` list which represents historical OHLCV data.
        # A common FVG is detected by checking current candle (idx), previous candle (idx-1), and next candle (idx+1).
        # We need to consider the last available candle and its predecessors for current FVG.
        
        # Check for FVG using the last 3 candles: candles[-3], candles[-2], candles[-1]
        if len(candles) >= 3:
            c0, c1, c2 = candles[-3], candles[-2], candles[-1] # c0=oldest, c2=most recent

            # Bullish FVG: low of c2 > high of c0
            if c2.low > c0.high and (c1.open is not None and c1.close is not None): # c1 doesn't fill the gap
        if len(candles) >= 3:
            c0, c1, c2 = candles[-3], candles[-2], candles[-1]
            if c2.low > c0.high:
                fvg_size = c2.low - c0.high
                if fvg_size >= self.config.fvg_min_size_ticks * 0.25: # Convert ticks to price points (ES is 0.25 points per tick)
                    bullish_fvgs.append({
                        'time': c2.timestamp,
                        'range': (c0.high, c2.low),
                        'size': fvg_size
                    })
                    logger.debug(f"ICTStrategy: Bullish FVG detected at {c2.timestamp}: {c0.high:.2f}-{c2.low:.2f}")

            # Bearish FVG: high of c2 < low of c0
            elif c2.high < c0.low and (c1.open is not None and c1.close is not None): # c1 doesn't fill the gap
                if fvg_size >= self.config.fvg_min_size_ticks * 0.25:
                    bullish_fvgs.append({'time': c2.timestamp, 'range': (c0.high, c2.low), 'size': fvg_size})
            elif c2.high < c0.low:
                fvg_size = c0.low - c2.high
                if fvg_size >= self.config.fvg_min_size_ticks * 0.25: # Convert ticks to price points
                    bearish_fvgs.append({
                        'time': c2.timestamp,
                        'range': (c2.high, c0.low),
                        'size': fvg_size
                    })
                    logger.debug(f"ICTStrategy: Bearish FVG detected at {c2.timestamp}: {c2.high:.2f}-{c0.low:.2f}")

                if fvg_size >= self.config.fvg_min_size_ticks * 0.25:
                    bearish_fvgs.append({'time': c2.timestamp, 'range': (c2.high, c0.low), 'size': fvg_size})
        return bullish_fvgs, bearish_fvgs


# --- Delta Strategy Implementation ---
class DeltaStrategy(BaseStrategy):
    """Delta/Volume Analysis Strategy Implementation"""
    

    def __init__(self, config: Optional[DeltaConfig] = None):
        self.config = config or DeltaConfig()
        self.delta_history: Deque[float] = deque(maxlen=self.config.lookback_bars)
        

    async def analyze(self, market_data: MarketData) -> Optional[TradeSignal]:
        """
        Analyze market data using cumulative delta with volume profiling to find a signal.
        Requires market_data.indicators to contain 'cumulative_delta_data'.
        """
        cumulative_delta_data: Optional[CumulativeDeltaData] = market_data.indicators.get('cumulative_delta_data')
        
        if not cumulative_delta_data or cumulative_delta_data.ratio is None:
            logger.debug("DeltaStrategy: Missing cumulative delta data for analysis.")
            return None
            

        current_delta_ratio = cumulative_delta_data.ratio
        self.delta_history.append(current_delta_ratio)
        

        if len(self.delta_history) < self.config.lookback_bars:
            logger.debug("DeltaStrategy: Insufficient delta history for lookback analysis.")
            return None
            
        # Calculate a simple average or weighted average of historical delta ratios
        # For this example, let's just use the current delta ratio against threshold
        

        direction = TradeDirection.NEUTRAL
        confidence = 0.0
        reason = []

        # Example Delta Confluence Logic (simplified)
        if current_delta_ratio > self.config.ratio_threshold:
            direction = TradeDirection.BUY
            confidence = min(0.6 + (current_delta_ratio - self.config.ratio_threshold) * 0.5, 0.95) # Scale confidence
            confidence = min(0.6 + (current_delta_ratio - self.config.ratio_threshold) * 0.5, 0.95)
            reason.append(f"Strong Positive Delta ({current_delta_ratio:.2f} > {self.config.ratio_threshold})")
        elif current_delta_ratio < -self.config.ratio_threshold:
            direction = TradeDirection.SELL
            confidence = min(0.6 + (abs(current_delta_ratio) - self.config.ratio_threshold) * 0.5, 0.95) # Scale confidence
            confidence = min(0.6 + (abs(current_delta_ratio) - self.config.ratio_threshold) * 0.5, 0.95)
            reason.append(f"Strong Negative Delta ({current_delta_ratio:.2f} < {-self.config.ratio_threshold})")
        

        if direction != TradeDirection.NEUTRAL:
            return TradeSignal(
                strategy='Delta',
                direction=direction,
                confidence=confidence,
                timestamp=market_data.timestamp,
                contract_id=market_data.symbol,
                reason=" | ".join(reason)
                reason=" | ".join(reason),
            )
        return None # No signal
        return None

    def reset(self):
        """Reset strategy history (e.g., at start of new trading day)."""
        self.delta_history.clear()
        logger.info("DeltaStrategy: History reset.")


# --- Dynamic Strategy Selection Manager ---
class StrategyManager:
    """
    Manages dynamic strategy selection and signal generation based on market conditions.
    This will replace the previous StrategyEngine.
    """
    
    def __init__(self, api_client: Any): # api_client here refers to TopstepClientFacade
        self.api_client = api_client # Used by MarketAnalyzer if it were fetching data
    """Manages dynamic strategy selection and signal generation."""

    def __init__(self, api_client: Any):
        self.api_client = api_client
        self.ict_strategy = ICTStrategy()
        self.delta_strategy = DeltaStrategy()
        # MarketAnalyzer is initialized separately in gui_main.py and its methods are called
        # self.market_analyzer = MarketAnalyzer(api_client=api_client) # Use the client facade
        
        # Track last signal time for overall cooldown (from old StrategyEngine)
        self.last_signal_time: Optional[datetime] = None
        self.cooldown_seconds: int = config.STRATEGY_COOLDOWN_SECONDS # From config.py
        
        self.cooldown_seconds: int = config.STRATEGY_COOLDOWN_SECONDS
        logger.info("StrategyManager initialized with ICT and Delta strategies.")

    async def evaluate_signal(self, market_data: MarketData) -> Optional[TradeSignal]:
        """
        Evaluates market data and dynamically selects a strategy to generate a trade signal.
        This method will be called periodically by GUIConnector.
        """
        # Enforce overall strategy cooldown
        current_time = datetime.utcnow()
        if self.last_signal_time and (current_time - self.last_signal_time).total_seconds() < self.cooldown_seconds:
            logger.debug(f"StrategyManager: In overall cooldown period. Next signal possible in {self.cooldown_seconds - (current_time - self.last_signal_time).total_seconds():.1f}s")
            logger.debug(
                f"StrategyManager: In overall cooldown period. Next signal possible in {self.cooldown_seconds - (current_time - self.last_signal_time).total_seconds():.1f}s"
            )
            return None

        # 1. Enrich MarketData with Indicators (Trend, Volatility, Delta/Volume Profile)
        # This is where market_analyzer and CouncilIndicators come into play.
        # MarketStateEngine should ideally pre-process raw data into `MarketData.indicators`.
        
        # For now, let's call MarketAnalyzer to enrich the data (it's async).
        # This is a bit of a placeholder call; `MarketAnalyzer` needs to be fleshed out
        # to calculate and return these indicators for `MarketData`.
        
        # You'll need to manually ensure `MarketStateEngine` processes `MarketData.indicators`
        # (e.g. `ohlcv_history` for ICT, `cumulative_delta_data` for Delta) from raw data.
        
        # 2. Select Strategy based on market_data indicators (e.g., trend)
        selected_strategy_name = await self._select_strategy_based_on_conditions(market_data)
        logger.debug(f"StrategyManager: Selected {selected_strategy_name} strategy.")

        trade_signal = None
        if selected_strategy_name == 'ICT':
            trade_signal = await self.ict_strategy.analyze(market_data)
        elif selected_strategy_name == 'Delta':
            trade_signal = await self.delta_strategy.analyze(market_data)

        # 3. Validate Trade Signal (common check for confidence)
        if trade_signal and trade_signal.confidence >= config.MIN_CONFIDENCE_THRESHOLD:
            self.last_signal_time = current_time # Update cooldown only on valid signal
            logger.info(f"StrategyManager: Generated {trade_signal.strategy} {trade_signal.direction.value} signal with confidence {trade_signal.confidence:.2f}")
            self.last_signal_time = current_time
            logger.info(
                f"StrategyManager: Generated {trade_signal.strategy} {trade_signal.direction.value} signal with confidence {trade_signal.confidence:.2f}"
            )
            return trade_signal
        

        logger.debug("StrategyManager: No valid signal generated or confidence too low.")
        return None

    async def _select_strategy_based_on_conditions(self, market_data: MarketData) -> str:
        """Dynamically choose ICT or Delta based on market conditions."""
        # For a truly dynamic selection, you need more robust trend analysis from MarketAnalyzer.
        # MarketAnalyzer's analyze_market_trends could return a MarketData with an indicator.
        
        # Assuming market_data.indicators now has 'trend_direction' and 'trend_confidence'
        # These should be populated by MarketAnalyzer running periodically or enriching MarketData.
        
        trend_direction = market_data.indicators.get('trend_direction')
        trend_confidence = market_data.indicators.get('trend_confidence', 0)

        # This is a placeholder for smart dynamic strategy selection.
        # The logic below is from the provided `strategies.py` and may need tuning.
        if trend_direction == "Bullish" and trend_confidence > 65:
            strategy = "ICT"
        elif trend_direction == "Bearish" and trend_confidence > 65:
            strategy = "Delta"
        elif trend_direction == "Neutral" and trend_confidence > 50: # Example for neutral market
            strategy = "Delta" # Or pick another strategy for ranging markets
        elif trend_direction == "Neutral" and trend_confidence > 50:
            strategy = "Delta"
        else:
            # Fallback strategy if trend is unclear or confidence is low
            strategy = "ICT" # Default to ICT for now, or could cycle.

        logger.debug(f"StrategyManager: Selected Strategy: {strategy} based on trend '{trend_direction}' ({trend_confidence}% confidence).")
            strategy = "ICT"
        logger.debug(
            f"StrategyManager: Selected Strategy: {strategy} based on trend '{trend_direction}' ({trend_confidence}% confidence)."
        )
        return strategy

    async def log_trade_decision(self, trade_signal: TradeSignal):
        """Detailed logging of strategy decision-making."""
        logger.info(f"📊 Trade Decision | Strategy: {trade_signal.strategy} | Direction: {trade_signal.direction.value} | Confidence: {trade_signal.confidence:.2f} | Reason: {trade_signal.reason}")
        logger.info(
            f"📊 Trade Decision | Strategy: {trade_signal.strategy} | Direction: {trade_signal.direction.value} | Confidence: {trade_signal.confidence:.2f} | Reason: {trade_signal.reason}"
        )

    async def log_strategy_error(self, error_message: str):
        """Capture and log unexpected strategy errors."""
        logger.error(f"⚠ STRATEGY ERROR: {error_message}")

    def reset_cooldown(self):
        """Resets the strategy cooldown."""
        self.last_signal_time = None
        logger.info("StrategyManager: Cooldown reset.")

# --- Placeholder Market Analyzer (will be replaced by full market_analyzer.py) ---
# This is a temporary minimal version to prevent StrategyManager from crashing.
# The full market_analyzer.py will provide richer trend/volatility data.
# Note: MarketAnalyzer is initialized in gui_main.py, but StrategyManager used it
# as a placeholder. This class definition is now redundant if MarketAnalyzer
# is directly passed and used in StrategyManager.
# For now, it's safer to keep this dummy class definition to ensure
# `StrategyManager`'s `__init__` does not crash if `MarketAnalyzer` isn't fully ready.
# In the current gui_main.py, StrategyManager takes `api_client` (Facade),
# and `MarketAnalyzer` is a separate instance.
# So, StrategyManager should *not* instantiate MarketAnalyzer directly.
# Let's remove the nested `MarketAnalyzer` definition from `strategies.py`
# as the real one is instantiated in `gui_main.py`.
# This class definition is REMOVED below.
# class MarketAnalyzer:
#     def __init__(self, api_client: Any):
#         self.api_client = api_client
#     async def analyze_market_trends(self, contract_id: str):
#         return {"trend_direction": "Neutral", "trend_confidence": 50}
#     async def get_market_sentiment(self, asset_name: str):
#         return {"score": 0.0}
#     async def get_market_volatility(self, contract_id: str):
#         return {"volatility": 1.0}