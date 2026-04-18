# YuePaoQuan Integration Data Architecture

## 1. Overview
The system will ingest running activity data from YuePaoQuan and store it in a cloud-native database to facilitate agentic analysis and personalized feedback.

## 2. Data Flow
1. **Ingestion**: YuePaoQuan -> OAuth2/API or Webhook -> Data Ingestion Service.
   - *Strategy*: Use authorized API if available; fallback to user-initiated manual export/upload or automated OCR/scraping if official API is restricted.
2. **Processing**: Normalization & Validation -> Enrichment (e.g., weather data, elevation).
3. **Storage**: Cloud-native NoSQL (Tencent CloudBase).
4. **Agentic Layer**: LLM/Processing service accesses normalized data for analysis.

## 3. Database Schema (Tencent CloudBase / MongoDB)

### Collection: `activities`
```json
{
  "_id": "uuid",
  "user_id": "string",
  "source": "yuepaoquan",
  "external_id": "string",
  "timestamp": "iso8601",
  "distance_meters": "float",
  "duration_seconds": "int",
  "pace_avg": "float",
  "calories": "int",
  "gps_path": ["array of [lat, lon]"],
  "heart_rate_data": "json_blob",
  "metadata": {
    "weather": "string",
    "shoe_id": "string"
  }
}
```

## 4. API Integration Strategy
- **Primary**: YuePaoQuan official OpenAPI (request access via developer platform).
- **Secondary (If API restricted)**: 
    - User provides daily activity summary via screenshot (OCR processing).
    - OAuth2 integration with common platforms if synced to YuePaoQuan.

## 5. Agentic Processing
- **Input**: Raw `activities` records.
- **Processing**:
    - Aggregation: Weekly mileage trends, pace progression.
    - Analysis: Identifying injury risk, goal alignment, performance plateaus.
    - Feedback: Generated via LLM based on extracted metrics.
