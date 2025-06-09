# account_manager.py

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta, timezone, time # IMPORTANT: Import timezone and time
from typing import Optional, Callable, Dict, Any
from PySide6.QtCore import Signal, QObject
from zoneinfo import ZoneInfo # NEW: Import ZoneInfo for timezones (Python 3.9+)
# If you are using Python < 3.9, you would need to install pytz: pip install pytz
# and change: from pytz import timezone as ZoneInfo

logger = logging.getLogger(__name__)

# AccountManager must inherit from QObject for its Signals to work properly
class AccountManager(QObject):
    # NEW SIGNAL:
    account_id_fetched_signal = Signal(str) # Emitted when accountId is successfully fetched

    """
    Manages TopstepX account data (balance, equity, daily PnL, open positions)
    by polling REST API and processing User Hub updates.
    """
    def __init__(self, auth_token_provider: Callable[[], Optional[str]], api_base_url: str,
                 account_data_signal: Any, diagnostics_log_signal: Any):
        super().__init__() # IMPORTANT: Call QObject's constructor
        self.auth_token_provider = auth_token_provider
        self.api_base_url = api_base_url
        self.account_data_signal = account_data_signal # PySide6 signal for GUI updates
        self.diagnostics_log_signal = diagnostics_log_signal # PySide6 signal for logging

        self.current_account_id: Optional[str] = None
        self.current_equity: Optional[float] = None
        self.current_balance: Optional[float] = None
        self.current_daily_pnl: Optional[float] = None # Will be populated by fetch_daily_pnl
        self.active_live_positions: Dict[str, Any] = {} # {contract_id: {side, size, avg_price}}
        self.polling_interval_sec = 60 # Poll account/PnL every 60 seconds

        self.polling_task: Optional[asyncio.Task] = None

        # Define ET timezone for TopstepX trading day calculation
        self.ET = ZoneInfo("America/New_York")


    async def fetch_initial_account_data(self):
        """Fetches account ID and initial balance/equity from REST API."""
        token = self.auth_token_provider()
        if not token:
            self.diagnostics_log_signal.emit("AccountManager: No auth token available to fetch account data.")
            logger.warning("AccountManager: No auth token available to fetch account data.")
            return False

        try:
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            url = f"{self.api_base_url}/api/Account/search"
            payload = {"onlyActiveAccounts": True} # Search for active accounts

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    accounts = data.get("accounts", []) # Assuming 'accounts' key
                    if accounts:
                        # Assuming we use the first active account found
                        account_info = accounts[0]
                        
                        # FIX: Changed to prioritize "id" as per debug_account_id.py output
                        self.current_account_id = str(account_info.get("id", account_info.get("accountId"))) # Use "id" if present, else "accountId"
                        
                        # Initial balance/equity might not be in Account/search,
                        # rely on GatewayUserAccount updates for these.
                        # Setting to None initially, will be filled by process_account_update
                        self.current_equity = None
                        self.current_balance = None
                        
                        if self.current_account_id and self.current_account_id != "None": # Ensure it's not the string "None"
                            self.diagnostics_log_signal.emit(f"AccountManager: Initialized for Account ID: {self.current_account_id}")
                            logger.info(f"AccountManager: Initialized for Account ID: {self.current_account_id}")
                            # Emit the new signal here AFTER current_account_id is set
                            self.account_id_fetched_signal.emit(self.current_account_id)

                            # Start periodic polling after initial data is fetched and account ID is known
                            if self.polling_task is None or self.polling_task.done():
                                 self.polling_task = asyncio.create_task(self._periodic_data_polling())
                                 logger.info("AccountManager: Started periodic data polling.")
                            return True
                        else:
                            self.diagnostics_log_signal.emit("AccountManager: Active account found but 'id'/'accountId' key is missing or None.")
                            logger.warning("AccountManager: Active account found but 'id'/'accountId' key is missing or None.")
                            return False
                    else:
                        self.diagnostics_log_signal.emit("AccountManager: No active accounts found.")
                        logger.warning("AccountManager: No active accounts found.")
                        return False

        except aiohttp.ClientResponseError as e:
            # Added more context to error messages for debugging HTTP issues
            response_text = await e.response.text()
            self.diagnostics_log_signal.emit(f"AccountManager: Failed to fetch accounts - HTTP Error {e.status}: {e.message}. Response: {response_text}")
            logger.error(f"AccountManager: Failed to fetch accounts - HTTP Error {e.status}: {e.message}. Response: {response_text}")
        except Exception as e:
            self.diagnostics_log_signal.emit(f"AccountManager: Error fetching initial account data: {e}")
            logger.error(f"AccountManager: Error fetching initial account data: {e}")
        return False

    async def _periodic_data_polling(self):
        """Periodically fetches daily PnL and updates UI."""
        while True:
            await self.fetch_daily_pnl()
            # Emit full data, including current PnL (RiskEngine will check this)
            self.account_data_signal.emit({
                "equity": self.current_equity,
                "daily_pnl": self.current_daily_pnl,
                "account_id": self.current_account_id
            })
            await asyncio.sleep(self.polling_interval_sec)

    async def fetch_daily_pnl(self):
        """Fetches realized daily PnL from the Trade/search REST API,
        adjusted for TopstepX's trading day (6 PM ET to 4:10 PM ET next day),
        including weekly start/end."""
        if not self.current_account_id:
            logger.warning("AccountManager: Cannot fetch daily PnL, account ID not set.")
            return

        token = self.auth_token_provider()
        if not token:
            logger.warning("AccountManager: No auth token available to fetch daily PnL.")
            return

        try:
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            url = f"{self.api_base_url}/api/Trade/search"
            
            # --- Calculate start and end of TopstepX trading day in UTC ---
            now_et = datetime.now(self.ET) # Get current time in ET
            
            # Define daily trading session boundaries in ET
            topstep_session_start_time_et = time(18, 0) # 6 PM ET
            topstep_session_end_time_et = time(16, 10) # 4:10 PM ET
            
            # Determine the calendar date for the START of the *current* TopstepX trading day
            # If current time is after 6 PM ET, the session started today.
            # If current time is before 6 PM ET, the session started yesterday.
            if now_et.time() >= topstep_session_start_time_et:
                start_date_of_session_et = now_et.date()
            else:
                start_date_of_session_et = now_et.date() - timedelta(days=1)
            
            # Construct the full datetime object for the session start in ET
            start_of_topstep_session_et = datetime.combine(start_date_of_session_et, topstep_session_start_time_et, tzinfo=self.ET)
            
            # The end of the trading session is on the *next* calendar day relative to its start date
            end_of_topstep_session_et = datetime.combine(start_date_of_session_et + timedelta(days=1), topstep_session_end_time_et, tzinfo=self.ET)
            
            # Handle weekly boundaries:
            # If the calculated session start is before Sunday 6 PM ET of the current week (i.e. it's Saturday),
            # or if it's currently Sunday before 6 PM ET, there's no active session.
            # In such cases, we might want to show PnL as 0, or PnL for the *last completed session*.
            # For simplicity, if `now_et` is Saturday or Sunday before market open,
            # this calculation will correctly pick up the last *actual* trading session (Friday's).
            # When Sunday 6 PM ET hits, it will correctly pick up the start of the new trading week.

            # Convert to UTC for the API call payload
            start_of_day_utc = start_of_topstep_session_et.astimezone(timezone.utc)
            end_of_day_utc = end_of_topstep_session_et.astimezone(timezone.utc)
            
            logger.info(f"AccountManager: Fetching daily PnL for TopstepX trading day from {start_of_day_utc.isoformat()} to {end_of_day_utc.isoformat()} UTC.")
            # --- END Trading Day Calculation ---

            payload = {
                "accountId": self.current_account_id,
                "startTime": start_of_day_utc.isoformat(),
                "endTime": end_of_day_utc.isoformat()
            }

            daily_pnl = 0.0
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    trades = data.get("trades", []) # Assuming 'trades' key
                    for trade in trades:
                        # Assuming PnL is in a field like 'profitAndLoss' as per previous logs
                        pnl_field_name = "profitAndLoss"
                        trade_pnl = trade.get(pnl_field_name)
                        if isinstance(trade_pnl, (int, float)):
                            daily_pnl += trade_pnl
                        else:
                            # This warning is expected if 'profitAndLoss' comes as None from the API
                            logger.warning(f"AccountManager: Trade PnL ('{pnl_field_name}') not numeric or missing in trade: {trade}. Fees: {trade.get('fees')}")

            self.current_daily_pnl = daily_pnl
            logger.info(f"AccountManager: Fetched daily PnL: {self.current_daily_pnl:.2f} for TopstepX trading day.")

        except aiohttp.ClientResponseError as e:
            response_text = await e.response.text()
            self.diagnostics_log_signal.emit(f"AccountManager: Failed to fetch daily PnL - HTTP Error {e.status}: {e.message}. Response: {response_text}")
            logger.error(f"AccountManager: Failed to fetch daily PnL - HTTP Error {e.status}: {e.message}. Response: {response_text}")
        except Exception as e:
            self.diagnostics_log_signal.emit(f"AccountManager: Error fetching daily PnL: {e}")
            logger.error(f"AccountManager: Error fetching daily PnL: {e}")

    # --- User Hub Callbacks (for real-time updates) ---
    def process_account_update(self, args):
        """Handler for GatewayUserAccount updates from User Hub."""
        # args[1] contains the actual data.
        # Assuming args format: [contract_id, {account_info}] or similar.
        # This will depend on the exact structure of GatewayUserAccount from TopstepX
        try:
            # Node.js bridge sends the data directly as the payload, not wrapped in an extra list.
            account_data_payload = args[1] 
            account_data = account_data_payload[0] if isinstance(account_data_payload, list) else account_data_payload
            
            # Fix: Check for 'id' first, then 'accountId'
            if str(account_data.get("id")) == self.current_account_id or str(account_data.get("accountId")) == self.current_account_id:
                equity = account_data.get("accountValue") # Common field name
                balance = account_data.get("balance") # Common field name
                
                if equity is not None:
                    self.current_equity = equity
                if balance is not None:
                    self.current_balance = balance
                
                logger.debug(f"AccountManager: GatewayUserAccount update - Equity: {self.current_equity}, Balance: {self.current_balance}")
                # Emit update to GUI if relevant for immediate display
                self.account_data_signal.emit({
                    "equity": self.current_equity,
                    "daily_pnl": self.current_daily_pnl, # Include current daily PnL from polling
                    "account_id": self.current_account_id
                })
        except Exception as e:
            logger.error(f"AccountManager: Error processing GatewayUserAccount update: {e} - Data: {args}")
            self.diagnostics_log_signal.emit(f"AccountManager: Error processing account update: {e}")

    # User Hub order/position/trade updates will be handled by RealTradeManager directly

    def get_current_account_id(self) -> Optional[str]:
        return self.current_account_id

    def get_current_equity(self) -> Optional[float]:
        return self.current_equity

    def get_current_daily_pnl(self) -> Optional[float]:
        return self.current_daily_pnl

    def stop_polling(self):
        if self.polling_task:
            self.polling_task.cancel()
            logger.info("AccountManager: Stopped periodic data polling.")