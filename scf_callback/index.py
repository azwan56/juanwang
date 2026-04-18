"""
Tencent Cloud Function (SCF) handler for WeCom callback.

Handles:
1. URL verification (GET) — WeCom's handshake when saving callback config.
2. Message reception (POST) — Receiving encrypted messages from WeCom.
3. Image OCR + Feedback — Processing running data and replying.

Deploy to Tencent SCF (Hong Kong region) to bypass ICP filing requirements.
"""

import json
import logging
import os
import time
from xml.etree import ElementTree as ET

from wecom_crypto import WXBizMsgCrypt, WeComCryptoError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ──────────────────────────────────────────────
# Configuration from environment variables
# ──────────────────────────────────────────────
CORP_ID = os.getenv("WECOM_CORP_ID", "")
TOKEN = os.getenv("WECOM_TOKEN", "")
ENCODING_AES_KEY = os.getenv("WECOM_ENCODING_AES_KEY", "")
AGENT_ID = os.getenv("WECOM_AGENT_ID", "1000002")
CORP_SECRET = os.getenv("WECOM_CORP_SECRET", "")
WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "")

# Access token cache (persists across warm invocations)
_access_token_cache = {"token": "", "expires_at": 0}


def main_handler(event, context):
    """
    Tencent SCF entry point.
    Routes GET (verification) and POST (message) requests.
    """
    http_method = event.get("httpMethod", "GET")

    if http_method == "GET":
        return handle_verification(event)
    elif http_method == "POST":
        return handle_message(event)
    else:
        return _response(405, "Method Not Allowed")


# ──────────────────────────────────────────────
# 1. URL Verification (GET)
# ──────────────────────────────────────────────
def handle_verification(event):
    """
    WeCom sends GET with msg_signature, timestamp, nonce, echostr.
    We must decrypt echostr and return the plaintext.
    """
    query = event.get("queryString", {}) or {}
    msg_signature = query.get("msg_signature", "")
    timestamp = query.get("timestamp", "")
    nonce = query.get("nonce", "")
    echostr = query.get("echostr", "")

    logger.info(f"[Verify] msg_signature={msg_signature}, timestamp={timestamp}")

    try:
        crypt = WXBizMsgCrypt(
            token=TOKEN,
            encoding_aes_key=ENCODING_AES_KEY,
            receive_id=CORP_ID
        )
        plain_echostr = crypt.verify_url(msg_signature, timestamp, nonce, echostr)
        logger.info("[Verify] Success!")
        return _response(200, plain_echostr, content_type="text/plain")
    except WeComCryptoError as e:
        logger.error(f"[Verify] Failed: {e}")
        return _response(403, "Verification failed")
    except Exception as e:
        logger.error(f"[Verify] Unexpected error: {e}")
        return _response(500, "Internal error")


# ──────────────────────────────────────────────
# 2. Message Reception (POST)
# ──────────────────────────────────────────────
def handle_message(event):
    """
    WeCom POSTs encrypted XML. We decrypt, parse, and process.
    Must respond quickly (within 5 seconds) to avoid WeCom retry.
    """
    query = event.get("queryString", {}) or {}
    msg_signature = query.get("msg_signature", "")
    timestamp = query.get("timestamp", "")
    nonce = query.get("nonce", "")
    body = event.get("body", "")

    logger.info(f"[Message] Received callback, body length={len(body)}")

    try:
        crypt = WXBizMsgCrypt(
            token=TOKEN,
            encoding_aes_key=ENCODING_AES_KEY,
            receive_id=CORP_ID
        )

        # Extract <Encrypt> from XML body
        root = ET.fromstring(body)
        encrypt = root.findtext("Encrypt", default="")

        # Decrypt
        xml_content = crypt.decrypt(msg_signature, timestamp, nonce, encrypt)
        xml_text = xml_content.decode("utf-8")
        logger.info(f"[Message] Decrypted XML: {xml_text[:200]}")

        # Parse message
        msg_root = ET.fromstring(xml_text)
        msg_type = (msg_root.findtext("MsgType") or "").lower()
        from_user = msg_root.findtext("FromUserName", default="")
        content = msg_root.findtext("Content", default="").strip()
        pic_url = msg_root.findtext("PicUrl", default="")

        logger.info(f"[Message] type={msg_type}, from={from_user}, content={content[:50]}")

        # ── Process based on message type ──
        if msg_type == "text":
            # Text message — generate running feedback
            feedback = _generate_text_feedback(content, from_user)
            if feedback:
                _send_via_webhook(feedback)

        elif msg_type == "image":
            # Image message — OCR running data
            logger.info(f"[Message] Image received: {pic_url[:80]}")
            feedback = _process_running_image(pic_url, from_user)
            if feedback:
                _send_via_webhook(feedback)

        elif msg_type == "event":
            event_type = (msg_root.findtext("Event") or "").lower()
            logger.info(f"[Message] Event: {event_type}")

        # Must return "success" quickly
        return _response(200, "success", content_type="text/plain")

    except WeComCryptoError as e:
        logger.error(f"[Message] Crypto error: {e}")
        return _response(400, "Decryption failed")
    except Exception as e:
        logger.error(f"[Message] Error: {e}", exc_info=True)
        return _response(200, "success", content_type="text/plain")


# ──────────────────────────────────────────────
# 3. Business Logic
# ──────────────────────────────────────────────
def _generate_text_feedback(content, from_user):
    """
    Process text messages. If it contains running data keywords,
    generate feedback.
    """
    keywords = ["km", "公里", "跑了", "配速", "心率", "完赛"]
    if not any(kw in content for kw in keywords):
        return None

    # Extract numbers from text for basic analysis
    import re
    numbers = re.findall(r"(\d+\.?\d*)", content)

    if numbers:
        dist = float(numbers[0]) if numbers else 0
        if "教练" in content or "分析" in content:
            return (
                f"Coach Canova 点评：今天 {from_user} 跑了{dist}km，"
                f"不错的训练量！建议关注特定配速段落的质量，"
                f"追求高效训练而非单纯里程。💪"
            )
        return (
            f"🏃‍♂️ 闵文卷王点评：{from_user} 刚完成{dist}km！"
            f"保持这个节奏，家属杯冠军就是你的！👍👍👍"
        )
    return None


def _process_running_image(pic_url, from_user):
    """
    Process running screenshot image via OCR.
    For now returns a placeholder; integrate with vision API later.
    """
    # TODO: Integrate with vision_analyze OCR for heart rate extraction
    # from processor import extract_hr_from_image
    return (
        f"🏃‍♂️ 闵文卷王收到 {from_user} 的运动截图！"
        f"正在分析中...数据看起来很不错，继续加油！💪"
    )


def _send_via_webhook(text):
    """Send feedback to WeCom group via webhook."""
    if not WEBHOOK_URL:
        logger.warning("[Webhook] WECOM_WEBHOOK_URL not configured")
        return False

    import urllib.request
    payload = json.dumps({
        "msgtype": "text",
        "text": {"content": text}
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            if result.get("errcode") != 0:
                logger.error(f"[Webhook] Error: {result}")
                return False
            logger.info("[Webhook] Sent successfully")
            return True
    except Exception as e:
        logger.error(f"[Webhook] Failed: {e}")
        return False


# ──────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────
def _response(status_code, body, content_type="application/json"):
    """Format response for Tencent SCF API Gateway."""
    if content_type == "text/plain":
        return {
            "isBase64Encoded": False,
            "statusCode": status_code,
            "headers": {"Content-Type": "text/plain"},
            "body": body
        }
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": body}) if isinstance(body, str) else json.dumps(body)
    }
