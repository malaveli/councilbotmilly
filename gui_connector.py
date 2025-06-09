# gui_connector.py

from PySide6.QtCore import QTimer
import logging
from datetime import datetime
import config # Import config to get values for SL/TP when signal comes in
import asyncio # For create_task in enter_trade

logger = logging.getLogger(__name__)

class GUIConnector:
    def __init__(self, gui, signal_engine, virtual_trade_manager, real_trade_manager, account_manager, risk_engine, ai_commentary, telegram_alert=None, trading_enabled: bool = False, real_trading_mode: bool = False): # NEW parameters
        self.gui = gui
        self.signal_engine = signal_engine
        self.virtual_trade_manager = virtual_trade_manager # Renamed for clarity
        self.real_trade_manager = real_trade_manager # NEW
        self.account_manager = account_manager # NEW
        self.risk_engine = risk_engine # NEW
        self.ai_commentary = ai_commentary
        self.telegram_alert = telegram_alert
        self.trading_enabled = trading_enabled # Controls if signals lead to trades
        self.real_trading_mode = real_trading_mode # Controls if trades are real or simulated

        self.snapshot_provider = None
        self.last_price = None
        self.last_signal_time = None

        # Processing statistics
        self.signal_count = 0
        self.connection_status = "Initializing"

        # Main processing timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.process)
        self.timer.start(1000)  # Process every second

        # Status update timer (for internal GUIConnector status, separate from main GUI's live data timer)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_system_status)
        self.status_timer.start(5000)  # Update status every 5 seconds

        # Callback for updating the dedicated current signal display in GUI
        self._update_current_signal_display_signal = None # Set by gui_main
        self._update_trade_log_panel = None # NEW: Set by gui_main for trade log


        logger.info("GUIConnector initialized with enhanced features")

    def set_snapshot_provider(self, provider):
        self.snapshot_provider = provider
        self.connection_status = "Connected"
        logger.info("Snapshot provider set, connection status updated")

    def set_trading_enabled(self, enabled: bool):
        self.trading_enabled = enabled
        logger.info(f"Trading enabled state set to: {self.trading_enabled}")

    def set_real_trading_mode(self, enabled: bool): # NEW
        self.real_trading_mode = enabled
        logger.info(f"Real trading mode set to: {self.real_trading_mode}")

    def process(self):
        if not self.snapshot_provider:
            self._log_to_system_panel("Waiting for snapshot provider...")
            return

        try:
            snapshot = self.snapshot_provider()
            if not snapshot:
                self._log_to_system_panel("No market data snapshot available yet.")
                return

            self._update_current_price(snapshot)

            if self.last_price is None:
                self._log_to_system_panel("Waiting for valid last price from market data.")
                return
            
            # Update the appropriate trade manager with current price
            current_trade_manager = self.real_trade_manager if self.real_trading_mode else self.virtual_trade_manager
            if current_trade_manager:
                current_trade_manager.update_price(self.last_price)
                # Check for closed trades and append to log
                # IMPORTANT: Loop through all pending updates
                for trade_data in current_trade_manager.get_trade_log_and_clear():
                    self._update_trade_log_panel(trade_data) # Send dictionary to GUI for formatting


            self._check_active_trade_warnings()

            # IMPORTANT: Update MarketContext time before evaluation
            if self.gui.market_context:
                self.gui.market_context.update_current_time()
                # Debug logging for market context
                logger.debug(f"Market Context: Session={self.gui.market_context.get_current_session()}, Chop={self.gui.market_context.is_chop_now()}, NewsActive={self.gui.market_context.is_news_active()}")

            self._evaluate_signals(snapshot)

            # NEW: Periodically check risk engine status
            # Only check if account_manager is initialized and has a daily PnL value
            if self.risk_engine and self.account_manager and self.account_manager.current_daily_pnl is not None:
                current_daily_pnl = self.account_manager.current_daily_pnl
                is_trading_allowed = self.risk_engine.is_trading_allowed(current_daily_pnl)
                # Emit signal to GUI to update account data labels, including trading_allowed status
                self.gui.update_account_data_signal.emit({
                    "equity": self.account_manager.current_equity,
                    "daily_pnl": self.account_manager.current_daily_pnl,
                    "account_id": self.account_manager.current_account_id,
                    "trading_allowed": is_trading_allowed
                })


        except Exception as e:
            logger.error(f"Error in GUIConnector.process(): {e}")
            self._log_to_system_panel(f"❌ Processing error: {str(e)}")

    def _update_current_price(self, snapshot):
        latest_quote = snapshot.get("quotes", {})

        if latest_quote.get("last") is not None:
            self.last_price = latest_quote["last"]
        elif latest_quote.get("bid") is not None and latest_quote.get("ask") is not None:
            self.last_price = (latest_quote["bid"] + latest_quote["ask"]) / 2
        else:
            latest_bar = snapshot.get("current_bar", {}).get(1)
            if latest_bar:
                self.last_price = latest_bar["c"]

        if "current_trend" not in snapshot:
            snapshot["current_trend"] = "N/A"


    def _check_active_trade_warnings(self):
        # Check active trade for the current mode's manager
        current_trade_manager = self.real_trade_manager if self.real_trading_mode else self.virtual_trade_manager
        active_trade = current_trade_manager.get_active_trade() if current_trade_manager else None

        if active_trade and self.last_price is not None: # Ensure price is available
            try:
                warning = self.ai_commentary.generate_trade_warning(active_trade, self.last_price)
                if warning:
                    self._log_to_commentary_panel(warning)
                    self._log_to_system_panel(f"⚠️ Trade warning generated")
            except Exception as e:
                logger.error(f"Error generating trade warning: {e}")

    def _evaluate_signals(self, snapshot):
        logger.debug("GUIConnector: Evaluating signals...")
        try:
            signal_result = self.signal_engine.evaluate_snapshot(snapshot)

            if not signal_result:
                # Clear dedicated signal display if no active signal
                if self._update_current_signal_display_signal:
                    self._update_current_signal_display_signal(None)
                logger.debug("GUIConnector: No signal generated by strategy.")
                return

            self.signal_count += 1
            self.last_signal_time = datetime.utcnow()
            
            # Current price for signal display
            signal_price = self.last_price
            direction_multiplier = 1 if signal_result["signal"] == "BUY" else -1
            potential_sl = signal_price - config.DEFAULT_STOP_TICKS * 0.25 * direction_multiplier
            potential_tp = signal_price + config.DEFAULT_TARGET_TICKS * 0.25 * direction_multiplier

            # NEW: 1. Check for Market Context suppression (Chop Zone / News)
            if self.gui.market_context and self.gui.market_context.should_suppress_trades():
                suppress_reason = "chop zone" if self.gui.market_context.is_chop_now() else ("news event" if self.gui.market_context.is_news_active() else "unknown market condition")
                skip_msg = (f"[{datetime.utcnow().strftime('%H:%M:%S')}] "
                           f"🚫 Signal detected ({signal_result['signal']}) but trading suppressed due to {suppress_reason}. "
                           f"Skipping entry.")
                self._log_to_commentary_panel(skip_msg)
                self._log_to_system_panel(f"Signal skipped - {suppress_reason}")
                logger.info(f"Signal detected but trading suppressed due to {suppress_reason}.")
                if self._update_current_signal_display_signal:
                    self._update_current_signal_display_signal({
                        "signal": f"{signal_result['signal']} (SUPPRESSED)",
                        "entry_price": signal_price,
                        "target_price": potential_tp,
                        "stop_price": potential_sl,
                        "confidence": signal_result["confidence"],
                        "reason": f"SUPPRESSED: {signal_result['reason']}"
                    })
                return

            # NEW: 2. Check if risk engine allows trading
            # This check is done only if account_manager is initialized and has a daily PnL value
            if self.risk_engine and self.account_manager and self.account_manager.current_daily_pnl is not None:
                if not self.risk_engine.is_trading_allowed(self.account_manager.current_daily_pnl):
                    skip_msg = (f"[{datetime.utcnow().strftime('%H:%M:%M')}] "
                               f"🚫 Signal detected ({signal_result['signal']}) but RISK ENGINE prevents trading. "
                               f"Skipping entry.")
                    self._log_to_commentary_panel(skip_msg)
                    self._log_to_system_panel("Signal skipped - risk engine prevents trade")
                    logger.info("Signal detected but risk engine prevents trade.")
                    if self._update_current_signal_display_signal:
                        self._update_current_signal_display_signal({
                            "signal": f"{signal_result['signal']} (RISK BLOCKED)",
                            "entry_price": signal_price,
                            "target_price": potential_tp,
                            "stop_price": potential_sl,
                            "confidence": signal_result["confidence"],
                            "reason": f"RISK BLOCKED: {signal_result['reason']}"
                        })
                    return


            # NEW: 3. Check if an active trade already exists (for the current mode's manager)
            current_trade_manager = self.real_trade_manager if self.real_trading_mode else self.virtual_trade_manager
            active_trade = current_trade_manager.get_active_trade() if current_trade_manager else None

            if active_trade:
                skip_msg = (f"[{datetime.utcnow().strftime('%H:%M:%S')}] "
                           f"🚫 Signal detected ({signal_result['signal']}) but trade is ACTIVE. "
                           f"Skipping new entry.")

                self._log_to_commentary_panel(skip_msg)
                self._log_to_system_panel("Signal skipped - active trade exists")
                logger.info("Signal detected but trade is already open. Skipping new entry.")
                if self._update_current_signal_display_signal:
                    self._update_current_signal_display_signal({
                        "signal": f"{signal_result['signal']} (TRADE ACTIVE)",
                        "entry_price": signal_price,
                        "target_price": potential_tp,
                        "stop_price": potential_sl,
                        "confidence": signal_result["confidence"],
                        "reason": f"TRADE ACTIVE: {signal_result['reason']}"
                    })
                return
            
            # NEW: 4. Check if trading is enabled by the user before entering
            if not self.trading_enabled:
                skip_msg = (f"[{datetime.utcnow().strftime('%H:%M:%S')}] "
                           f"⚠️ Signal detected ({signal_result['signal']}) but USER TRADING is DISABLED. "
                           f"Skipping entry.")
                self._log_to_commentary_panel(skip_msg)
                self._log_to_system_panel("Signal skipped - user trading disabled")
                logger.info("Signal detected but user trading is disabled. Skipping entry.")
                if self._update_current_signal_display_signal:
                    self._update_current_signal_display_signal({
                        "signal": f"{signal_result['signal']} (USER BLOCKED)",
                        "entry_price": signal_price,
                        "target_price": potential_tp,
                        "stop_price": potential_sl,
                        "confidence": signal_result["confidence"],
                        "reason": f"USER BLOCKED: {signal_result['reason']}"
                    })
                return


            # Determine contract size
            # IMPORTANT: Current equity might be None if account manager hasn't fetched it yet.
            # RiskEngine handles this with a warning and returns 0.
            contract_size = self.risk_engine.calculate_contract_size(
                account_equity=self.account_manager.current_equity,
                signal_confidence=signal_result["confidence"]
            )
            if contract_size == 0:
                skip_msg = (f"[{datetime.utcnow().strftime('%H:%M:%S')}] "
                           f"🚫 Signal ({signal_result['signal']}) but contract size calculated as 0. "
                           f"Skipping entry. (Equity: {self.account_manager.current_equity}, Conf: {signal_result['confidence']})")
                self._log_to_commentary_panel(skip_msg)
                self._log_to_system_panel("Signal skipped - 0 contracts")
                logger.info("Signal detected but 0 contracts calculated. Skipping entry.")
                if self._update_current_signal_display_signal:
                    self._update_current_signal_display_signal({
                        "signal": f"{signal_result['signal']} (SIZE 0)",
                        "entry_price": signal_price,
                        "target_price": potential_tp,
                        "stop_price": potential_sl,
                        "confidence": signal_result["confidence"],
                        "reason": f"SIZE 0: {signal_result['reason']}"
                    })
                return

            # Update dedicated signal display with actual signal and calculated SL/TP
            if self._update_current_signal_display_signal:
                self._update_current_signal_display_signal({
                    "signal": signal_result["signal"],
                    "entry_price": signal_price,
                    "target_price": potential_tp,
                    "stop_price": potential_sl,
                    "confidence": signal_result["confidence"],
                    "reason": signal_result["reason"]
                })


            # Generate AI commentary for the signal
            signal_msg = self._generate_signal_message(signal_result)
            
            # Log to appropriate panels
            self._log_to_signal_panel(signal_msg)
            self._log_to_commentary_panel(signal_msg)
            
            # Send Telegram alert if configured
            self._send_telegram_alert(signal_msg)

            # Enter the trade using the appropriate trade manager
            self._enter_trade(signal_result, contract_size)


        except Exception as e:
            logger.error(f"Error evaluating signals: {e}")
            self._log_to_system_panel(f"❌ Signal evaluation error: {str(e)}")

    def _generate_signal_message(self, signal_result):
        try:
            base_msg = self.ai_commentary.generate_signal_comment(
                signal_result["signal"],
                signal_result["confidence"],
                signal_result["reason"]
            )

            timestamp = datetime.utcnow().strftime('%H:%M:%S')
            formatted_msg = f"[{timestamp}] 🎯 {base_msg}"

            return formatted_msg

        except Exception as e:
            logger.error(f"Error generating signal message: {e}")
            timestamp = datetime.utcnow().strftime('%H:%M:%S')
            return f"[{timestamp}] 📊 {signal_result['signal']} signal detected (confidence: {signal_result.get('confidence', 'N/A')})"

    def _enter_trade(self, signal_result, contract_size): # Added contract_size parameter
        """Enter a new trade based on signal using the appropriate manager."""
        entry_msg = (f"[{datetime.utcnow().strftime('%H:%M:%S')}] "
                    f"✅ Attempting {'LIVE' if self.real_trading_mode else 'SIM'} "
                    f"{signal_result['signal']} trade ({contract_size} contracts) at {self.last_price:.2f}")
        
        self._log_to_commentary_panel(entry_msg)
        self._log_to_system_panel(f"Trade attempt: {'LIVE' if self.real_trading_mode else 'SIM'} {signal_result['signal']} @ {self.last_price:.2f} ({contract_size} contracts)")
        logger.info(f"Attempting {'LIVE' if self.real_trading_mode else 'SIM'} trade: {signal_result['signal']} at {self.last_price:.2f} ({contract_size} contracts)")

        try:
            if self.real_trading_mode:
                # Call RealTradeManager for live trade
                # We need to ensure this async call is properly awaited or run in the asyncio loop
                # As GUIConnector.process is run by a QTimer, it's synchronous.
                # So we must use asyncio.create_task to hand it off to the main asyncio loop.
                self.gui.asyncio_thread.call_async(self.real_trade_manager.enter_trade(
                    signal_result["signal"], self.last_price, contract_size,
                    config.DEFAULT_STOP_TICKS, config.DEFAULT_TARGET_TICKS # Pass SL/TP ticks
                ))
            else:
                # Call VirtualTradeManager for simulated trade
                self.virtual_trade_manager.enter_trade(
                    signal_result["signal"], self.last_price, contract_size # Pass contract size
                )
            
            self._log_to_commentary_panel(f"[{datetime.utcnow().strftime('%H:%M:%S')}] ✅ Trade entry INITIATED: {'LIVE' if self.real_trading_mode else 'SIM'} {signal_result['signal']} at {self.last_price:.2f}")
            # For live trades, actual fill message will come from SignalR's user hub

        except Exception as e:
            logger.error(f"Error entering trade: {e}")
            self._log_to_system_panel(f"❌ Trade entry failed: {str(e)}")


    def _send_telegram_alert(self, message):
        if self.telegram_alert:
            try:
                self.telegram_alert.send_message(message)
                self._log_to_system_panel("📱 Telegram alert sent")
                logger.info("Telegram alert sent for new signal.")
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")
                self._log_to_system_panel(f"❌ Telegram alert failed: {str(e)}")

    def update_system_status(self):
        """Update system status information periodically"""
        try:
            status_parts = []

            status_parts.append(f"Connection: {self.connection_status}")

            if self.last_signal_time:
                time_since_signal = (datetime.utcnow() - self.last_signal_time).total_seconds()
                if time_since_signal < 60:
                    status_parts.append(f"Last Signal: {int(time_since_signal)}s ago")
                else:
                    status_parts.append(f"Last Signal: {int(time_since_signal/60)}m ago")

            # Check active trade for the current mode's manager
            current_trade_manager = self.real_trade_manager if self.real_trading_mode else self.virtual_trade_manager
            active_trade = current_trade_manager.get_active_trade() if current_trade_manager else None

            if active_trade:
                duration = (datetime.utcnow() - active_trade['open_time']).total_seconds()
                status_parts.append(f"Trade Active: {int(duration/60)}m")

            status_msg = " | ".join(status_parts)
            self._log_to_system_panel(f"💡 Status: {status_msg}")

        except Exception as e:
            logger.error(f"Error updating system status: {e}")

    # Thread-safe logging methods that use the GUI's signal system
    def _log_to_signal_panel(self, message):
        if hasattr(self.gui, 'update_signal_feed'):
            self.gui.update_signal_feed.emit(message)

    def _log_to_commentary_panel(self, message):
        if hasattr(self.gui, 'update_commentary_feed'):
            self.gui.update_commentary_feed.emit(message)

    def _log_to_system_panel(self, message): # Renamed
        if hasattr(self.gui, 'update_diagnostics_log'):
            self.gui.update_diagnostics_log.emit(message)

    def _update_current_signal_display_signal(self, data):
        """Placeholder, this is set by gui_main to emit its signal."""
        pass

    def _update_trade_log_panel(self, trade_data: dict): # NEW: Now takes trade_data dict
        if hasattr(self.gui, 'update_trade_log_panel'):
            # Format trade_data dict into a string for display
            dir_str = "Long" if trade_data["direction"] == 1 else "Short"
            res = trade_data.get("status", "UNKNOWN").upper()
            
            # PnL can be raw or ticks, ensure it's formatted based on type
            # Check for 'pnl_value' for virtual trades, 'realized_pnl' for real trades
            pnl_val = trade_data.get("pnl_value", trade_data.get("realized_pnl", "N/A"))
            pnl_display = f"${pnl_val:.2f}" if isinstance(pnl_val, (int, float)) else str(pnl_val) # Format as currency
            
            entry_price_display = f"{trade_data['entry_price']:.2f}" if isinstance(trade_data.get('entry_price'), (int, float)) else str(trade_data.get('entry_price', 'N/A'))
            exit_price_display = f"{trade_data['exit_price']:.2f}" if isinstance(trade_data.get('exit_price'), (int, float)) else str(trade_data.get('exit_price', 'N/A'))

            self.gui.update_trade_log_panel.emit(
                f"[{trade_data['open_time'].strftime('%H:%M:%S')}] TRADE {res}: {dir_str} {trade_data.get('size', 1)} @ {entry_price_display}, "
                f"Exit: {exit_price_display}, PnL: {pnl_display}"
            )

    def get_statistics(self):
        return {
            'signal_count': self.signal_count,
            'connection_status': self.connection_status,
            'last_price': self.last_price
        }

    def stop(self):
        try:
            if self.timer:
                self.timer.stop()
            if self.status_timer:
                self.status_timer.stop()
            logger.info("GUIConnector stopped cleanly")
        except Exception as e:
            logger.error(f"Error stopping GUIConnector: {e}")