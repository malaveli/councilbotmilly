# config.py

# ✅ Hardcoded username for TopstepX login
USERNAME = "millycapital"

# SignalR + API constants
API_BASE_URL = "https://api.topstepx.com"
MARKET_HUB_URL = "wss://rtc.topstepx.com/hubs/market"
USER_HUB_URL = "wss://rtc.topstepx.com/hubs/user" # NEW: User Hub URL

# Default contract (ES Futures)
DEFAULT_CONTRACT_ID = "CON.F.US.EP.M25"

# Signal confidence threshold
MIN_CONFIDENCE_THRESHOLD = 0.85

# Default SL/TP for simulated trades (ticks)
DEFAULT_STOP_TICKS = 6
DEFAULT_TARGET_TICKS = 10

# Daily profit target and signal minimum (for informational display, not strict bot logic)
MIN_DAILY_PROFIT = 300
MIN_SIGNALS_PER_DAY = 2

# Telegram Alert Settings (Leave empty if not using)
# Fill these with your actual Telegram bot token and chat ID if you want alerts.
TELEGRAM_BOT_TOKEN = "" # YOUR TELEGRAM BOT TOKEN HERE
TELEGRAM_CHAT_ID = "" # YOUR TELEGRAM CHAT ID HERE

# Finnhub API Key for News & Earnings (Required for MarketContext)
# IMPORTANT: The key "d0qbkg9r01qt60oncohgd0qbkg9r01qt60oncoi0" is a placeholder/example
# and is very likely INVALID or EXPIRED.
# You MUST obtain your own free API key from finnhub.io (or a similar news provider)
# and replace it below. A "403 Forbidden" error in the logs indicates an invalid key.
FINNHUB_API_KEY = "YOUR_FINNHUB_API_KEY_HERE" # <--- REPLACE THIS WITH YOUR ACTUAL FINNHUB API KEY

# Strategy Cooldown (in seconds) - will be updated by settings UI
STRATEGY_COOLDOWN_SECONDS = 60


# --- Automated Trading & Risk Engine Settings ---

# Default state for live trading mode (True for live, False for signal-only/simulated)
LIVE_TRADING_ENABLED_DEFAULT = False

# Max daily loss limit in USD (bot will NOT enforce this internally anymore)
# This setting has been removed from the bot's internal risk management.
# You should rely on TopstepX's platform-level risk controls for daily loss limits.
# MAX_DAILY_LOSS_USD = 1000.0 # <--- REMOVED

# Contract size tiers based on account equity (USD)
# Format: (Min Equity, Max Contracts)
CONTRACT_SIZE_TIERS_USD = [
    (0, 1),        # Default 1 contract for accounts below 50k
    (50000, 5),    # Up to 5 contracts for $50k+ account
    (100000, 10),  # Up to 10 contracts for $100k+ account
    (150000, 15)   # Up to 15 contracts for $150k+ account
]

# Signal confidence scaling for contract size
# Example: If confidence is 0.85-0.90, use 0.5 * max_contracts; if 0.90+, use 1.0 * max_contracts
# Format: (Min Confidence, Multiplier)
CONFIDENCE_SCALING_METHOD = [
    (0.0, 0.0), # Default to 0 contracts if confidence below MIN_CONFIDENCE_THRESHOLD (handled by strategy_engine)
    (MIN_CONFIDENCE_THRESHOLD, 0.5), # 0.85 to (next tier min), use 0.5x contracts
    (0.90, 1.0) # 0.90+, use 1.0x contracts (can be adjusted for finer control)
]

# Default max concurrent trades for live trading (only 1 for now for simplicity)
MAX_CONCURRENT_LIVE_TRADES = 1

# NEW: Flag to indicate if default settings have been written to settings.json
# This helps in initial setup to ensure a settings file is created on first run.
DEFAULT_SETTINGS_INITIALIZED = False