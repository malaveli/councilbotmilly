# risk_management.py

import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any  # Added Any import

# Import the new consolidated models
from models import Position, TradeSignal, TradeDirection, MarketData  # Added MarketData import

# Import the TopstepClientFacade (which wraps Auth, Account, RealTrade Managers)
from topstep_client_facade import TopstepClientFacade

logger = logging.getLogger(__name__)

class RiskManager:
    """
    Manages risk parameters for automated trading:
    - Dynamic daily loss limit with trailing profit adjustment
    - Volatility-adjusted and balance-based position sizing
    - Margin & exposure verification
    - Automated stop-loss enforcement
    - Trading cooldown enforcement after loss limits
    """
    def __init__(self, api_client: TopstepClientFacade, max_daily_loss: float, max_acceptable_volatility: float, diagnostics_log_signal: Any):
        self.api_client = api_client
        self.max_initial_daily_loss = max_daily_loss  # Store the initial max loss
        self.current_max_daily_loss = max_daily_loss  # This can adjust dynamically
        self.current_pnl = 0.0  # Will be updated by check_daily_loss
        self.cooldown_active = False  # Flag for trading cooldown
        self.max_acceptable_volatility = max_acceptable_volatility
        self.exposure_limits: Dict[str, float] = {}  # {contract_id: max_market_value_exposure}
        self.diagnostics_log_signal = diagnostics_log_signal  # For logging to GUI

        logger.info(f"RiskManager initialized. Max initial daily loss: ${self.max_initial_daily_loss:.2f}")

    async def check_daily_loss(self):
        """
        Enforce maximum daily loss limits with trailing loss adjustments.
        This method should be called periodically (e.g., from GUIConnector).
        """
        try:
            # Get current PnL from the facade
            # Note: AccountManager's get_current_daily_pnl() might be None initially.
            # This logic needs to align with AccountManager's actual updates.
            # Assuming api_client.get_account_pnl() will eventually return a float.
            fetched_pnl = await self.api_client.get_account_pnl()
            if fetched_pnl is not None:
                self.current_pnl = fetched_pnl
            else:
                logger.warning("RiskManager: Could not fetch current PnL. Daily loss check skipped for this cycle.")
                return  # Skip check if PnL is not available

            # Adjust loss limit dynamically based on positive PnL (trailing loss)
            # This means if you make $1000, your max loss for the day becomes less negative than initial
            # e.g., if initial max_loss=-1000, and current_pnl=+1000, then max_loss becomes +1000 * 0.3 = $300
            # This is a VERY aggressive trailing stop for the daily PnL.
            # A more common approach is `max_loss = max(initial_max_loss, highest_pnl_so_far - drawdown_tolerance)`.
            # For now, sticking to the provided logic but noting its aggression.
            if self.current_pnl > 0:
                self.current_max_daily_loss = max(self.max_initial_daily_loss, self.current_pnl * 0.3)
                logger.debug(f"RiskManager: Adjusted max daily loss to ${self.current_max_daily_loss:.2f} based on positive PnL.")
            else:
                self.current_max_daily_loss = self.max_initial_daily_loss  # Reset if PnL goes negative


            # Check if loss limit is breached
            if self.current_pnl <= -abs(self.current_max_daily_loss):
                if not self.cooldown_active:  # Only log and trigger once
                    self.cooldown_active = True
                    reason = f"🚨 Max daily loss limit of ${self.current_max_daily_loss:.2f} breached! Current PnL: ${self.current_pnl:.2f}. Trading cooldown activated."
                    logger.warning(reason)
                    self.diagnostics_log_signal.emit(f"RISK BREACH: {reason}")
                    # Trigger the actual disabling of trading in the GUIConnector/main loop
                    await self.api_client.disable_trading()  # This method on facade needs to trigger GUI signal
            else:
                if self.cooldown_active and self.current_pnl > -abs(self.max_initial_daily_loss) * 0.5:  # Example: allow re-enable if recovered halfway
                    self.cooldown_active = False
                    logger.info("RiskManager: Daily PnL recovered, cooldown deactivated.")
                    self.diagnostics_log_signal.emit("RISK: Daily PnL recovered, cooldown deactivated.")
                    # Re-enable trading if desired, but typically, a breach means done for the day.
                    # This would need a corresponding `enable_trading` method on api_client/GUIConnector.

        except Exception as e:
            logger.error(f"RiskManager: Error during daily loss check: {e}")
            self.diagnostics_log_signal.emit(f"RISK ERROR: Daily loss check failed: {e}")


    async def adjust_position_size(self, trade_signal: TradeSignal) -> int:
        """
        Dynamically adjust trade size based on volatility and account balance.
        This method will be called by StrategyManager or directly before trade execution.
        """
        volatility = trade_signal.volatility  # Expected to be in TradeSignal
        if volatility is None:
            logger.warning("RiskManager: Volatility not found in trade_signal. Using default 1.0.")
            volatility = 1.0

        account_balance = await self.api_client.get_account_balance()

        # Base position size determined by volatility and balance thresholds
        # Ensure volatility is not zero or too small to avoid division by zero or huge sizes
        effective_volatility = max(volatility, 0.01)  # Avoid division by zero

        # The logic: account_balance / (volatility * 1000)
        # This seems to imply a certain capital allocation per unit of volatility.
        base_size = int(account_balance / (effective_volatility * 1000))

        # Further adjust based on strategy confidence (from TradeSignal)
        confidence = trade_signal.confidence

        # Apply a minimum to the confidence to ensure size is not tiny
        effective_confidence = max(confidence, 0.6)  # Minimum confidence for sizing

        final_size = max(1, int(base_size * effective_confidence))  # Ensure at least 1 contract if eligible

        logger.info(f"📊 Adjusted Position Size: {final_size} contracts | Balance: ${account_balance:.2f}, Volatility: {volatility:.2f}, Confidence: {confidence:.2f}")
        self.diagnostics_log_signal.emit(f"RISK: Adj. Size: {final_size} (Bal:${account_balance:.0f}, Vol:{volatility:.1f}, Conf:{confidence:.1f})")

        return final_size

    def calculate_contract_size(self, account_equity: Optional[float], signal_confidence: float) -> int:
        """Simplified contract sizing used by GUIConnector."""
        if account_equity is None or account_equity <= 0:
            logger.warning("RiskManager: Account equity unavailable, returning 0 contract size.")
            return 0

        base_size = int(account_equity / 10000)
        effective_confidence = max(signal_confidence, 0.6)
        return max(1, int(base_size * effective_confidence))

    async def enforce_stop_loss(self, position: Position):
        """
        Trigger stop-loss automatically if price falls below threshold.
        This would be called periodically by ExecutionEngine or a main loop.
        """
        # Ensure position has a defined stop_loss_price set by the ExecutionEngine
        if position.stop_loss_price is None:
            logger.debug(f"RiskManager: Position {position.symbol} has no stop-loss price defined. Skipping enforcement.")
            return

        # Check current price against stop loss price based on direction
        current_price = position.current_market_price
        if current_price is None:
            logger.warning(f"RiskManager: Cannot enforce stop-loss for {position.symbol}, current market price is unknown.")
            return

        stop_triggered = False
        if position.direction == TradeDirection.LONG and current_price <= position.stop_loss_price:
            stop_triggered = True
        elif position.direction == TradeDirection.SHORT and current_price >= position.stop_loss_price:
            stop_triggered = True

        if stop_triggered:
            logger.warning(f"🚨 Stop-loss triggered for {position.symbol} at {current_price:.2f}. Closing position.")
            self.diagnostics_log_signal.emit(f"RISK: SL Triggered for {position.symbol} @ {current_price:.2f}")
            await self.api_client.close_position(position.symbol, position.quantity)  # Pass contract_id and full quantity

    async def verify_margin_risk(self, trade_signal: TradeSignal, size: int) -> bool:
        """Ensure sufficient margin exists for a new trade."""
        required_margin = await self.api_client.get_margin_requirement(trade_signal.contract_id, size)
        account_balance = await self.api_client.get_account_balance()

        if account_balance < required_margin:
            reason = f"⚠ Insufficient margin for {trade_signal.contract_id} (Req: ${required_margin:.2f}, Avail: ${account_balance:.2f}). Trade rejected."
            logger.warning(reason)
            self.diagnostics_log_signal.emit(f"RISK: {reason}")
            trade_signal.rejection_reason = reason  # Update signal with rejection reason
            return False
        return True

    async def monitor_volatility(self, market_data: MarketData):
        """Track market volatility and issue risk alerts."""
        volatility_index = market_data.indicators.get("volatility", 0.0)

        if volatility_index > self.max_acceptable_volatility:
            reason = f"🚨 High Volatility Alert! Market conditions ({volatility_index:.2f}) unstable for trading (Max Acceptable: {self.max_acceptable_volatility:.2f})."
            logger.warning(reason)
            self.diagnostics_log_signal.emit(f"RISK: {reason}")
            # This could potentially trigger a cooldown or temporarily disable trading

    async def monitor_exposure(self, position: Position):
        """
        Prevent over-leveraging across multiple trades.
        This method assumes `self.exposure_limits` are set up.
        It should be called periodically for all open positions.
        """
        if position.symbol in self.exposure_limits:
            max_exposure_value = self.exposure_limits[position.symbol]
            if position.market_value > max_exposure_value:
                reason = f"⚠ Exposure limit (${max_exposure_value:.2f}) exceeded for {position.symbol} (Current: ${position.market_value:.2f}). Adjusting position size."
                logger.warning(reason)
                self.diagnostics_log_signal.emit(f"RISK: {reason}")
                await self.api_client.close_position(position.symbol, position.quantity)

    async def enforce_trading_cooldown(self) -> bool:
        """Prevent trading when cooldown is active."""
        if self.cooldown_active:
            logger.info("🛑 Trading cooldown in effect. No new trades allowed.")
            self.diagnostics_log_signal.emit("RISK: Trading cooldown active.")
            return False
        return True

    async def ensure_risk_limits(self) -> bool:
        """
        Verify that trading stays within predefined overall risk limits (beyond daily loss).
        This is a final check before trade execution.
        """
        if self.cooldown_active:  # Rely on cooldown from check_daily_loss
            return False

        # Add other general risk checks here if needed (e.g., total open PnL limit, drawdowns)

        return True  # If no general risk limits are breached

    async def track_trade_rejections(self, trade_signal: TradeSignal):
        """Log rejected trades and provide reasoning."""
        reason = trade_signal.rejection_reason or "Unknown issue"  # Get from TradeSignal
        logger.info(f"❌ Trade Rejected: {reason}")
        self.diagnostics_log_signal.emit(f"TRADE REJECTED: {reason}")

    async def validate_trade_eligibility(self, trade_signal: TradeSignal, current_trade_size: int) -> bool:
        """
        Final safeguard to verify a trade can proceed.
        This is a composite check.
        """
        # 1. Check if overall risk limits are fine (including daily loss cooldown)
        if not await self.ensure_risk_limits():
            self.diagnostics_log_signal.emit("RISK: Trade blocked by overall risk limits.")
            trade_signal.rejection_reason = "Overall risk limits breached or cooldown active."
            return False

        # 2. Check for explicit cooldown (redundant with ensure_risk_limits if it checks cooldown)
        if self.cooldown_active:  # Redundant check if ensure_risk_limits covers it, but explicit here.
            self.diagnostics_log_signal.emit("RISK: Trade blocked due to active cooldown.")
            trade_signal.rejection_reason = "Trading cooldown active."
            return False

        # 3. Verify sufficient margin for the proposed trade size
        if not await self.verify_margin_risk(trade_signal, current_trade_size):  # Pass current_trade_size
            # Rejection reason already set inside verify_margin_risk
            return False

        logger.info(f"✅ Trade eligibility validated for: {trade_signal.strategy} {trade_signal.direction.value}")
        return True

    def reset_daily_pnl_tracking(self):
        """Resets daily PnL tracking and cooldown status (typically at start of new trading day)."""
        self.current_pnl = 0.0
        self.current_max_daily_loss = self.max_initial_daily_loss
        self.cooldown_active = False
        logger.info("RiskManager: Daily PnL tracking and cooldown reset.")
        self.diagnostics_log_signal.emit("RISK: Daily PnL tracking and cooldown reset.")
