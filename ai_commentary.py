# ai_commentary.py

from datetime import datetime

class AICommentary:
    def __init__(self):
        self.messages = []
        self.max_messages = 100

    def generate_signal_comment(self, signal, confidence, reason):
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        comment = f"[{timestamp}] Signal: {signal} | Confidence: {confidence:.2f} | Reason: {reason}"
        self._log_message(comment)
        return comment

    def generate_trade_warning(self, trade, current_price):
        direction = "Long" if trade["direction"] == 1 else "Short"
        move = current_price - trade["entry_price"]
        ticks = round(abs(move) / 0.25)

        if (direction == "Long" and move < 0) or (direction == "Short" and move > 0):
            if ticks >= 4:
                comment = f"⚠️ Warning: {direction} trade under pressure, {ticks} ticks against position."
                self._log_message(comment)
                return comment

        return None

    def _log_message(self, msg):
        self.messages.append(msg)
        if len(self.messages) > self.max_messages:
            self.messages.pop(0)

    def get_recent_comments(self):
        return self.messages[-10:]
