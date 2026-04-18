"""
Tencent Cloud Function (SCF) as a PURE REVERSE PROXY for WeCom callbacks.

Since Hermes Agent already natively implements decryption, queueing, and WeCom APIs 
in `gateway/platforms/wecom_callback.py` (which immediately returns 'success' 
to prevent WeCom timeouts), this SCF only needs to blindly forward the raw 
GET and POST requests to the GCP VM. 

Deploy to Tencent SCF (Hong Kong region) to bypass ICP filing requirements.
"""

import os
import logging
import urllib.request
import urllib.parse
from wecom_crypto import WeComCryptoError  # Keeping import mostly to satisfy deps if any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Your GCP VM Hermes API endpoint
# e.g. http://34.120.x.x:8645/wecom/callback
HERMES_AGENT_URL = os.getenv("HERMES_AGENT_URL", "")


def main_handler(event, context):
    http_method = event.get("httpMethod", "GET")
    query_string_obj = event.get("queryString", {}) or {}
    
    # 1. Rebuild query params
    query_string = urllib.parse.urlencode(query_string_obj)
    target_url = f"{HERMES_AGENT_URL}?{query_string}" if query_string else HERMES_AGENT_URL

    if not HERMES_AGENT_URL:
        logger.error("[Relay] HERMES_AGENT_URL is not configured!")
        return _response(500, "Hermes Agent URL not set in Tencent SCF Environment Variables")

    logger.info(f"[{http_method}] Proxying to: {HERMES_AGENT_URL}")

    # 2. Forward request
    try:
        if http_method == "GET":
            req = urllib.request.Request(target_url, method="GET")
        elif http_method == "POST":
            # For POST, we get the body (usually WeCom XML)
            body = event.get("body", "")
            req = urllib.request.Request(
                target_url,
                data=body.encode("utf-8") if isinstance(body, str) else body,
                headers={"Content-Type": "application/xml"},
                method="POST"
            )
        else:
            return _response(405, "Method Not Allowed")

        # Call the GCP VM
        with urllib.request.urlopen(req, timeout=4) as resp:
            status = resp.status
            response_body = resp.read().decode("utf-8")
            content_type = resp.headers.get("Content-Type", "text/plain")
            return _response(status, response_body, content_type)

    except urllib.error.HTTPError as e:
        logger.error(f"[Relay] HTTP Error {e.code}: {e.read().decode('utf-8')}")
        return _response(e.code, "Gateway relay failed")
    except Exception as e:
        logger.error(f"[Relay] Network/Timeout Error: {e}")
        # Return 200 "success" on POST timeouts to prevent WeCom retry loops, 
        # but 500 on GET since it's a manual validation step
        if http_method == "POST":
            return _response(200, "success", "text/plain")
        return _response(500, f"Gateway connection failed: {e}")


def _response(status_code, body, content_type="text/plain"):
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": {"Content-Type": content_type},
        "body": body
    }
