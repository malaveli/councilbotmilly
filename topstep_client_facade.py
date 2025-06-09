# topstep_client_facade.py

import logging
from typing import Optional, Dict, List, Any
import asyncio # For async operations if needed by wrapped clients

# Import your existing client components
from auth_handler import AuthHandler
from account_manager import AccountManager
# from real_trade_manager import RealTradeManager # REMOVED: Now use ExecutionEngine for low-level API calls

# Import the new consolidated models
from models import MarketData, Order, Position, TradeDirection, OrderType

logger = logging.getLogger(__name__)

class TopstepClientFacade:
    """
    A facade class that provides a unified, higher-level interface for
    interacting with TopstepX API clients.
    It wraps AuthHandler, AccountManager, and the low-level API calls
    exposed by ExecutionEngine.
    """
    def __init__(self,
                 auth_handler: AuthHandler,
                 account_manager: AccountManager,
                 # real_trade_manager: RealTradeManager, # REMOVED: Replaced by execution_engine for API calls
                 execution_engine: Any): # Pass ExecutionEngine instance
        
        self._auth_handler = auth_handler
        self._account_manager = account_manager
        # self._real_trade_manager = real_trade_manager # REMOVED
        self._execution_engine = execution_engine # Now responsible for actual API order/position calls
        
        logger.info("TopstepClientFacade initialized, wrapping core API handlers.")

    # --- Account & PnL Methods ---
    async def get_account_pnl(self) -> float:
        """Retrieves the current daily PnL from AccountManager."""
        pnl = self._account_manager.get_current_daily_pnl()
        if pnl is None:
            logger.warning("Facade: get_account_pnl returned None. AccountManager might not have fetched PnL yet.")
            return 0.0
        return pnl

    async def get_account_balance(self) -> float:
        """Retrieves the current account equity/balance from AccountManager."""
        equity = self._account_manager.get_current_equity()
        if equity is None:
            logger.warning("Facade: get_account_balance returned None. AccountManager might not have fetched equity yet.")
            return 0.0
        return equity

    async def get_account_id(self) -> Optional[str]:
        """Retrieves the current active account ID."""
        return self._account_manager.get_current_account_id()

    # --- Market Data Methods ---
    async def get_market_data(self, contract_id: str) -> Dict[str, Any]:
        """
        Retrieves the latest market data snapshot.
        This method needs to access the MarketStateEngine's snapshot.
        Assuming MarketStateEngine's snapshot can be retrieved here for analysis.
        Alternatively, MarketAnalyzer might receive snapshots directly.
        """
        # This facade does not directly hold MarketStateEngine.
        # This is a placeholder for where MarketAnalyzer would get its data,
        # or MarketStateEngine needs to be passed into this facade.
        # For now, it's safer for MarketAnalyzer to get data directly from snapshot provided by GUIConnector.
        
        # If MarketAnalyzer needs MarketData, it should probably be passed by GUIConnector.
        # However, if `api_client.get_market_data` is directly called by new modules,
        # it needs to provide actual market data.
        
        # Let's make this method retrieve the last known market snapshot data from AccountManager
        # as a temporary measure, because AccountManager has a link to the MarketStateEngine.
        snapshot = self._account_manager.get_current_market_snapshot() # AccountManager now gets snapshot
        if snapshot:
            quotes = snapshot.get("quotes", {})
            current_bar = snapshot.get("current_bar", {}).get(1, {}) # Get 1-min bar
            # Construct a basic MarketData dict from snapshot
            return {
                "symbol": contract_id,
                "timestamp": quotes.get("timestamp") or datetime.utcnow(),
                "bid": quotes.get("bid"),
                "ask": quotes.get("ask"),
                "last": quotes.get("last"),
                "volume": quotes.get("volume"),
                "open": current_bar.get("o"),
                "high": current_bar.get("h"),
                "low": current_bar.get("l"),
                "close": current_bar.get("c"),
                "order_book": snapshot.get("depth"),
                "indicators": snapshot.get("indicators", {}) # Pass along any calculated indicators
            }
        logger.warning(f"Facade: get_market_data called for {contract_id}, but no snapshot available.")
        return { # Return a minimal dummy if no snapshot
            "symbol": contract_id, "timestamp": datetime.utcnow(),
            "bid": 0.0, "ask": 0.0, "last": 0.0, "volume": 0,
            "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0,
            "order_book": {}, "indicators": {}
        }


    async def get_margin_requirement(self, contract_id: str, size: int = 1) -> float:
        """
        Retrieves the margin requirement for a contract.
        This is a placeholder; requires actual TopstepX API to expose this.
        """
        logger.warning(f"Facade: get_margin_requirement is a placeholder. Returning dummy value for {contract_id}.")
        # Example for ES Futures (adjust based on actual contract)
        if contract_id.startswith("CON.F.US.EP"): # ES Futures
            return size * 5000.0 # Dummy: $5000 per ES contract margin
        return size * 1000.0 # Generic dummy margin

    # --- Order & Position Methods (Delegated to ExecutionEngine) ---
    async def place_order(self, contract_id: str, order_type: OrderType, direction: TradeDirection, size: int, price: Optional[float] = None) -> Optional[str]:
        """
        Places an order by delegating to ExecutionEngine's low-level API call.
        Returns order_id on success, None on failure.
        """
        # ExecutionEngine.place_order_to_topstep directly talks to TopstepX API.
        return await self._execution_engine.place_order_to_topstep(contract_id, order_type, direction, size, price)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an order by delegating to ExecutionEngine's low-level API call."""
        return await self._execution_engine.cancel_order_to_topstep(order_id)

    async def close_position(self, contract_id: str, size: Optional[int] = None) -> bool:
        """
        Closes a specific size of an open position by delegating to ExecutionEngine.
        """
        # If size is None, assume close all
        current_pos_size = 0
        current_position_obj = self._execution_engine.live_positions.get(contract_id)
        if current_position_obj:
            current_pos_size = abs(current_position_obj.quantity) # Get absolute current quantity

        size_to_close = size if size is not None else current_pos_size
        if size_to_close == 0:
            logger.warning(f"Facade: No size specified and no open position for {contract_id} to close.")
            return True # Already closed or nothing to close
        
        return await self._execution_engine.close_position_to_topstep(contract_id, size_to_close)

    async def get_open_positions(self) -> List[Position]:
        """Retrieves currently open positions from ExecutionEngine."""
        # ExecutionEngine.live_positions already tracks Position objects.
        return list(self._execution_engine.live_positions.values())

    # --- Other Methods (Placeholders for deeper integration) ---
    async def get_sentiment_data(self, asset_name: str) -> Dict[str, Any]:
        """Placeholder for retrieving sentiment data."""
        logger.warning("Facade: get_sentiment_data is a placeholder. Returning dummy.")
        return {"score": 0.0, "sources": []}

    async def get_volatility(self, contract_id: str) -> Dict[str, Any]:
        """Placeholder for retrieving volatility data."""
        logger.warning("Facade: get_volatility is a placeholder. Returning dummy.")
        return {"volatility": 1.0}

    async def get_strategy_performance(self) -> List[Dict[str, Any]]:
        """Placeholder for retrieving strategy performance data. PerformanceMonitor should store this."""
        logger.warning("Facade: get_strategy_performance is a placeholder. PerformanceMonitor provides this.")
        # This would usually be retrieved from PerformanceMonitor, not API.
        return []

    async def get_trade_history(self) -> List[Dict[str, Any]]:
        """Placeholder for retrieving trade history. PerformanceMonitor should store this."""
        logger.warning("Facade: get_trade_history is a placeholder. PerformanceMonitor provides this.")
        # This would usually be retrieved from PerformanceMonitor, not API.
        return []

    async def disable_trading(self) -> None:
        """Disables trading (e.g., in GUIConnector or a global flag)."""
        logger.warning("Facade: disable_trading is a placeholder. This needs to trigger GUIConnector's disable_trading_signal.")
        # This would emit a signal to GUIConnector or update a global flag to stop new trades.
        pass