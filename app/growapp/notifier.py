import logging
import time

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends messages via the Telegram Bot API.

    Per-key cooldown stops a dry plant from spamming you every sample
    interval; watering confirmations are always sent.
    """

    def __init__(self, config):
        self.enabled = config["enabled"] and config["bot_token"] and config["chat_id"]
        self._token = config["bot_token"]
        self._chat_id = config["chat_id"]
        self._cooldown = config["alert_cooldown_minutes"] * 60
        self._last_sent = {}
        if config["enabled"] and not self.enabled:
            logger.warning("Telegram enabled but bot_token/chat_id missing - notifications off")

    def send(self, text, cooldown_key=None):
        if not self.enabled:
            return False

        now = time.time()
        if cooldown_key is not None:
            if now - self._last_sent.get(cooldown_key, 0) < self._cooldown:
                return False

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("Telegram send failed: %s", e)
            return False

        if cooldown_key is not None:
            self._last_sent[cooldown_key] = now
        return True
