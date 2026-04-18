from .config import Config
from .processor import normalize_activity
from .storage import DatabaseConnector
from .wecom_service import WeComService
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_connector = DatabaseConnector()
wecom_service = WeComService()

def cloud_function_handler(event, context):
    """
    Main entry point for YuePaoQuan ingestion Cloud Function.
    """
    logger.info("Received request")
    
    try:
        # Assuming event is a dict or string representing JSON body
        data = event if isinstance(event, dict) else json.loads(event)
        
        # 1. Normalize
        normalized_data = normalize_activity(data)
        
        # 2. Save
        result = db_connector.save_activity(normalized_data)
        logger.info(f"Activity saved: {result.inserted_id}")
        
        # 3. Trigger Feedback (Dual Mode)
        def _get_feedback(data, command=""):
            avg = data.get('heart_rate_avg', 0)
            max_hr = data.get('heart_rate_max', 0)
            dist = data.get('distance_meters', 0) / 1000
            pace = data.get('pace_avg', 0)

            # Coach Canova Mode
            if "教练" in command or "分析" in command:
                if pace < 5.0: # 目标配速设定
                    return f"Coach Canova 点评：特定配速 {pace}min/km 保持得不错！在 {dist}km 距离下，你的代谢适应正在增强。注意核心姿态，这是高质量训练。💪"
                return f"Coach Canova 点评：今天进行了{dist}km的训练。平均心率 {avg}，处于有效代谢区间。建议在下一次长距离跑中增加特定配速的段落，追求质量而非单纯里程。"

            # JuanWang Mode (Default)
            if avg > 145:
                return f"🏃‍♂️ 闵文卷王提醒：刚才这次{dist:.1f}km跑得很拼啊！平均心率 {avg}，最大 {max_hr}，这强度有点高了，注意身体恢复，别让家属担心！😸"
            elif avg > 0:
                return f"🏃‍♂️ 闵文卷王点评：{dist:.1f}km 跑得非常稳！平均心率 {avg}，最大 {max_hr}，这节奏控制很成熟。基础扎实，继续保持，家属杯预热中！👍👍👍"
            return f"🏃‍♂️ 闵文卷王收到记录：{dist:.1f}km 完成！今天的状态很不错，继续加油！"

        feedback_text = _get_feedback(normalized_data, command="") 
        logger.info(f"Attempting to send feedback: {feedback_text}")
        send_result = wecom_service.send_feedback(feedback_text)
        logger.info(f"Feedback send result: {send_result}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "success", "activity_id": str(result.inserted_id)})
        }
    except Exception as e:
        logger.error("Error processing request: %s", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "message": str(e)})
        }
