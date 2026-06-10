# Manual Chat Checks

Start the API:

```bash
uvicorn app:app --reload
```

Run these requests:

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"printer not working"}'

curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"create purchase request for 10 laptops"}'

curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"check server status"}'

curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"suspicious login detected"}'
```

Each response should include:

```json
{
  "classifier_source": "gemini",
  "classifier_error": null
}
```

If Gemini quota or configuration fails, the request should still return HTTP 200
with:

```json
{
  "intent": "classification_failed",
  "selected_agent": "general_agent",
  "confidence": 0.0,
  "requires_approval": false,
  "classifier_source": "gemini_failed",
  "classifier_error": "actual error message"
}
```
