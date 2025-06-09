# models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from enum import Enum

# --- Enums ---
class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit" # Often implies a stop order that becomes a limit order
    TRAILING_STOP = "trailing_stop" # Could be implemented client-side or as platform-specific
    OCO = "oco" # One-Cancels-Other, often handled by platform or client-side logic

class OrderStatus(Enum):
    PENDING = "pending" # Order submitted, not yet acknowledged or filled
    NEW = "new" # Acknowledged by exchange, waiting to be filled
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ERROR = "error" # Client-side error in submission
    UNKNOWN = "unknown" # Default or fallback status

class TradeDirection(Enum):
    BUY = "buy"
    SELL = "sell"
    LONG = "long" # For positions
    SHORT = "short" # For positions
    NEUTRAL = "neutral"

# --- Data Classes ---

@dataclass
class MarketData:
    """Represents a snapshot of market data, including price, volume, and order book."""
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: int
    open: float = 0.0 # From current or last completed bar
    high: float = 0.0 # From current or last completed bar
    low: float = 0.0  # From current or last completed bar
    close: float = 0.0 # From current or last completed bar
    # Order book representation: { 'bid': [(price, size), ...], 'ask': [(price, size), ...] }
    order_book: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    indicators: Dict[str, float] = field(default_factory=dict) # Calculated indicators (e.g., volatility, trend_strength)

    def __post_init__(self):
        # Basic validation
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime object")
        if self.bid is not None and self.ask is not None and (self.bid < 0 or self.ask < 0):
            raise ValueError("Bid/ask prices cannot be negative")
        if self.volume is not None and self.volume < 0:
            raise ValueError("Volume cannot be negative")

    @property
    def mid_price(self) -> float:
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last # Fallback if bid/ask not available

    @property
    def spread(self) -> float:
        if self.bid is not None and self.ask is not None:
            return round(self.ask - self.bid, 4)
        return 0.0 # Default if no bid/ask

    def is_valid_candle(self) -> bool:
        """Checks if OHLC values form a valid candle."""
        return all([
            self.high >= self.low,
            self.open is not None and self.high is not None and self.open <= self.high,
            self.close is not None and self.high is not None and self.close <= self.high,
            self.open is not None and self.low is not None and self.open >= self.low,
            self.close is not None and self.low is not None and self.close >= self.low
        ])

@dataclass
class Order:
    """Represents a trade order."""
    order_id: str
    contract_id: str
    order_type: OrderType
    direction: TradeDirection # BUY/SELL
    size: int
    price: Optional[float] = None # For limit/stop orders
    timestamp: datetime = field(default_factory=datetime.utcnow)
    status: OrderStatus = OrderStatus.PENDING
    client_order_id: Optional[str] = None # Your internal ID for tracking
    filled_price: Optional[float] = None
    filled_size: int = 0
    remaining_size: int = field(init=False) # Automatically set after init
    # Used for retry logic or for attaching strategy signal data
    signal_data: Optional[Dict] = field(default_factory=dict)

    def __post_init__(self):
        self.remaining_size = self.size - self.filled_size
        if self.size <= 0:
            raise ValueError("Order size must be positive")
        if self.order_type != OrderType.MARKET and self.price is None:
            raise ValueError("Price is required for non-market orders")
        if self.order_type == OrderType.MARKET and self.price is not None:
            logger.warning("Price provided for Market order, it will be ignored.")
        
    def is_stale(self, timeout_seconds: int = 60) -> bool:
        """Check if a pending order is stale (e.g., stuck for too long)"""
        return self.status == OrderStatus.PENDING and \
               (datetime.utcnow() - self.timestamp).total_seconds() > timeout_seconds

@dataclass
class Position:
    """Represents an open trading position."""
    position_id: Optional[str] # Could be platform-assigned position ID
    symbol: str # Contract ID
    quantity: int # Positive for long, negative for short
    avg_price: float # Average entry price
    current_market_price: Optional[float] = None # Latest market price for unrealized PnL
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    initial_margin: float = 0.0 # Initial margin held for position
    maintenance_margin: float = 0.0 # Maintenance margin requirement
    leverage: float = 1.0 # Leverage applied
    timestamp: datetime = field(default_factory=datetime.utcnow) # Time position was opened or last updated
    status: str = "open" # "open", "closed", "liquidated"
    stop_loss_price: Optional[float] = None # Price at which stop loss should trigger
    take_profit_price: Optional[float] = None # Price at which take profit should trigger
    # Thresholds for risk management
    stop_loss_threshold: Optional[float] = None # Renamed from original risk_management.py for clarity
    margin_threshold: Optional[float] = None # Renamed from original engine.py for clarity

    def __post_init__(self):
        if self.quantity == 0:
            # A position with 0 quantity is technically closed, but might be
            # passed temporarily for update purposes before final closure.
            self.status = "closed"
        if self.avg_price <= 0:
            # Handle cases where avg_price might not be known yet (e.g., pending fill)
            # raise ValueError("Invalid average price")
            pass # Allow 0 or None for initial state, actual validation later

    @property
    def direction(self) -> TradeDirection:
        return TradeDirection.LONG if self.quantity > 0 else (TradeDirection.SHORT if self.quantity < 0 else TradeDirection.NEUTRAL)

    @property
    def market_value(self) -> float:
        """Calculates current market value of the position (absolute)."""
        if self.current_market_price is None or self.current_market_price <= 0:
            return 0.0
        return abs(self.quantity) * self.current_market_price

    def update_unrealized_pnl(self, current_price: float, tick_size: float = 0.25, tick_value: float = 12.50):
        """Updates unrealized PnL based on current market price."""
        if self.quantity == 0 or current_price is None or self.avg_price is None:
            self.unrealized_pnl = 0.0
            return
        
        # PnL in points per contract
        pnl_points_per_contract = (current_price - self.avg_price) if self.direction == TradeDirection.LONG else \
                                 (self.avg_price - current_price)
        
        # Convert points to USD
        # Assuming ES futures: 1 point = 4 ticks ($50)
        # 1 tick = $12.50
        points_per_dollar = (1 / tick_size) * tick_value
        
        self.unrealized_pnl = pnl_points_per_contract * abs(self.quantity) * points_per_dollar


@dataclass
class TradeSignal:
    """Represents a trading signal generated by a strategy."""
    strategy: str # e.g., 'ICT', 'Delta'
    direction: TradeDirection # 'buy' or 'sell'
    confidence: float # 0.0 to 1.0 (confidence level)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    contract_id: str = "CON.F.US.EP.M25" # Default to ES futures contract
    entry_price: Optional[float] = None # Suggested entry price
    stop_loss_ticks: Optional[int] = None # Suggested SL in ticks
    take_profit_ticks: Optional[int] = None # Suggested TP in ticks
    reason: Optional[str] = None # Explanation for the signal
    # Additional fields from original strategy_optimizer.py
    volatility: Optional[float] = None # Market volatility at time of signal
    liquidity: Optional[float] = None # Market liquidity at time of signal
    # Used for order_scheduler.py
    execution_time: Optional[datetime] = None
    # Used for risk_management.py
    rejection_reason: Optional[str] = None # If a trade was rejected by risk manager


@dataclass
class ScheduledOrder:
    """Represents an order scheduled for future execution by the bot."""
    contract_id: str
    order_type: OrderType
    direction: TradeDirection
    size: int
    execution_time: datetime
    price: Optional[float] = None # For limit orders
    status: str = "scheduled" # "scheduled", "executed", "failed"
    original_trade_signal: Optional[TradeSignal] = None # Link to the signal that generated it

@dataclass
class StrategyPerformance:
    """Tracks key performance indicators for a specific strategy."""
    strategy_name: str
    total_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = field(init=False)
    risk_factor: float = 1.0 # Dynamic risk factor for optimization

    def __post_init__(self):
        self.win_rate = (self.win_count / self.trade_count) * 100 if self.trade_count > 0 else 0.0

@dataclass
class TradeRecord:
    """Comprehensive record of a completed trade."""
    symbol: str
    entry_price: float
    exit_price: float
    size: int
    direction: TradeDirection
    pnl: float
    strategy: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4())) # Unique ID for the trade
    exit_reason: Optional[str] = None # e.g., 'SL', 'TP', 'Manual', 'Vol_Limit'
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None

# For indicators
@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class CumulativeDeltaData:
    delta: float
    ratio: float
    price_level_delta: Dict[float, float] = field(default_factory=dict)