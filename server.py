"""
YuePaoQuan WeCom Callback Server
独立运行的企业微信回调服务器，完全替代 Hermes Agent 框架。

用法:
    python server.py

环境变量（见 .env / .env.example）:
    WECOM_CORP_ID            企业ID
    WECOM_TOKEN              回调验证 Token
    WECOM_ENCODING_AES_KEY   消息加密 Key
    WECOM_CORP_SECRET        应用 Secret（用于发送消息）
    WECOM_AGENT_ID           应用 AgentID
    AI_API_KEY               智谱 GLM API Key
    AI_BASE_URL              AI API 地址（默认智谱）
    AI_MODEL                 模型名称（默认 glm-4v-plus）
    PORT                     监听端口（默认 8645）
"""

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from xml.etree import ElementTree as ET

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

try:
    from aiohttp import web
    import httpx
except ImportError:
    print("❌ 缺少依赖: pip install aiohttp httpx")
    sys.exit(1)

# Ensure project root is importable
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from wecom_crypto import WXBizMsgCrypt, WeComCryptoError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("yuepaoquan.server")

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

CORP_ID           = os.getenv("WECOM_CORP_ID", "")
TOKEN             = os.getenv("WECOM_TOKEN", "")
ENCODING_AES_KEY  = os.getenv("WECOM_ENCODING_AES_KEY", "")
CORP_SECRET       = os.getenv("WECOM_CORP_SECRET", "")
AGENT_ID          = int(os.getenv("WECOM_AGENT_ID", "0"))
PORT              = int(os.getenv("PORT", "8645"))
CALLBACK_PATH     = "/wecom/callback"
MESSAGE_DEDUP_TTL = 300  # seconds


def _check_config() -> bool:
    missing = []
    for name, val in [
        ("WECOM_CORP_ID", CORP_ID),
        ("WECOM_TOKEN", TOKEN),
        ("WECOM_ENCODING_AES_KEY", ENCODING_AES_KEY),
        ("WECOM_CORP_SECRET", CORP_SECRET),
        ("WECOM_AGENT_ID", AGENT_ID),
    ]:
        if not val:
            missing.append(name)
    if missing:
        logger.error("❌ 以下环境变量未配置: %s", ", ".join(missing))
        return False
    if not os.getenv("AI_API_KEY"):
        logger.warning("⚠️  AI_API_KEY 未配置，图片 OCR 功能将不可用")
    return True


# ──────────────────────────────────────────────
# Minimal event / adapter stubs
# (matches the interface expected by yuepaoquan_service/main.py)
# ──────────────────────────────────────────────

@dataclass
class EventSource:
    user_id: str
    chat_id: str
    user_name: str = ""
    chat_type: str = "dm"


@dataclass
class WeComEvent:
    text: str
    source: EventSource
    message_id: str
    metadata: Optional[Dict[str, Any]] = None


class WeComAdapter:
    """Thin adapter: send proactive messages via WeCom API."""

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client
        self._token_cache: Dict[str, Any] = {}

    async def send(self, chat_id: str, content: str, **_) -> bool:
        """Send a text message to a WeCom user.
        
        chat_id format: "corp_id:user_id" (or bare user_id).
        """
        touser = chat_id.split(":", 1)[1] if ":" in chat_id else chat_id
        try:
            token = await self._get_access_token()
            payload = {
                "touser": touser,
                "msgtype": "text",
                "agentid": AGENT_ID,
                "text": {"content": content[:2048]},
                "safe": 0,
            }
            resp = await self._client.post(
                f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if data.get("errcode") != 0:
                logger.error("[Send] WeCom API error: %s", data)
                return False
            logger.info("[Send] ✅ Sent to %s", touser)
            return True
        except Exception as exc:
            logger.exception("[Send] Failed: %s", exc)
            return False

    async def _get_access_token(self) -> str:
        now = time.time()
        cached = self._token_cache
        if cached.get("expires_at", 0) > now + 60:
            return cached["token"]
        return await self._refresh_access_token()

    async def _refresh_access_token(self) -> str:
        resp = await self._client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": CORP_ID, "corpsecret": CORP_SECRET},
            timeout=10,
        )
        data = resp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"Token refresh failed: {data}")
        token = data["access_token"]
        expires_in = int(data.get("expires_in", 7200))
        self._token_cache = {"token": token, "expires_at": time.time() + expires_in}
        logger.info("[Token] ✅ Refreshed, expires in %ds", expires_in)
        return token


# ──────────────────────────────────────────────
# XML Parsing
# ──────────────────────────────────────────────

def _parse_xml_event(xml_text: str) -> Optional[WeComEvent]:
    """Parse decrypted WeCom XML into a WeComEvent."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("[Parse] Invalid XML: %s", exc)
        return None

    msg_type = (root.findtext("MsgType") or "").lower()

    # Silently ignore lifecycle events
    if msg_type == "event":
        event_name = (root.findtext("Event") or "").lower()
        if event_name in {"enter_agent", "subscribe", "unsubscribe"}:
            logger.info("[Parse] Lifecycle event '%s', skipping", event_name)
            return None

    if msg_type not in {"text", "image", "event"}:
        logger.info("[Parse] Unsupported msg_type '%s', skipping", msg_type)
        return None

    user_id  = root.findtext("FromUserName", default="")
    corp_id  = root.findtext("ToUserName", default=CORP_ID)
    chat_id  = f"{corp_id}:{user_id}" if corp_id else user_id
    msg_id   = (
        root.findtext("MsgId")
        or f"{user_id}:{root.findtext('CreateTime', default='0')}"
    )

    metadata = None
    if msg_type == "image":
        pic_url = root.findtext("PicUrl", default="")
        content = f"[Image] {pic_url}"
        if pic_url:
            metadata = {"pic_url": pic_url}
    else:
        content = root.findtext("Content", default="").strip()
        if not content and msg_type == "event":
            content = "/start"

    source = EventSource(user_id=user_id, chat_id=chat_id, user_name=user_id)
    return WeComEvent(text=content, source=source, message_id=msg_id, metadata=metadata)


# ──────────────────────────────────────────────
# HTTP Request Handlers
# ──────────────────────────────────────────────

_crypt: Optional[WXBizMsgCrypt] = None
_adapter: Optional[WeComAdapter] = None
_seen_messages: Dict[str, float] = {}


def _get_crypt() -> WXBizMsgCrypt:
    global _crypt
    if _crypt is None:
        _crypt = WXBizMsgCrypt(
            token=TOKEN,
            encoding_aes_key=ENCODING_AES_KEY,
            receive_id=CORP_ID,
        )
    return _crypt


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "service": "yuepaoquan-wecom",
        "corp_id": CORP_ID[:4] + "****" if CORP_ID else "",
    })


async def handle_verify(request: web.Request) -> web.Response:
    """GET /wecom/callback — WeCom URL 验证握手"""
    try:
        plain = _get_crypt().verify_url(
            msg_signature=request.query.get("msg_signature", ""),
            timestamp=request.query.get("timestamp", ""),
            nonce=request.query.get("nonce", ""),
            echostr=request.query.get("echostr", ""),
        )
        logger.info("[Verify] ✅ URL verification success")
        return web.Response(text=plain, content_type="text/plain")
    except WeComCryptoError as exc:
        logger.error("[Verify] ❌ Signature error: %s", exc)
        return web.Response(status=403, text="signature verification failed")


async def handle_callback(request: web.Request) -> web.Response:
    """POST /wecom/callback — 接收加密消息"""
    # Always acknowledge immediately to prevent WeCom retry loops
    body = await request.text()
    params = request.query

    asyncio.create_task(_process_message(body, params))
    return web.Response(text="success", content_type="text/plain")


async def _process_message(body: str, params) -> None:
    """Process a WeCom callback in the background."""
    try:
        # 1. Decrypt
        root = ET.fromstring(body)
        encrypt = root.findtext("Encrypt", default="")
        decrypted = _get_crypt().decrypt(
            msg_signature=params.get("msg_signature", ""),
            timestamp=params.get("timestamp", ""),
            nonce=params.get("nonce", ""),
            encrypt=encrypt,
        ).decode("utf-8")

        # 2. Parse
        event = _parse_xml_event(decrypted)
        if event is None:
            return

        # 3. Dedup
        now = time.time()
        _seen_messages.update({k: v for k, v in _seen_messages.items() if now - v < MESSAGE_DEDUP_TTL})
        if event.message_id in _seen_messages:
            logger.info("[Dedup] Already processed %s, skipping", event.message_id)
            return
        _seen_messages[event.message_id] = now

        logger.info(
            "[Recv] user=%s type=%s text=%.60s",
            event.source.user_id,
            "image" if event.metadata else "text",
            event.text,
        )

        # 4. Dispatch to YuePaoQuan service
        from agent.yuepaoquan_service.main import handle_incoming_wecom
        await handle_incoming_wecom(_adapter, event, {})

    except WeComCryptoError as exc:
        logger.error("[Callback] Crypto error: %s", exc)
    except Exception:
        logger.exception("[Callback] Unexpected error processing message")


# ──────────────────────────────────────────────
# Server lifecycle
# ──────────────────────────────────────────────

async def create_app() -> web.Application:
    global _adapter

    http_client = httpx.AsyncClient(timeout=20.0)
    _adapter = WeComAdapter(http_client)

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get(CALLBACK_PATH, handle_verify)
    app.router.add_post(CALLBACK_PATH, handle_callback)

    # Pre-warm access token
    try:
        await _adapter._refresh_access_token()
    except Exception as exc:
        logger.warning("[Startup] Token pre-warm failed (will retry on first send): %s", exc)

    async def on_shutdown(app):
        await http_client.aclose()

    app.on_shutdown.append(on_shutdown)
    return app


def main():
    if not _check_config():
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("  🏃 YuePaoQuan WeCom Server")
    logger.info("  Corp: %s", CORP_ID[:4] + "****" if len(CORP_ID) > 4 else CORP_ID)
    logger.info("  Port: %d", PORT)
    logger.info("  Path: %s", CALLBACK_PATH)
    logger.info("=" * 60)

    web.run_app(create_app(), host="0.0.0.0", port=PORT, access_log=logger)


if __name__ == "__main__":
    main()
