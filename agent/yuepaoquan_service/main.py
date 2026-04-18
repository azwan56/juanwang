"""
Core Orchestration for YuePaoQuan Service via Hermes.
Intercepts Webhook payload directly from WeCom callback adapter.
"""

from .storage import DatabaseConnector
from .processor import analyze_running_image
import logging
import re
import asyncio
import datetime

logger = logging.getLogger(__name__)
_db = None

def get_db():
    global _db
    if _db is None:
        _db = DatabaseConnector()
    return _db

async def handle_incoming_wecom(adapter, event, app) -> bool:
    """
    Hook called tightly from wecom_callback.py.
    Returns True if handled (do not forward to Hermes standard agent), else False.
    """
    user_id = event.source.user_id
    text = event.text or ""
    metadata = getattr(event, "metadata", None) or {}
    
    # 1. Goal Setting Command Handling
    goal_match = re.search(r"本月目标\s*(\d+\.?\d*)", text)
    if goal_match:
        target_km = float(goal_match.group(1))
        month = datetime.datetime.now().strftime("%Y-%m")
        db = get_db()
        db.save_monthly_goal(user_id, month, target_km)
        
        reply = f"✅ 【卷王通报】立下军令状！\n{user_id} 设定了 {month} 月终极目标：{target_km} km。\n牛皮吹出去了，剩下的就是流汗了！"
        await adapter.send(event.source.chat_id, reply)
        return True
        
    # 2. Image Activity Processing
    pic_url = metadata.get("pic_url")
    if pic_url:
        # Prompt immediately so user knows it hasn't died
        await adapter.send(event.source.chat_id, f"👀 收到截图！敏文卷王正在拿起放大镜审视 {user_id} 的数据...")
        
        # Async run the blocking OCR
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, analyze_running_image, pic_url)
        except Exception as e:
            logger.error(f"[Main] OCR execution failed: {e}")
            await adapter.send(event.source.chat_id, f"❌ 读取截图失败了，图片里可能没有跑步数据？")
            return True
            
        if not data or "distance_km" not in data:
            await adapter.send(event.source.chat_id, f"❌ 没看明白这张图，或者 API 配置有误没提取到数据，换一张符合规范的手表截图试试？")
            return True
            
        # Clean user input data
        data["user_id"] = user_id
        # Use message_id as unique msg id
        data["msg_id"] = event.message_id
        
        db = get_db()
        try:
            db.save_activity(data)
        except Exception as e:
            logger.error(f"[Main] Database save failed: {e}")
            
        # Fetch Stats
        month = datetime.datetime.now().strftime("%Y-%m")
        stats = db.get_monthly_stats(user_id, month)
        
        # Build Feedback Output
        dist = data.get("distance_km")
        pace = data.get("avg_pace", "—")
        hr = data.get("avg_hr") or "—"
        
        lines = [
            f"🏆 【闵文卷王认证】档案解密",
            f"━━━━━━━━━━━━━━",
            f"⏱️ 本次跑步距离：{dist} km",
            f"⚡ 平均配速：{pace} /km",
            f"❤️ 平均心率：{hr} bpm",
            f"━━━━━━━━━━━━━━"
        ]
        
        if stats.get("target_km"):
            lines.append(f"📊 本月累计：跑了 {stats['total_km']} km / 目标 {stats['target_km']} km")
            lines.append(f"🔥 当月进度：[{stats['progress_pct']}%] 距离目标还差 {stats['remaining_km']} km！")
        else:
            lines.append(f"📊 本月累计：悄悄地卷了 {stats['total_km']} km。")
            lines.append(f"👉 你还没有设目标！快在群里喊『本月目标 100』试试！")
            
        lines.append(f"━━━━━━━━━━━━━━")
        lines.append("🔥 卷王辣评：")
        lines.append(data.get("summary", "再接再厉，卷死他们！"))
        
        # Send Back to User/Group
        await adapter.send(event.source.chat_id, "\n".join(lines))
        return True

    # Allow standard chat text routing in Hermes to proceed if not handled
    return False
