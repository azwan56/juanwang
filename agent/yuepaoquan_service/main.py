from .processor import normalize_activity
from .storage import DatabaseConnector
from .wecom_service import WeComService
from .feedback import generate_feedback
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy-initialized singletons — no connections opened at import time
_db_connector = None
_wecom_service = None


def _get_db():
    global _db_connector
    if _db_connector is None:
        _db_connector = DatabaseConnector()
    return _db_connector


def _get_wecom():
    global _wecom_service
    if _wecom_service is None:
        _wecom_service = WeComService()
    return _wecom_service


def cloud_function_handler(event, context):
    """
    Main entry point for YuePaoQuan ingestion Cloud Function.
    """
    logger.info("Received request")

    try:
        # Parse event payload
        data = event if isinstance(event, dict) else json.loads(event)

        # Extract command keyword (e.g., from WeCom message text)
        command = data.pop("command", "")

        # Extract optional image path for OCR heart-rate extraction
        image_path = data.pop("image_path", None)

        # 1. Normalize (with optional OCR)
        normalized_data = normalize_activity(data, image_path=image_path)

        # 2. Save to database
        db = _get_db()
        result = db.save_activity(normalized_data)
        logger.info(f"Activity saved: {result.inserted_id}")

        # 3. Generate & send feedback
        feedback_text = generate_feedback(normalized_data, command=command)
        logger.info(f"Generated feedback: {feedback_text}")

        wecom = _get_wecom()
        send_result = wecom.send_feedback(feedback_text)
        logger.info(f"Feedback send result: {send_result}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "activity_id": str(result.inserted_id)
            })
        }
    except Exception as e:
        logger.error("Error processing request: %s", str(e), exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "message": str(e)})
        }
