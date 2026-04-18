# OCR Data Structure for YuePaoQuan Heart Rate

The OCR service is expected to return a JSON payload representing the extracted heart rate data from running activity images.

## Payload Structure

```json
{
  "avg_hr": <float>,
  "max_hr": <float>
}
```

- `avg_hr`: Average heart rate recorded during the activity.
- `max_hr`: Maximum heart rate recorded during the activity.
