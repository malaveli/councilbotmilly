# telegram_alert.py

import requests
import logging

logger = logging.getLogger(__name__)

class TelegramAlert:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        if not bot_token or not chat_id:
            logger.warning("TelegramAlert initialized but bot_token or chat_id is missing. Alerts will not be sent.")

    def send_message(self, text):
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram config missing (bot_token or chat_id). Cannot send alert.")
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML" # Use HTML for basic formatting
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            logger.info("✅ Telegram alert sent.")
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Telegram HTTP error: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Telegram connection error: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"❌ Telegram timeout error: {e}")
        except requests.RequestException as e:
            logger.error(f"❌ Telegram error: {e}")
