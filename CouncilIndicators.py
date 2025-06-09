# CouncilIndicators.py

import logging
from typing import Dict, List, Tuple, Any
from datetime import datetime
from collections import deque
import numpy as np

# Import models to use OHLCV and CumulativeDeltaData
from models import OHLCV, CumulativeDeltaData, MarketData, TradeDirection

logger = logging.getLogger(__name__)

class SmartVolumeProfile:
    """
    Calculates a TPO (Time Price Opportunity)-based volume profile for a given price range.
    This can help identify high volume nodes (HVN) and low volume nodes (LVN).
    """
    def __init__(self, resolution: float = 0.25):
        """
        Initializes the SmartVolumeProfile.
        :param resolution: The price resolution for each profile level (e.g., 0.25 for ES ticks).
        """
        self.resolution = resolution
        self.profile: Dict[float, float] = {} # {price_level: volume}
        self.total_volume = 0.0

    def update(self, price: float, volume: float):
        """
        Updates the volume profile with a new trade/price point.
        :param price: The price of the trade/tick.
        :param volume: The volume associated with that price.
        """
        # Round price to the nearest resolution level
        price_level = round(price / self.resolution) * self.resolution
        self.profile[price_level] = self.profile.get(price_level, 0.0) + volume
        self.total_volume += volume
        logger.debug(f"VolumeProfile: Updated price {price_level:.2f} with volume {volume}. Total volume: {self.total_volume:.2f}")

    def get_value_areas(self, value_area_percentage: float = 0.70) -> List[Tuple[float, float]]:
        """
        Calculates the Value Area (VA) which typically contains 70% of the total volume.
        Returns a list of (price_level, volume) tuples within the VA, sorted by price level.
        :param value_area_percentage: The percentage of total volume to include in the Value Area.
        """
        if not self.profile or self.total_volume == 0:
            return []

        # Sort levels by price to easily identify contiguous areas if needed
        sorted_levels = sorted(self.profile.items())
        
        # Find the Point of Control (POC) - level with highest volume
        poc_level = max(self.profile, key=self.profile.get)
        
        # Build the value area by adding levels around the POC until target percentage is reached
        value_area_levels = []
        cumulative_volume = 0.0
        
        # Start with POC
        value_area_levels.append((poc_level, self.profile[poc_level]))
        cumulative_volume += self.profile[poc_level]

        # Expand outwards from POC
        levels_to_check = sorted(self.profile.keys()) # Get all unique levels
        poc_index = levels_to_check.index(poc_level)
        
        low_idx = poc_index
        high_idx = poc_index

        while cumulative_volume < self.total_volume * value_area_percentage and (low_idx > 0 or high_idx < len(levels_to_check) - 1):
            can_expand_low = low_idx > 0
            can_expand_high = high_idx < len(levels_to_check) - 1

            if can_expand_low and can_expand_high:
                # Compare next lowest and next highest levels
                next_low_vol = self.profile.get(levels_to_check[low_idx - 1], 0.0)
                next_high_vol = self.profile.get(levels_to_check[high_idx + 1], 0.0)

                if next_low_vol >= next_high_vol:
                    low_idx -= 1
                    level = levels_to_check[low_idx]
                    value_area_levels.append((level, self.profile[level]))
                    cumulative_volume += self.profile[level]
                else:
                    high_idx += 1
                    level = levels_to_check[high_idx]
                    value_area_levels.append((level, self.profile[level]))
                    cumulative_volume += self.profile[level]
            elif can_expand_low:
                low_idx -= 1
                level = levels_to_check[low_idx]
                value_area_levels.append((level, self.profile[level]))
                cumulative_volume += self.profile[level]
            elif can_expand_high:
                high_idx += 1
                level = levels_to_check[high_idx]
                value_area_levels.append((level, self.profile[level]))
                cumulative_volume += self.profile[level]
            else:
                break # No more levels to expand to

        value_area_levels.sort() # Sort by price level
        logger.debug(f"VolumeProfile: Calculated Value Area. POC: {poc_level:.2f}, VA levels: {len(value_area_levels)}")
        return value_area_levels

    def reset(self):
        """Resets the volume profile data."""
        self.profile = {}
        self.total_volume = 0.0
        logger.debug("VolumeProfile: Reset.")


class CumulativeDelta:
    """
    Calculates and tracks cumulative delta, which is (Buy Volume - Sell Volume).
    Can provide insights into buying/selling pressure.
    """
    def __init__(self):
        self.cumulative_bid_volume = 0.0
        self.cumulative_ask_volume = 0.0
        self.cumulative_delta = 0.0
        self.last_update_time: Optional[datetime] = None

    def update(self, trade_price: float, trade_size: float, trade_direction: TradeDirection, timestamp: datetime):
        """
        Updates the cumulative delta with a new trade.
        :param trade_price: The price of the trade.
        :param trade_size: The size of the trade.
        :param trade_direction: The direction of the trade (TradeDirection.BUY or TradeDirection.SELL).
        :param timestamp: The timestamp of the trade.
        """
        if trade_direction == TradeDirection.BUY:
            self.cumulative_bid_volume += trade_size
        elif trade_direction == TradeDirection.SELL:
            self.cumulative_ask_volume += trade_size
        
        self.cumulative_delta = self.cumulative_bid_volume - self.cumulative_ask_volume
        self.last_update_time = timestamp
        logger.debug(f"CumulativeDelta: Updated. Delta: {self.cumulative_delta:.2f}, Bid Vol: {self.cumulative_bid_volume:.2f}, Ask Vol: {self.cumulative_ask_volume:.2f}")

    @property
    def current_data(self) -> CumulativeDeltaData:
        """Returns the current cumulative delta data as a dataclass."""
        total_volume = self.cumulative_bid_volume + self.cumulative_ask_volume
        delta_ratio = self.cumulative_delta / total_volume if total_volume > 0 else 0.0
        return CumulativeDeltaData(
            delta=self.cumulative_delta,
            ratio=delta_ratio,
            price_level_delta={} # This class doesn't track price level delta, but the model has it.
        )

    def reset(self):
        """Resets the cumulative delta values."""
        self.cumulative_bid_volume = 0.0
        self.cumulative_ask_volume = 0.0
        self.cumulative_delta = 0.0
        self.last_update_time = None
        logger.info("CumulativeDelta: Reset.")