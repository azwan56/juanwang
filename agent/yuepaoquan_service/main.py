"""
YuePaoQuan 核心业务编排模块。
支持独立 server.py 和 Hermes 两种运行模式。

处理:
  - 「本月目标 X」命令：设定月度跑量目标
  - 「查询」/「我的数据」命令：查看本月进度
  - 图片消息：OCR 提取跑步数据并反馈
"""

from .storage import DatabaseConnector
from .processor import analyze_running_image
import logging
import os
import re
import asyncio
import datetime
import httpx

_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "")

async def broadcast_to_group(message: str) -> None:
    """通过群机器人 Webhook 广播消息到群。"""
    if not _WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(_WEBHOOK_URL, json={
                "msgtype": "text",
                "text": {"content": message}
            })
            logging.getLogger(__name__).info("[Broadcast] ✅ 已发送群播")
    except Exception as e:
        logging.getLogger(__name__).error("[Broadcast] 群播失败: %s", e)

logger = logging.getLogger(__name__)
_db = None

def get_db():
    global _db
    if _db is None:
        _db = DatabaseConnector()
    return _db

async def handle_incoming_wecom(adapter, event, app) -> bool:
    """
    主入口：处理来自企业微信的消息事件。
    adapter: 任何有 async send(chat_id, text) 方法的对象
    event:   有 source.user_id / source.chat_id / text / metadata / message_id 的对象
    返回 True 表示已处理，False 表示未处理（可继续往下路由）。
    """
    user_id = event.source.user_id
    text = event.text or ""
    metadata = getattr(event, "metadata", None) or {}
    
    # 1. Goal Setting Command
    # Flexible: matches "本月目标 300", "目标是300公里", "跑量目标300", "我这个月的跑量目标是300公里哦" etc.
    goal_match = re.search(r"目标[是为]?\s*(\d+\.?\d*)\s*(?:公里|km|K)?", text, re.IGNORECASE)
    if goal_match:
        target_km = float(goal_match.group(1))
        month = datetime.datetime.now().strftime("%Y-%m")
        db = get_db()
        db.save_monthly_goal(user_id, month, target_km)
        reply = (
            f"✅ 【卷王通报】立下军令状！\n"
            f"{user_id} 设定了 {month} 月终极目标：{target_km} km。\n"
            f"牛皮吹出去了，剩下的就是流汗了！"
        )
        await adapter.send(event.source.chat_id, reply)
        return True

    # 2. Query Command — 查看本月进度
    # Flexible: matches "查询", "进展如何", "到目前我的进展如何", "目前进度", "完成了多少" etc.
    if re.search(r"(查询|我的数据|我的进度|本月进度|跑了多少|进展|进度|完成了多少|跑了多远|目前.*多少|战报)", text):
        month = datetime.datetime.now().strftime("%Y-%m")
        db = get_db()
        stats = db.get_monthly_stats(user_id, month)
        if stats.get("target_km"):
            reply = (
                f"📊 【{user_id} 的 {month} 月战报】\n"
                f"━━━━━━━━━━━━━━\n"
                f"已跑：{stats['total_km']} km / 目标 {stats['target_km']} km\n"
                f"进度：{stats['progress_pct']}%\n"
                f"还差：{stats['remaining_km']} km\n"
                f"━━━━━━━━━━━━━━\n"
                f"{'🎉 已完成目标！继续卷！' if stats['progress_pct'] >= 100 else '💪 加油，别让自己后悔！'}"
            )
        else:
            reply = (
                f"📊 {month} 月你悄悄跑了 {stats['total_km']} km。\n"
                f"还没设目标？发「本月目标 100」试试！"
            )
        await adapter.send(event.source.chat_id, reply)
        return True

    # 3. Image Activity Processing
    pic_url = metadata.get("pic_url")
    if pic_url:
        # Prompt immediately so user knows it hasn't died
        await adapter.send(event.source.chat_id, f"👀 收到截图！闵文卷王正在拿起放大镜审视 {user_id} 的数据...")
        
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
        
        private_reply = "\n".join(lines)

        # 私信回复本人（详细版）
        await adapter.send(event.source.chat_id, private_reply)

        # 群播战报（简洁版公告）
        if stats.get("target_km"):
            progress_line = (
                f"本月进度：{stats['total_km']} km / {stats['target_km']} km "
                f"({stats['progress_pct']}%)"
            )
        else:
            progress_line = f"本月累计：{stats['total_km']} km"

        group_msg = (
            f"🏃 {user_id} 刚刚完成了一次跑步！\n"
            f"━━━━━━━━━━━━━━\n"
            f"📏 距离：{dist} km  ⚡ 配速：{pace} /km\n"
            f"📊 {progress_line}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💬 {data.get('summary', '再接再厉！')}"
        )
        await broadcast_to_group(group_msg)

        return True

    # Allow standard chat text routing in Hermes to proceed if not handled
    return False
