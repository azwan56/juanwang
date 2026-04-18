import logging
import json
from hermes_tools import vision_analyze

logger = logging.getLogger(__name__)

def extract_hr_from_image(image_path):
    """Uses vision AI to extract heart rate data from an image."""
    prompt = """Analyze this running activity screenshot from the YuePaoQuan app. Extract the following heart rate metrics precisely:
- 'Average Heart Rate' (average_hr): The mean heart rate value.
- 'Maximum Heart Rate' (max_hr): The peak heart rate value.
- If data is not clearly labeled, infer based on standard running summary layouts.
- Return ONLY valid JSON:
{
  "avg_hr": <number>,
  "max_hr": <number>
}
If a value is missing, set it to null."""
    
    result = vision_analyze(image_url=image_path, question=prompt)
    # Parse and return JSON data from result
    try:
        # Assuming the vision_analyze output can be parsed to JSON
        # Need to handle potential markdown formatting in output
        cleaned_result = result.replace('```json', '').replace('```', '').strip()
        return json.loads(cleaned_result)
    except Exception as e:
        logger.error(f"Failed to parse OCR result: {e}")
        return {"avg_hr": None, "max_hr": None}

def normalize_activity(raw_data, image_path=None):
    """
    Normalizes raw data from YuePaoQuan into the standard activity schema.
    If image_path is provided, performs OCR.
    """
    try:
        hr_data = {"avg_hr": raw_data.get("avg_hr"), "max_hr": raw_data.get("max_hr")}
        if image_path:
            hr_data = extract_hr_from_image(image_path)
            
        normalized = {
            "user_id": raw_data.get("user_id"),
            "source": "yuepaoquan",
            "external_id": str(raw_data.get("id")),
            "timestamp": raw_data.get("start_time"),
            "distance_meters": float(raw_data.get("distance", 0)),
            "duration_seconds": int(raw_data.get("duration", 0)),
            "pace_avg": float(raw_data.get("avg_pace", 0)),
            "heart_rate_avg": float(hr_data.get("avg_hr") or 0),
            "heart_rate_max": float(hr_data.get("max_hr") or 0)
        }
        return normalized
    except Exception as e:
        logger.error(f"Normalization failed: {e}")
        raise ValueError("Invalid activity data format")
