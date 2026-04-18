import requests
import logging
from .config import Config

logger = logging.getLogger(__name__)


class WeComService:
    def __init__(self):
        self.webhook_url = Config.WECOM_WEBHOOK_URL
        if not self.webhook_url:
            logger.warning(
                "WECOM_WEBHOOK_URL is not set. "
                "Feedback sending will be disabled."
            )

    def send_feedback(self, text):
        """Sends feedback via WeCom Webhook."""
        if not self.webhook_url:
            logger.error("Cannot send feedback: WECOM_WEBHOOK_URL is not configured.")
            return False

        payload = {
            "msgtype": "text",
            "text": {"content": text}
        }
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            data = response.json()
            if data.get("errcode") != 0:
                logger.error(f"WeCom API error: {data}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending feedback: {e}")
            return False

    def poll_new_messages(self):
        """
        Polls for new messages.
        Note: True WeCom message reading requires 'App' mode (access_token),
        not Webhook. This mock demonstrates the polling structure.
        """
        logger.info("Polling for new images in chat...")
        # Implementation would use: GET https://qyapi.weixin.qq.com/cgi-bin/message/get_group_msg
        return []
