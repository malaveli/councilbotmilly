# market_state_engine.py

from datetime import datetime, timedelta
from collections import deque
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class MarketStateEngine:
    def __init__(self):
        self.trades = deque(maxlen=5000)
        # Initialize all potential quote fields to None to ensure they are always present
        self.quotes = {
            "bid": None, "ask": None,
            "bidSize": None, "askSize": None,
            "last": None,  # This stores the last known trade price OR lastPrice from quote
            "lastPrice": None,  # This stores the 'lastPrice' specifically from GatewayQuote
            "change": None,
            "changePercent": None,
            "open": None,
            "high": None,
            "low": None,
            "volume": None,
            "lastUpdated": None,
            "timestamp": None
        }
        self.depth = {}
        self.bars = {1: deque(maxlen=200), 5: deque(maxlen=200), 15: deque(maxlen=200)}  # Use deque with maxlen
        self.current_bar = {1: None, 5: None, 15: None}

    def process_trade(self, args: List[Any]):  # Added type hint
        # FIX: Node.js bridge sends the data directly as the payload, not wrapped in an extra list.
        # FlaskSignalEmitter mimics SignalRHandler by passing it as [None, actual_payload].
        # So, args[1] will be the data sent from Node.js, which could be a single object or a list.
        trade_data = args[1]
        if not trade_data:
            logger.warning("MarketStateEngine: Received empty trade data.")
            return

        # TopstepX trade format can be a list of trades, process each one
        if isinstance(trade_data, list):
            for trade in trade_data:
                self._process_single_trade(trade)
        else:
            self._process_single_trade(trade_data)
        logger.debug(f"MarketStateEngine: Processed trade update. Total trades in deque: {len(self.trades)}")


    def _process_single_trade(self, trade: Dict[str, Any]):  # Added type hint
        timestamp = datetime.utcnow()
        price = trade.get("price")
        size = trade.get("size", 1)

        if price is None:
            logger.warning(f"MarketStateEngine: Trade data missing price, cannot process: {trade}")
            return

        self.trades.append({"timestamp": timestamp, "price": price, "size": size})
        # Update last known price from trade data, as this is a confirmed execution price.
        self.quotes["last"] = price
        self._update_bars(timestamp, price, size)

        last_price_display = f"{self.quotes['last']:.2f}" if self.quotes['last'] is not None else "N/A"
        logger.debug(f"MarketStateEngine: Single trade processed: Price={price}, Size={size}. LastPrice updated to {last_price_display}")


    def process_quote(self, args: List[Any]):  # Added type hint
        # FIX: Node.js bridge sends the data directly as the payload, not wrapped in an extra list.
        quote_data = args[1]
        if not quote_data:
            logger.warning("MarketStateEngine: Received empty quote data.")
            return

        # TopstepX quote format can be a list, process the first one for simplicity
        quote = quote_data[0] if isinstance(quote_data, list) else quote_data

        # Update relevant quote fields from the incoming data using .get() for safety
        # Prioritize 'bestBid' and 'bestAsk' for bid/ask.
        self.quotes["bid"] = quote.get("bestBid", self.quotes["bid"])
        self.quotes["ask"] = quote.get("bestAsk", self.quotes["ask"])
        self.quotes["bidSize"] = quote.get("bidSize", self.quotes["bidSize"])  # Ensure bidSize is updated or kept None
        self.quotes["askSize"] = quote.get("askSize", self.quotes["askSize"])  # Ensure askSize is updated or kept None

        # Update 'last' from 'lastPrice' in quote, but only if it's available.
        # Otherwise, retain the 'last' price from the latest trade (if any), or previous quote.
        self.quotes["last"] = quote.get("lastPrice", self.quotes["last"])

        # Update other informational fields from quote if they exist
        self.quotes["change"] = quote.get("change", self.quotes["change"])
        self.quotes["changePercent"] = quote.get("changePercent", self.quotes["changePercent"])
        self.quotes["open"] = quote.get("open", self.quotes["open"])
        self.quotes["high"] = quote.get("high", self.quotes["high"])
        self.quotes["low"] = quote.get("low", self.quotes["low"])
        self.quotes["volume"] = quote.get("volume", self.quotes["volume"])
        self.quotes["lastUpdated"] = quote.get("lastUpdated", self.quotes["lastUpdated"])
        self.quotes["timestamp"] = quote.get("timestamp", self.quotes["timestamp"])

        # FIX: Format numbers for debug logging safely using ternary operator or checking for None
        # This will prevent the "unsupported format string passed to NoneType.__format__" error
        bid_display = f"{self.quotes['bid']:.2f}" if self.quotes['bid'] is not None else "N/A"
        ask_display = f"{self.quotes['ask']:.2f}" if self.quotes['ask'] is not None else "N/A"
        last_display = f"{self.quotes['last']:.2f}" if self.quotes['last'] is not None else "N/A"
        logger.debug(f"MarketStateEngine: Processed quote: Bid={bid_display}, Ask={ask_display}, Last={last_display}")


    def process_depth(self, args: List[Any]):  # Added type hint
        # FIX: Node.js bridge sends the data directly as the payload, not wrapped in an extra list.
        levels = args[1]
        if not levels:
            logger.debug("MarketStateEngine: Received empty depth data.")
            self.depth = {}  # Clear depth if empty
            return

        # Ensure levels is iterable (can be a single dict or list of dicts)
        if not isinstance(levels, list):
            levels = [levels]

        # Filter out invalid levels (e.g., missing position or size)
        self.depth = {lvl.get("position"): lvl for lvl in levels if lvl.get("position") is not None and lvl.get("size") is not None}
        logger.debug(f"MarketStateEngine: Processed depth with {len(self.depth)} levels.")

    def _update_bars(self, timestamp: datetime, price: float, size: int):  # Added type hint
        """Updates OHLCV bars for specified intervals."""
        for interval in [1, 5, 15]:
            rounded_time_for_bar = self._round_time(timestamp, interval)
            bar = self.current_bar[interval]

            # Debugging the bar logic directly
            logger.debug(f"MarketStateEngine: Bar update check for {interval}-min. Current bar start: {bar.get('t') if bar else 'None'}, Trade timestamp rounded: {rounded_time_for_bar}")

            if bar is None or bar["t"] != rounded_time_for_bar:
                # Close the previous bar if it existed and was for a different time period
                if bar:  # Only close if it's a valid old bar
                    self.bars[interval].append(bar)  # Add to historical bars
                    logger.debug(f"MarketStateEngine: Closed {interval}-min bar {bar['t']}. Appended to history. History size: {len(self.bars[interval])}")

                # Start a new bar
                self.current_bar[interval] = {
                    "t": rounded_time_for_bar,
                    "o": price,
                    "h": price,
                    "l": price,
                    "c": price,
                    "v": size,
                }
                logger.debug(f"MarketStateEngine: Opened NEW {interval}-min bar at {rounded_time_for_bar}. O={price:.2f}, V={size}")
            else:
                # Update existing bar
                bar["h"] = max(bar["h"], price)
                bar["l"] = min(bar["l"], price)
                bar["c"] = price  # Update closing price
                bar["v"] += size  # Add volume
                logger.debug(f"MarketStateEngine: Updated EXISTING {interval}-min bar {bar['t']}. H={bar['h']:.2f}, L={bar['l']:.2f}, C={bar['c']:.2f}, V={bar['v']}")

    def _round_time(self, dt: datetime, minutes: int) -> datetime:  # Added type hint
        """Rounds a datetime object down to the nearest multiple of 'minutes'."""
        # Calculate total minutes from midnight for the given datetime
        total_minutes = dt.hour * 60 + dt.minute

        # Determine the start minute of the current interval
        start_minute_of_interval = (total_minutes // minutes) * minutes

        # Construct the new datetime object for the start of the interval
        rounded_dt = dt.replace(
            hour=start_minute_of_interval // 60,
            minute=start_minute_of_interval % 60,
            second=0,
            microsecond=0,
        )
        logger.debug(f"MarketStateEngine: _round_time input: {dt.isoformat()}, interval: {minutes}, output: {rounded_dt.isoformat()}")
        return rounded_dt

    def get_snapshot(self) -> Dict[str, Any]:  # Added type hint
        """Returns a snapshot of the current market state."""
        # This copies the current state for safe external use by GUIConnector
        return {
            "trades": list(self.trades),
            "quotes": self.quotes.copy(),  # quotes dict is copied
            "depth": self.depth.copy(),   # depth dict is copied
            "bars": {k: list(v) for k, v in self.bars.items()},  # deque objects converted to lists
            "current_bar": {k: v.copy() if v else None for k, v in self.current_bar.items()},  # current_bar dicts copied
        }
