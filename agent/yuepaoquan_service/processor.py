"""
Vision AI OCR processing logic using Zhipu or Gemini parameters.
"""

import os
import json
import base64
import urllib.request
import logging

logger = logging.getLogger(__name__)

# Use the same env vars the user configured for scf previously
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
AI_MODEL = os.getenv("AI_MODEL", "glm-4v-plus")

def _download_image_as_base64(image_url):
    logger.info(f"[Processor] Downloading image: {image_url}")
    try:
        req = urllib.request.Request(image_url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            image_data = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            b64 = base64.b64encode(image_data).decode("utf-8")
            return f"data:{content_type};base64,{b64}"
    except Exception as e:
        logger.error(f"[Processor] Download failed: {e}")
        return None

def analyze_running_image(pic_url: str) -> dict:
    """Download the image from PicUrl, run it through AI, and return structured dict."""
    if not AI_API_KEY:
        logger.warning("[Processor] AI_API_KEY not set. OCR disabled.")
        return {}

    b64_data = _download_image_as_base64(pic_url)
    if not b64_data:
        return {}

    prompt = """请作为专业且精准的 OCR 数据提取工具，仔细分析这张跑步成绩截图。
请提取出以下核心数据（以数字形式返回）。如果某项数据在图片中找不到，设为 null。

必须使用如下 JSON 格式返回结果（并且只返回这段 JSON，不要包含任何前后说明文字、不需要 Markdown 标记）：
{
  "distance_km": <距离，如果是英里请换算为公里，保留小数点后两位>,
  "duration": "<用时，形如 '01:23:45' 字符串，必须带有冒号>",
  "avg_pace": "<平均配速，形如 '05:30' 字符串>",
  "avg_hr": <平均心率，整数，如无则null>,
  "max_hr": <最大心率，整数，如无则null>,
  "calories": <消耗卡路里，整数，如无则null>,
  "elevation": <爬升高度，米，整数，如无则null>,
  "cadence": <平均步频，整数，如无则null>,
  "summary": "<作为‘闵文卷王’（一个毒舌、爱搞事、极度内卷但又护短的跑步大佬魔头），结合上面提取的数据，给这位跑者写一段50-100字的辣评与鼓励。语气要很‘来事’、带点傲娇和调侃，让人看了既想笑又觉得被打鸡血了。>"
}"""

    payload = json.dumps({
        "model": AI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": b64_data}}
                ]
            }
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }).encode("utf-8")

    api_url = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_API_KEY}"
    }

    try:
        logger.info(f"[Processor] Sending request to {api_url} using model {AI_MODEL}")
        req = urllib.request.Request(api_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]
            # Clear markdown explicitly
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
    except Exception as e:
        logger.error(f"[Processor] Vision API Error: {e}")
        try:
            err_body = getattr(e, "read", lambda: b"")().decode()
            logger.error(f"[Processor] Body: {err_body}")
        except: pass
        return {}
