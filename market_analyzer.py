# market_analyzer.py

import logging
import asyncio
from typing import Dict, List, Any
from datetime import datetime

# Import consolidated models
from models import MarketData, TradeDirection, OHLCV # Added OHLCV import

# Import the facade client
from topstep_client_facade import TopstepClientFacade

logger = logging.getLogger(__name__)

class MarketAnalyzer:
    """
    Analyzes real-time market trends, volatility, and can serve as a base
    for sentiment analysis integration.
    """

    def __init__(self, api_client: TopstepClientFacade): # Use TopstepClientFacade
        self.api_client = api_client
        logger.info("MarketAnalyzer initialized.")

    async def analyze_market_trends(self, candles: List[OHLCV]) -> Dict[str, Any]: # Changed to accept OHLCV list
        """
        Identify trend direction based on OHLCV price movements.
        Expects a list of OHLCV objects, ordered from oldest to newest.
        """
        if len(candles) < 5: # Need at least 5 candles for a simple trend analysis
            logger.debug("MarketAnalyzer: Not enough candle data to analyze trends. Needs at least 5 candles.")
            return {"trend_direction": TradeDirection.NEUTRAL, "trend_confidence": 0}

        # Simple moving average based trend detection (you can replace with more complex logic)
        # Use close prices for SMA
        close_prices = [c.close for c in candles]
        
        # Calculate a short-term and long-term SMA
        if len(close_prices) < 5: # Ensure enough data for 5-period SMA
            logger.debug("MarketAnalyzer: Not enough data for SMA trend analysis.")
            return {"trend_direction": TradeDirection.NEUTRAL, "trend_confidence": 0}

        short_sma = sum(close_prices[-5:]) / 5 # Last 5 candles
        long_sma = sum(close_prices[-min(len(close_prices), 10):]) / min(len(close_prices), 10) # Last 10 candles or available

        trend_direction = TradeDirection.NEUTRAL
        trend_confidence = 0

        if short_sma > long_sma and close_prices[-1] > short_sma:
            trend_direction = TradeDirection.LONG # Bullish
            trend_confidence = min(100, int(50 + (short_sma - long_sma) / long_sma * 1000)) # Simple confidence score
        elif short_sma < long_sma and close_prices[-1] < short_sma:
            trend_direction = TradeDirection.SHORT # Bearish
            trend_confidence = min(100, int(50 + (long_sma - short_sma) / long_sma * 1000)) # Simple confidence score
        else:
            trend_direction = TradeDirection.NEUTRAL
            trend_confidence = 50 # Base confidence for neutral

        logger.debug(f"MarketAnalyzer: Market Trend: {trend_direction.value} with {trend_confidence}% confidence.")
        return {"trend_direction": trend_direction.value, "trend_confidence": trend_confidence} # Return value as string for compatibility


    async def evaluate_sentiment_analysis(self, asset_name: str) -> Dict[str, Any]:
        """
        Placeholder for performing sentiment analysis using external data (news, social media).
        This would integrate with Finnhub (already in MarketContext) or other APIs.
        """
        # MarketContext already fetches news. This method could aggregate sentiment from there.
        # For now, it remains a dummy.
        logger.warning(f"MarketAnalyzer: evaluate_sentiment_analysis for {asset_name} is a placeholder. Returning dummy score.")
        sentiment_score = 0.0 # Placeholder
        if datetime.now().minute % 5 == 0: # Dummy dynamic sentiment
            sentiment_score = 0.6
        elif datetime.now().minute % 7 == 0:
            sentiment_score = -0.7
        return {"score": sentiment_score, "sources": []}

    async def detect_volatility_shifts(self, candles: List[OHLCV]) -> Dict[str, Any]: # Changed to accept OHLCV list
        """
        Monitor sudden increases in market volatility based on candle data.
        Calculates Historical Volatility using a simple standard deviation of returns.
        """
        if len(candles) < 20: # Need enough candles for a meaningful volatility calculation
            logger.debug("MarketAnalyzer: Not enough candle data to detect volatility shifts. Needs at least 20 candles.")
            return {"volatility": 0.0}

        # Calculate daily returns (or per-candle returns)
        returns = []
        for i in range(1, len(candles)):
            if candles[i-1].close and candles[i-1].close != 0:
                returns.append((candles[i].close - candles[i-1].close) / candles[i-1].close)
        
        if len(returns) < 10: # Need at least 10 returns for std dev
            return {"volatility": 0.0}

        volatility = float(np.std(returns) * np.sqrt(252)) # Annualized volatility for daily data (dummy 252 days)
        
        logger.debug(f"MarketAnalyzer: Detected volatility for candles: {volatility:.4f}")
        return {"volatility": volatility}

    async def generate_trade_opportunities(self, contract_id: str, market_data: MarketData): # Added market_data
        """
        Identify potential trade entry and exit points (e.g., mean reversion, breakout).
        This is distinct from the main strategy analysis.
        """
        recent_prices = [c.close for c in market_data.indicators.get('ohlcv_history', []) if c.close is not None]

        if len(recent_prices) < 5:
            logger.warning(f"MarketAnalyzer: Insufficient data for trade opportunity analysis on {contract_id}")
            return TradeDirection.NEUTRAL # Return a neutral signal indication

        avg_price = sum(recent_prices[-5:]) / len(recent_prices[-5:]) # Last 5 candle close prices
        current_price = recent_prices[-1]

        trade_opportunity_direction = TradeDirection.NEUTRAL

        # Simple mean reversion idea: price significantly below/above average
        if current_price < avg_price * 0.995: # 0.5% below average
            trade_opportunity_direction = TradeDirection.BUY
            logger.info(f"MarketAnalyzer: 🚀 Buy Opportunity Detected for {contract_id} at {current_price:.2f} (Below Avg: {avg_price:.2f})")
        elif current_price > avg_price * 1.005: # 0.5% above average
            trade_opportunity_direction = TradeDirection.SELL
            logger.info(f"MarketAnalyzer: ❌ Sell Opportunity Detected for {contract_id} at {current_price:.2f} (Above Avg: {avg_price:.2f})")
        
        return trade_opportunity_direction