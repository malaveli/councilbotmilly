# gui_main.py (with Codex layout fixes applied)

import sys
import asyncio
import threading
import logging
import json
import os
import subprocess
import time
import requests
import aiohttp
import jwt
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QTextEdit, QTabWidget,
    QCheckBox, QGroupBox, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread, QMetaObject, Q_ARG, QObject
from PySide6.QtGui import QPalette, QColor, QFont, QTextCharFormat, QTextCursor, QIntValidator, QDoubleValidator

from auth_handler import AuthHandler
from market_state_engine import MarketStateEngine
from gui_connector import GUIConnector
from telegram_alert import TelegramAlert
from market_context import MarketContext
from account_manager import AccountManager
import config

from models import TradeSignal, MarketData, Position, Order, TradeDirection, OrderType
from exceptions import APIError, AuthenticationError
from topstep_client_facade import TopstepClientFacade
from risk_management import RiskManager
from strategies import StrategyManager
from engine import ExecutionEngine
from market_analyzer import MarketAnalyzer
from CouncilIndicators import SmartVolumeProfile, CumulativeDelta
from performance import PerformanceMonitor
from strategy_optimizer import StrategyOptimizer
from order_scheduler import OrderScheduler

import flask_data_receiver
from flask_data_receiver import FlaskSignalEmitter
from auth_worker import AuthWorker
from ai_commentary import AICommentary

print("--- Script execution started. ---")
logger = logging.getLogger(__name__)

class QAsyncioEventLoopThread(QThread):
    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.running = True

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self):
        self.running = False
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()

    def call_async(self, coro):
        if self.running and self.loop.is_running() and not self.loop.is_closed():
            return asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            logger.warning(f"Attempted to call async on stopped, non-running, or closed asyncio thread. Coro: {coro.__name__ if hasattr(coro, '__name__') else 'unknown'}")
            return None

class CouncilBotGUI(QMainWindow):
    update_signal_feed = Signal(str)
    update_commentary_feed = Signal(str)
    update_diagnostics_log = Signal(str)
    update_current_signal_display = Signal(dict)
    update_market_data_overview = Signal(str)
    update_overall_status = Signal(str)
    update_trade_log_panel = Signal(str)
    set_trading_enabled_signal = Signal(bool)
    set_real_trading_mode_signal = Signal(bool)
    update_account_data_signal = Signal(dict)
    init_bot_modules_signal = Signal()
    SETTINGS_FILE = "settings.json"

    def __init__(self):
        super().__init__()
        print("--- CouncilBotGUI constructor entered. ---")
        self.setWindowTitle("Council Bot")
        self.setGeometry(100, 100, 1400, 900)

        self.auth_handler: AuthHandler = AuthHandler()
        self.account_manager: Optional[AccountManager] = None
        self.market_state_engine: Optional[MarketStateEngine] = None
        self.market_context: Optional[MarketContext] = None
        self.telegram_alert: Optional[TelegramAlert] = None

        self.topstep_client_facade: Optional[TopstepClientFacade] = None
        self.risk_manager: Optional[RiskManager] = None
        self.strategy_manager: Optional[StrategyManager] = None
        self.execution_engine: Optional[ExecutionEngine] = None
        self.market_analyzer: Optional[MarketAnalyzer] = None
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.strategy_optimizer: Optional[StrategyOptimizer] = None
        self.order_scheduler: Optional[OrderScheduler] = None

        self.ai_commentary: Optional[AICommentary] = None
        self.gui_connector: Optional[GUIConnector] = None

        self.api_key_input_value: Optional[str] = None

        self.asyncio_thread = QAsyncioEventLoopThread()
        self.asyncio_thread.start()

        self.flask_signal_emitter = FlaskSignalEmitter()
        flask_data_receiver.set_signal_emitter(self.flask_signal_emitter)

        self.nodejs_process: Optional[subprocess.Popen] = None

        self.init_ui()

        self._setup_text_edit_formatting()
        self._apply_theme()

        self.trading_enabled = False
        self.real_trading_mode = config.LIVE_TRADING_ENABLED_DEFAULT
        self.set_trading_enabled_signal.connect(self._toggle_trading_state)
        self.set_real_trading_mode_signal.connect(self._toggle_real_trading_mode)

        self.update_account_data_signal.connect(self._update_account_data_labels)

        self.account_manager_account_id_signal_connected = False
        self.init_bot_modules_signal.connect(self._initialize_bot_modules)

        self.gui_live_data_timer = QTimer(self)
        self.gui_live_data_timer.timeout.connect(self._update_gui_live_data)
        self.gui_live_data_timer.start(500)
        print("--- CouncilBotGUI constructor exited. ---")

    def init_ui(self):
        self._setup_login_ui()
        self._setup_main_bot_ui()
        self.setCentralWidget(self.login_widget)

    def _setup_main_bot_ui(self):
        self.main_bot_widget = QWidget()
        main_layout = QVBoxLayout()

        top_control_panel = QWidget()
        top_control_layout = QVBoxLayout()

        status_bar_layout = QHBoxLayout()
        self.overall_status_label = QLabel("Status: Disconnected")
        self.overall_status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        status_bar_layout.addWidget(self.overall_status_label)
        status_bar_layout.addStretch(1)

        self.current_price_label = QLabel("Last Price: N/A")
        status_bar_layout.addWidget(self.current_price_label)
        status_bar_layout.addStretch(1)

        self.active_trade_label = QLabel("Active Trade: None")
        status_bar_layout.addWidget(self.active_trade_label)
        status_bar_layout.addStretch(1)

        self.account_balance_label = QLabel("Account: N/A")
        status_bar_layout.addWidget(self.account_balance_label)
        status_bar_layout.addStretch(1)

        self.daily_pnl_label = QLabel("Daily PnL: N/A")
        status_bar_layout.addWidget(self.daily_pnl_label)
        status_bar_layout.addStretch(1)

        self.total_pnl_label = QLabel("Total Sim PnL: $0.00")
        status_bar_layout.addWidget(self.total_pnl_label)
        top_control_layout.addLayout(status_bar_layout)

        control_center_group = QGroupBox("Control Center")
        control_center_layout = QHBoxLayout()

        self.start_trading_button = QPushButton("Start Trading")
        self.start_trading_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.start_trading_button.clicked.connect(lambda: self.set_trading_enabled_signal.emit(True))
        self.start_trading_button.setEnabled(False)
        control_center_layout.addWidget(self.start_trading_button)

        self.stop_trading_button = QPushButton("Stop Trading")
        self.stop_trading_button.setStyleSheet("background-color: #f44336; color: white;")
        self.stop_trading_button.clicked.connect(lambda: self.set_trading_enabled_signal.emit(False))
        self.stop_trading_button.setEnabled(False)
        control_center_layout.addWidget(self.stop_trading_button)

        control_center_layout.addSpacing(20)
        self.real_trading_mode_checkbox = QCheckBox("Live Trading Mode")
        self.real_trading_mode_checkbox.setChecked(config.LIVE_TRADING_ENABLED_DEFAULT)
        self.real_trading_mode_checkbox.stateChanged.connect(lambda state: self.set_real_trading_mode_signal.emit(state == Qt.Checked))
        control_center_layout.addWidget(self.real_trading_mode_checkbox)

        control_center_group.setLayout(control_center_layout)
        top_control_layout.addWidget(control_center_group)

        top_control_panel.setLayout(top_control_layout)
        main_layout.addWidget(top_control_panel)

        self.tab_widget = QTabWidget()

        dashboard_tab = QWidget()
        dashboard_layout = QVBoxLayout()

        self.current_signal_group = QGroupBox("Latest Signal")
        self.current_signal_layout = QGridLayout()
        self.current_signal_group.setLayout(self.current_signal_layout)
        dashboard_layout.addWidget(self.current_signal_group)
        self._setup_current_signal_display()

        feeds_grid_widget = QWidget()
        feeds_grid_layout = QGridLayout(feeds_grid_widget)

        self.market_data_overview_panel = QTextEdit()
        self.market_data_overview_panel.setReadOnly(True)
        self.market_data_overview_panel.setPlaceholderText("Live Market Data Overview...")
        self.market_data_overview_panel.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;")
        market_data_group = QGroupBox("Market Data Overview")
        market_data_layout = QVBoxLayout()
        market_data_layout.addWidget(self.market_data_overview_panel)
        market_data_group.setLayout(market_data_layout)
        feeds_grid_layout.addWidget(market_data_group, 0, 0)

        self.commentary_panel = QTextEdit()
        self.commentary_panel.setReadOnly(True)
        self.commentary_panel.setPlaceholderText("AI Commentary and Trade Warnings...")
        self.commentary_panel.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;")
        commentary_group = QGroupBox("AI Commentary")
        commentary_layout = QVBoxLayout()
        commentary_layout.addWidget(self.commentary_panel)
        commentary_group.setLayout(commentary_layout)
        feeds_grid_layout.addWidget(commentary_group, 0, 1)

        self.signal_feed_panel = QTextEdit()
        self.signal_feed_panel.setReadOnly(True)
        self.signal_feed_panel.setPlaceholderText("Historical Signal Feed...")
        self.signal_feed_panel.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;")
        signal_feed_group = QGroupBox("Historical Signal Feed")
        signal_feed_layout = QVBoxLayout()
        signal_feed_layout.addWidget(self.signal_feed_panel)
        signal_feed_group.setLayout(signal_feed_layout)
        feeds_grid_layout.addWidget(signal_feed_group, 1, 0)

        self.diagnostics_log_panel = QTextEdit()
        self.diagnostics_log_panel.setReadOnly(True)
        self.diagnostics_log_panel.setPlaceholderText("System Diagnostics, Connection Status, Errors...")
        self.diagnostics_log_panel.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;")
        diagnostics_group = QGroupBox("Diagnostics Log")
        diagnostics_layout = QVBoxLayout()
        diagnostics_layout.addWidget(self.diagnostics_log_panel)
        diagnostics_group.setLayout(diagnostics_layout)
        feeds_grid_layout.addWidget(diagnostics_group, 1, 1)

        feeds_grid_layout.setContentsMargins(0, 0, 0, 0)
        feeds_grid_layout.setSpacing(5)
        dashboard_layout.addWidget(feeds_grid_widget)

        self.trade_log_panel = QTextEdit()
        self.trade_log_panel.setReadOnly(True)
        self.trade_log_panel.setPlaceholderText("Completed Trade Log...")
        self.trade_log_panel.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px;")
        trade_log_group = QGroupBox("Trade Log")
        trade_log_layout = QVBoxLayout()
        trade_log_layout.addWidget(self.trade_log_panel)
        trade_log_group.setLayout(trade_log_layout)
        dashboard_layout.addWidget(trade_log_group)

        dashboard_tab.setLayout(dashboard_layout)
        self.tab_widget.addTab(dashboard_tab, "Dashboard")

        self._setup_settings_tab()
        self.tab_widget.addTab(self.settings_tab, "Settings")

        main_layout.addWidget(self.tab_widget)
        self.main_bot_widget.setLayout(main_layout)
      
    def _setup_current_signal_display(self):
        labels = [
            ("Signal:", ""), ("Entry:", "N/A"), ("Target:", "N/A"),
            ("Stop:", "N/A"), ("Confidence:", "N/A"), ("Reason:", "")
        ]
        self.signal_labels = {}
        for i, (key, default_val) in enumerate(labels):
            row = i // 2
            col_label = (i % 2) * 2
            col_value = (i % 2) * 2 + 1

            label_widget = QLabel(key)
            value_widget = QLabel(default_val)
            value_widget.setStyleSheet("font-weight: bold;")
            self.signal_labels[key.replace(":", "")] = value_widget

            self.current_signal_layout.addWidget(label_widget, row, col_label)
            self.current_signal_layout.addWidget(value_widget, row, col_value)

        self.current_signal_layout.setColumnStretch(1, 1)
        self.current_signal_layout.setColumnStretch(3, 1)

    def _setup_current_signal_display(self):
        labels = [
            ("Signal:", ""), ("Entry:", "N/A"), ("Target:", "N/A"),
            ("Stop:", "N/A"), ("Confidence:", "N/A"), ("Reason:", "")
        ]
        self.signal_labels = {}
        for i, (key, default_val) in enumerate(labels):
            row = i // 2
            col_label = (i % 2) * 2
            col_value = (i % 2) * 2 + 1

            label_widget = QLabel(key)
            value_widget = QLabel(default_val)
            value_widget.setStyleSheet("font-weight: bold;")
            self.signal_labels[key.replace(":", "")] = value_widget

            self.current_signal_layout.addWidget(label_widget, row, col_label)
            self.current_signal_layout.addWidget(value_widget, row, col_value)

        self.current_signal_layout.setColumnStretch(1, 1)
        self.current_signal_layout.setColumnStretch(3, 1)

    def _setup_settings_tab(self):
        self.settings_tab = QWidget()
        settings_layout = QVBoxLayout()

        api_keys_group = QGroupBox("API Keys")
        api_keys_layout = QGridLayout()

        api_keys_layout.addWidget(QLabel("Telegram Bot Token:"), 0, 0)
        self.telegram_bot_token_input = QLineEdit()
        api_keys_layout.addWidget(self.telegram_bot_token_input, 0, 1)

        api_keys_layout.addWidget(QLabel("Telegram Chat ID:"), 1, 0)
        self.telegram_chat_id_input = QLineEdit()
        api_keys_layout.addWidget(self.telegram_chat_id_input, 1, 1)

        api_keys_layout.addWidget(QLabel("Finnhub API Key:"), 2, 0)
        self.finnhub_api_key_input = QLineEdit()
        api_keys_layout.addWidget(self.finnhub_api_key_input, 2, 1)

        api_keys_group.setLayout(api_keys_layout)
        settings_layout.addWidget(api_keys_group)

        trading_params_group = QGroupBox("Simulated Trading Parameters")
        trading_params_layout = QGridLayout()

        trading_params_layout.addWidget(QLabel("Default Stop (Ticks):"), 0, 0)
        self.default_stop_ticks_input = QLineEdit()
        self.default_stop_ticks_input.setValidator(QIntValidator(1, 100))
        trading_params_layout.addWidget(self.default_stop_ticks_input, 0, 1)

        trading_params_layout.addWidget(QLabel("Default Target (Ticks):"), 1, 0)
        self.default_target_ticks_input = QLineEdit()
        self.default_target_ticks_input.setValidator(QIntValidator(1, 100))
        trading_params_layout.addWidget(self.default_target_ticks_input, 1, 1)

        trading_params_group.setLayout(trading_params_layout)
        settings_layout.addWidget(trading_params_group)

        strategy_params_group = QGroupBox("Strategy Parameters")
        strategy_params_layout = QGridLayout()

        strategy_params_layout.addWidget(QLabel("Min Confidence Threshold:"), 0, 0)
        self.min_confidence_threshold_input = QLineEdit()
        self.min_confidence_threshold_input.setValidator(QDoubleValidator(0.0, 1.0, 2))
        strategy_params_layout.addWidget(self.min_confidence_threshold_input, 0, 1)

        strategy_params_layout.addWidget(QLabel("Signal Cooldown (Seconds):"), 1, 0)
        self.cooldown_seconds_input = QLineEdit()
        self.cooldown_seconds_input.setValidator(QIntValidator(1, 3600))
        strategy_params_layout.addWidget(self.cooldown_seconds_input, 1, 1)

        strategy_params_group.setLayout(strategy_params_layout)
        settings_layout.addWidget(strategy_params_group)

        theme_layout = QHBoxLayout()
        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.dark_mode_checkbox.setChecked(True)
        self.dark_mode_checkbox.stateChanged.connect(self._apply_theme)
        theme_layout.addWidget(self.dark_mode_checkbox)
        theme_layout.addStretch(1)

        settings_layout.addLayout(theme_layout)

        self.save_settings_button = QPushButton("Save Settings and Apply")
        self.save_settings_button.clicked.connect(self._save_settings)
        settings_layout.addWidget(self.save_settings_button)

        settings_layout.addStretch(1)
        self.settings_tab.setLayout(settings_layout)
 
    def _setup_text_edit_formatting(self):
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)

        self.base_format = QTextCharFormat()
        self.base_format.setFont(font)

        self.signal_format_buy = QTextCharFormat(self.base_format)
        self.signal_format_buy.setForeground(QColor("#4CAF50"))

        self.signal_format_sell = QTextCharFormat(self.base_format)
        self.signal_format_sell.setForeground(QColor("#f44336"))

        self.warning_format = QTextCharFormat(self.base_format)
        self.warning_format.setForeground(QColor("#FFC107"))

        self.info_format = QTextCharFormat(self.base_format)
        self.info_format.setForeground(QColor("#2196F3"))

    def _apply_theme(self):
        palette = QApplication.instance().palette()
        text_color = QColor(255, 255, 255) if self.dark_mode_checkbox.isChecked() else QColor(0, 0, 0)

        if self.dark_mode_checkbox.isChecked():
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
            palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
            palette.setColor(QPalette.Text, QColor(255, 255, 255))
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
            palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        else:
            QApplication.instance().setPalette(QApplication.instance().style().standardPalette())

        QApplication.instance().setPalette(palette)

        self.base_format.setForeground(text_color)
        for panel in [
            self.signal_feed_panel,
            self.commentary_panel,
            self.diagnostics_log_panel,
            self.market_data_overview_panel,
            self.trade_log_panel
        ]:
            cursor = panel.textCursor()
            cursor.select(QTextCursor.Document)
            cursor.setCharFormat(self.base_format)
            panel.setTextCursor(cursor)
            panel.verticalScrollBar().setValue(panel.verticalScrollBar().maximum())
 
    def _append_formatted_text(self, panel, text, format_type):
        cursor = panel.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", format_type)
        panel.setTextCursor(cursor)
        panel.verticalScrollBar().setValue(panel.verticalScrollBar().maximum())

    @Slot(str)
    def _append_to_signal_feed(self, text):
        self._append_formatted_text(self.signal_feed_panel, text, self.base_format)

    @Slot(str)
    def _append_to_commentary_feed(self, text):
        if "Signal:" in text and "BUY" in text:
            self._append_formatted_text(self.commentary_panel, text, self.signal_format_buy)
        elif "Signal:" in text and "SELL" in text:
            self._append_formatted_text(self.commentary_panel, text, self.signal_format_sell)
        elif "⚠️" in text:
            self._append_formatted_text(self.commentary_panel, text, self.warning_format)
        else:
            self._append_formatted_text(self.commentary_panel, text, self.info_format)

    @Slot(str)
    def _set_overall_status_label(self, text):
        self.overall_status_label.setText(text)

    @Slot(str)
    def _append_to_diagnostics_log(self, text):
        self._append_formatted_text(self.diagnostics_log_panel, text, self.info_format)

    @Slot(str)
    def _append_to_trade_log_panel(self, text):
        self._append_formatted_text(self.trade_log_panel, text, self.base_format)

    @Slot(dict)
    def _update_current_signal_labels(self, signal_data):
        if not signal_data:
            for label_name in self.signal_labels:
                self.signal_labels[label_name].setText("N/A")
                self.signal_labels[label_name].setStyleSheet("font-weight: bold;")
            self.signal_labels["Signal"].setText("")
            return

        signal_type = signal_data.get("signal", "N/A")
        entry_price = signal_data.get("entry_price", "N/A")
        target_price = signal_data.get("target_price", "N/A")
        stop_price = signal_data.get("stop_price", "N/A")
        confidence = signal_data.get("confidence", "N/A")
        reason = signal_data.get("reason", "")

        self.signal_labels["Signal"].setText(signal_type)
        if "BUY" in signal_type:
            self.signal_labels["Signal"].setStyleSheet("font-weight: bold; color: #4CAF50;")
        elif "SELL" in signal_type:
            self.signal_labels["Signal"].setStyleSheet("font-weight: bold; color: #f44336;")
        else:
            self.signal_labels["Signal"].setStyleSheet("font-weight: bold; color: #FFC107;")

        self.signal_labels["Entry"].setText(f"{entry_price:.2f}" if isinstance(entry_price, (float, int)) else str(entry_price))
        self.signal_labels["Target"].setText(f"{target_price:.2f}" if isinstance(target_price, (float, int)) else str(target_price))
        self.signal_labels["Stop"].setText(f"{stop_price:.2f}" if isinstance(stop_price, (float, int)) else str(stop_price))
        self.signal_labels["Confidence"].setText(f"{confidence:.2f}" if isinstance(confidence, (float, int)) else str(confidence))
        self.signal_labels["Reason"].setText(reason)
 
    @Slot(str)
    def _update_market_data_overview_panel(self, html_text):
        self.market_data_overview_panel.setHtml(html_text)

    @Slot(bool)
    def _toggle_trading_state(self, enabled):
        self.trading_enabled = enabled
        if self.gui_connector:
            self.gui_connector.set_trading_enabled(enabled)
        self.start_trading_button.setEnabled(not enabled)
        self.stop_trading_button.setEnabled(enabled)
        status_text = "Trading Enabled" if enabled else "Trading Disabled"
        self._append_to_diagnostics_log(f"Control: {status_text}")
        logger.info(f"Trading state changed to: {status_text}")

    @Slot(bool)
    def _toggle_real_trading_mode(self, enabled):
        self.real_trading_mode = enabled
        if self.gui_connector:
            self.gui_connector.set_real_trading_mode(enabled)
        mode_text = "LIVE TRADING" if enabled else "SIMULATED TRADING"
        self._append_to_diagnostics_log(f"Mode: Switched to {mode_text} mode.")
        logger.info(f"Trading mode switched to: {mode_text}.")
        if self.execution_engine:
            self.execution_engine.reset_pnl_and_trades(live_mode=self.real_trading_mode)
        self.total_pnl_label.setText(f"Total {'Live' if enabled else 'Sim'} PnL: $0.00")
        self.trade_log_panel.clear()
        if self.risk_manager:
            self.risk_manager.reset_daily_pnl_tracking()

    @Slot(dict)
    def _update_account_data_labels(self, data):
        equity = data.get("equity")
        daily_pnl = data.get("daily_pnl")
        account_id = data.get("account_id")
        if equity is not None:
            equity_color = "green" if equity >= 0 else "red"
            self.account_balance_label.setText(f"Acct ({account_id or 'N/A'}): <span style='color:{equity_color};'>${equity:.2f}</span>")
        else:
            self.account_balance_label.setText(f"Acct ({account_id or 'N/A'}): N/A")
        if daily_pnl is not None:
            pnl_color = "green" if daily_pnl >= 0 else "red"
            self.daily_pnl_label.setText(f"Daily PnL: <span style='color:{pnl_color};'>${daily_pnl:.2f}</span>")
        else:
            self.daily_pnl_label.setText("Daily PnL: N/A")
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CouncilBotGUI()
    window.show()
    sys.exit(app.exec())
               