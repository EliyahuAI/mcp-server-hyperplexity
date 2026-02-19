# Hyperplexity External API Reference

**Version:** v1
**Base URL:** `https://api.hyperplexity.ai/v1`
**Last updated:** 2026-02-18

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Authentication](#authentication)
3. [Standard Response Format](#standard-response-format)
4. [Rate Limiting](#rate-limiting)
5. [Endpoints](#endpoints)
   - [POST /v1/uploads/presigned](#post-v1uploadspresigned)
   - [POST /v1/jobs](#post-v1jobs)
   - [GET /v1/jobs/{job_id}](#get-v1jobsjob_id)
   - [POST /v1/jobs/{job_id}/validate](#post-v1jobsjob_idvalidate)
   - [GET /v1/jobs/{job_id}/results](#get-v1jobsjob_idresults)
   - [GET /v1/account/balance](#get-v1accountbalance)
   - [GET /v1/account/usage](#get-v1accountusage)
6. [WebSocket (Real-time Progress)](#websocket-real-time-progress)
7. [Webhooks](#webhooks)
8. [Error Reference](#error-reference)
9. [Code Examples](#code-examples)
   - [Python SDK Example](#python-sdk-example)
   - [JavaScript Example](#javascript-example)
   - [curl Quickstart](#curl-quickstart)
10. [Config Schema Reference](#config-schema-reference)

---

## Getting Started

Hyperplexity is a **validation-as-a-service** platform. You upload a spreadsheet, provide a validation configuration, and the API validates each row using AI — returning a results file with per-cell verdicts and confidence scores.

### How it works

The validation workflow has two stages:

1. **Preview** — validates a small sample of rows (1–10) so you can verify the configuration is correct and see an estimated cost before committing.
2. **Full validation** — after you approve the estimated cost, the entire file is validated asynchronously.

Both stages are asynchronous. You submit a job and poll for status (or use WebSockets / webhooks for push notifications).

### Prerequisites

- An active Hyperplexity account with a positive credit balance.
- An API key. Generate one from your [account page](https://app.hyperplexity.ai/account).

### Quick start (curl)

```bash
# 1. Request a presigned upload URL
curl -X POST https://api.hyperplexity.ai/v1/uploads/presigned \
  -H "Authorization: Bearer hpx_live_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"filename":"companies.xlsx","file_size":204800,"file_type":"excel"}'

# 2. Upload your file directly to S3 (use the presigned_url from step 1)
curl -X PUT "PRESIGNED_URL_FROM_STEP_1" \
  -H "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  --data-binary @companies.xlsx

# 3. Create a validation job (use session_id and s3_key from step 1)
curl -X POST https://api.hyperplexity.ai/v1/jobs \
  -H "Authorization: Bearer hpx_live_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SESSION_ID_FROM_STEP_1",
    "s3_key": "S3_KEY_FROM_STEP_1",
    "config": {
      "tables": [{
        "name": "Companies",
        "columns": {
          "Company Name": {"validation_type": "text", "required": true},
          "Website": {"validation_type": "url", "required": false}
        }
      }]
    },
    "preview_rows": 3
  }'

# 4. Poll for status
curl https://api.hyperplexity.ai/v1/jobs/JOB_ID \
  -H "Authorization: Bearer hpx_live_YOUR_KEY_HERE"
```

---

## Authentication

All endpoints require an API key passed as a **Bearer token** in the `Authorization` header:

```
Authorization: Bearer hpx_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
```

### Getting an API key

Log in at `https://app.hyperplexity.ai/account`, navigate to the **API Keys** section, and click **+ New API Key**. The raw key is displayed exactly once — copy it immediately. After you close the dialog, only the display prefix (`hpx_live_a1b2c3d4...`) is shown.

### Key format

```
hpx_{tier}_{40 url-safe characters}
```

| Tier | Prefix | Purpose |
|------|--------|---------|
| `live` | `hpx_live_` | Production — uses real credits |
| `test` | `hpx_test_` | Sandbox — restricted rate limits, for testing |
| `int` | `hpx_int_` | Internal — elevated limits, Hyperplexity staff only |

Examples:
```
hpx_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
hpx_test_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
```

### Key security

- Raw keys are **never stored** — only an HMAC-SHA256 hash is kept in the database.
- If you lose a key, revoke it and generate a new one from the account page.
- Keys can optionally be scoped and IP-whitelisted.

---

## Standard Response Format

Every response from the API is wrapped in the same envelope:

### Success envelope

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "request_id": "req_4a7f1b2c3d8e",
    "timestamp": "2026-02-18T10:30:00Z",
    "api_version": "v1"
  }
}
```

### Error envelope

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "insufficient_credits",
    "message": "Account balance is $0.00. Please add credits.",
    "details": {
      "current_balance": 0.00,
      "required_balance": 2.00
    }
  },
  "meta": {
    "request_id": "req_4a7f1b2c3d8e",
    "timestamp": "2026-02-18T10:30:00Z",
    "api_version": "v1"
  }
}
```

`details` is only present on some error codes (see [Error Reference](#error-reference)).

### HTTP status codes

| Code | Meaning | When used |
|------|---------|-----------|
| `200` | OK | Successful GET; job status responses regardless of job state |
| `201` | Created | Resource created (reserved for future use) |
| `202` | Accepted | Job successfully queued for async processing |
| `400` | Bad Request | Missing or invalid request fields |
| `401` | Unauthorized | Missing, invalid, revoked, or expired API key |
| `402` | Payment Required | Insufficient account credits |
| `403` | Forbidden | API key lacks permission for this operation |
| `404` | Not Found | Unknown endpoint, job not found, or results not ready |
| `409` | Conflict | Job already queued; preview not complete; cost mismatch |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected server error — include `request_id` in support tickets |

---

## Rate Limiting

Rate limits are enforced per API key using a **sliding window** — separate counters for requests per minute (RPM) and requests per day (RPD).

### Per-key limits

| Tier | Requests / minute | Requests / day | Notes |
|------|-------------------|----------------|-------|
| `live` | 60 | 1,000 | Standard |
| `test` | 10 | 100 | Intentionally restricted |
| `int` | 600 | unlimited | Hyperplexity internal only |

### Rate limit headers

Every response includes these headers regardless of whether the request was allowed:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Your RPM limit |
| `X-RateLimit-Remaining` | Requests remaining in the current minute window |
| `X-RateLimit-Reset` | ISO 8601 timestamp when the current minute window resets |

### 429 response example

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 2026-02-18T10:31:00Z
Content-Type: application/json

{
  "success": false,
  "data": null,
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Too many requests. Rate limit: 60/min."
  },
  "meta": {
    "request_id": "req_4a7f1b2c3d8e",
    "timestamp": "2026-02-18T10:30:45Z",
    "api_version": "v1"
  }
}
```

When rate-limited, wait until `X-RateLimit-Reset` before retrying. The `Retry-After` header provides the same information in seconds.

---

## Endpoints

### POST /v1/uploads/presigned

Request a presigned S3 URL to upload a file directly from your client to S3. This bypasses the API Gateway payload size limit — files up to 50 MB are supported.

**Two-step upload flow:**
1. Call this endpoint to get a `presigned_url` and associated identifiers.
2. `PUT` your file body directly to the `presigned_url` — no API key required for the S3 step.

#### Request

```http
POST /v1/uploads/presigned
Authorization: Bearer hpx_live_...
Content-Type: application/json
```

```json
{
  "filename": "companies.xlsx",
  "file_size": 2048000,
  "file_type": "excel"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | Yes | Original filename including extension |
| `file_size` | integer | Yes | File size in bytes (1 – 52,428,800) |
| `file_type` | string | Yes | `"excel"` (`.xlsx`, `.xls`) or `"pdf"` |
| `session_id` | string | No | Existing session ID to reuse; generated if omitted |

#### Response — 200 OK

```json
{
  "success": true,
  "data": {
    "presigned_url": "https://s3.amazonaws.com/hyperplexity-storage/results/example.com/user/session_20260218_103045_abc12345/upload_def456789012_companies.xlsx?...",
    "upload_id": "upload_def456789012",
    "s3_key": "results/example.com/user/session_20260218_103045_abc12345/upload_def456789012_companies.xlsx",
    "session_id": "session_20260218_103045_abc12345",
    "file_type": "excel",
    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "expires_in": 300
  },
  "error": null,
  "meta": { ... }
}
```

| Field | Description |
|-------|-------------|
| `presigned_url` | Temporary S3 PUT URL. Valid for `expires_in` seconds (300 s / 5 min). |
| `upload_id` | Unique identifier for this upload. |
| `s3_key` | S3 object key — pass this to `POST /v1/jobs`. |
| `session_id` | Session identifier — pass this to `POST /v1/jobs`. |
| `content_type` | MIME type inferred from the filename extension. Use this as the `Content-Type` header when uploading to S3. |
| `expires_in` | Seconds until the presigned URL expires. |

#### Uploading to S3

```bash
curl -X PUT "PRESIGNED_URL" \
  -H "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  --data-binary @companies.xlsx
```

The S3 PUT must succeed (HTTP 200) before you create a job. Do not include the `Authorization` header when uploading to S3 — the presigned URL carries its own credentials.

---

### POST /v1/jobs

Create a validation job. The job starts with a **preview** of `preview_rows` rows. When the preview completes you will review the cost estimate and approve (or reject) the full run via `POST /v1/jobs/{job_id}/validate`.

Returns `202 Accepted` immediately — processing is asynchronous.

#### Request

```http
POST /v1/jobs
Authorization: Bearer hpx_live_...
Content-Type: application/json
```

```json
{
  "session_id": "session_20260218_103045_abc12345",
  "s3_key": "results/example.com/user/session_20260218_103045_abc12345/upload_def456789012_companies.xlsx",
  "config": {
    "tables": [
      {
        "name": "Companies",
        "columns": {
          "Company Name": { "validation_type": "text", "required": true },
          "Website":      { "validation_type": "url",  "required": false }
        }
      }
    ]
  },
  "preview_rows": 3,
  "webhook_url": "https://your-app.com/webhooks/hyperplexity",
  "webhook_secret": "your_webhook_secret_123",
  "notify_method": "both"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | **Yes** | From the presigned URL response. May be passed with or without the `session_` prefix — it is normalized automatically. |
| `s3_key` | string | No | From the presigned URL response. If omitted, the session's previously uploaded file is used. |
| `config` | object | No | Validation configuration JSON (see [Config Schema Reference](#config-schema-reference)). If omitted, a previously stored config for the session is used. |
| `preview_rows` | integer | No | Number of rows to validate in the preview phase. Default: `3`. Range: `1`–`10`. |
| `webhook_url` | string | No | HTTPS URL to POST completion notifications. Must be a public HTTPS endpoint. |
| `webhook_secret` | string | No | Secret used to sign webhook payloads with HMAC-SHA256. |
| `notify_method` | string | No | `"poll"` (default), `"webhook"`, `"email"`, or `"both"` (`webhook` + `email`). |

#### Response — 202 Accepted

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "queued",
    "run_type": "preview",
    "created_at": "2026-02-18T10:30:45Z",
    "urls": {
      "status":  "/v1/jobs/session_20260218_103045_abc12345",
      "results": "/v1/jobs/session_20260218_103045_abc12345/results"
    },
    "polling": {
      "recommended_interval_seconds": 10,
      "max_wait_seconds": 1800
    }
  },
  "error": null,
  "meta": { ... }
}
```

Poll `urls.status` every `recommended_interval_seconds` (10 s) until `status` is `preview_complete` or `failed`.

---

### GET /v1/jobs/{job_id}

Retrieve the current status and progress of a job.

```http
GET /v1/jobs/{job_id}
Authorization: Bearer hpx_live_...
```

Returns `200 OK` for all states including `failed`. The `status` field indicates the current state.

#### Job status values

| Status | Description |
|--------|-------------|
| `queued` | Job accepted; waiting for a worker |
| `processing` | Actively validating rows |
| `preview_complete` | Preview done; cost estimate available; awaiting your approval |
| `completed` | Full validation complete; results available for download |
| `failed` | Job failed; see `current_step` for the error message |

When status is `processing`, the response includes the header:
```
Retry-After: 10
```

#### Response — queued

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "queued",
    "progress_percent": 0,
    "current_step": "Waiting in queue",
    "submitted_at": "2026-02-18T10:30:45Z"
  },
  "error": null,
  "meta": { ... }
}
```

#### Response — processing

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "processing",
    "progress_percent": 67,
    "current_step": "Validating row 2 of 3",
    "submitted_at": "2026-02-18T10:30:45Z"
  },
  "error": null,
  "meta": { ... }
}
```

#### Response — preview_complete

When the preview phase finishes, the status becomes `preview_complete`. At this point you must review the cost estimate and call `POST /v1/jobs/{job_id}/validate` to proceed.

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "preview_complete",
    "progress_percent": 100,
    "current_step": "Preview validation complete",
    "submitted_at": "2026-02-18T10:30:45Z"
  },
  "error": null,
  "meta": { ... }
}
```

> **Note:** The full cost estimate and preview sample results are surfaced through the underlying run record. Use the job status to detect `preview_complete` and then call `/validate` with `approved_cost_usd` set to the estimate shown in the Hyperplexity web UI, or a value retrieved from your own tracking of the quote.

#### Response — completed

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "completed",
    "progress_percent": 100,
    "current_step": null,
    "submitted_at": "2026-02-18T10:30:45Z"
  },
  "error": null,
  "meta": { ... }
}
```

Once `completed`, call `GET /v1/jobs/{job_id}/results` for the download URL.

#### Response — failed

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "failed",
    "progress_percent": 34,
    "current_step": "Invalid Excel file structure: sheet 'Companies' not found",
    "submitted_at": "2026-02-18T10:30:45Z"
  },
  "error": null,
  "meta": { ... }
}
```

---

### POST /v1/jobs/{job_id}/validate

Approve the full validation run after reviewing the preview. The `approved_cost_usd` value must match the cost estimate returned by the system — this prevents unexpected charges if the estimate changed between preview and approval.

Returns `202 Accepted` when the full run is queued.

#### Request

```http
POST /v1/jobs/{job_id}/validate
Authorization: Bearer hpx_live_...
Content-Type: application/json
```

```json
{
  "approved_cost_usd": 12.00,
  "webhook_url": "https://your-app.com/webhooks/hyperplexity",
  "webhook_secret": "your_webhook_secret_123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `approved_cost_usd` | number | No | The cost estimate you are approving. Recommended — protects against estimate drift. |
| `webhook_url` | string | No | Override or add a webhook URL for the full-run completion notification. |
| `webhook_secret` | string | No | HMAC-SHA256 secret for webhook signature verification. |

#### Response — 202 Accepted

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "queued",
    "run_type": "validation",
    "message": "Full validation queued successfully."
  },
  "error": null,
  "meta": { ... }
}
```

After approval, poll `GET /v1/jobs/{job_id}` until `status` is `completed` or `failed`.

#### Error — 409 Conflict: validation already queued

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "validation_already_queued",
    "message": "Full validation has already been queued for this job."
  },
  "meta": { ... }
}
```

#### Error — 409 Conflict: preview not complete

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "preview_not_complete",
    "message": "Preview is not yet complete. Current status: PROCESSING"
  },
  "meta": { ... }
}
```

#### Error — 402 Payment Required: insufficient credits

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "insufficient_credits",
    "message": "Insufficient account balance",
    "details": {
      "required_usd": 12.00,
      "current_balance_usd": 5.00,
      "shortfall_usd": 7.00
    }
  },
  "meta": { ... }
}
```

---

### GET /v1/jobs/{job_id}/results

Get the download URL for a completed validation job. Returns `404` if the job has not yet reached `completed` status.

```http
GET /v1/jobs/{job_id}/results
Authorization: Bearer hpx_live_...
```

#### Response — 200 OK (completed)

```json
{
  "success": true,
  "data": {
    "job_id": "session_20260218_103045_abc12345",
    "status": "completed",
    "results": {
      "download_url": "https://s3.amazonaws.com/hyperplexity-storage/results/...?X-Amz-Expires=3600&...",
      "download_expires_at": null,
      "file_format": "zip"
    },
    "summary": {
      "rows_processed": 450,
      "run_time_seconds": 863,
      "cost_usd": 11.73
    }
  },
  "error": null,
  "meta": { ... }
}
```

`download_url` is a temporary presigned S3 URL. Download your results promptly — the URL expires.

#### Error — 404: results not ready

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "results_not_ready",
    "message": "Validation results are not yet available.",
    "details": {
      "current_status": "processing",
      "progress_percent": 67,
      "status_url": "/v1/jobs/session_20260218_103045_abc12345"
    }
  },
  "meta": { ... }
}
```

#### Error — 404: job not found

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "job_not_found",
    "message": "No full validation job found. Submit a preview and approve it first."
  },
  "meta": { ... }
}
```

---

### GET /v1/account/balance

Return the current credit balance and recent transaction history for the authenticated account.

```http
GET /v1/account/balance
Authorization: Bearer hpx_live_...
```

#### Response — 200 OK

```json
{
  "success": true,
  "data": {
    "account_info": {
      "email": "you@example.com",
      "current_balance": 88.27,
      "email_domain": "example.com",
      "recent_transactions": [
        {
          "timestamp": "2026-02-18T10:46:23Z",
          "amount": -11.73,
          "balance_after": 88.27,
          "transaction_type": "debit",
          "description": "Validation job: session_20260218_103045_abc12345",
          "session_id": "session_20260218_103045_abc12345"
        },
        {
          "timestamp": "2026-02-15T14:20:00Z",
          "amount": 100.00,
          "balance_after": 100.00,
          "transaction_type": "credit",
          "description": "Account recharge via Squarespace",
          "session_id": null
        }
      ]
    },
    "message": "Account balance retrieved successfully"
  },
  "error": null,
  "meta": { ... }
}
```

| Field | Description |
|-------|-------------|
| `current_balance` | Account balance in USD |
| `recent_transactions` | Up to 10 most recent transactions |
| `transaction_type` | `"debit"` (charge for validation) or `"credit"` (account top-up) |
| `amount` | Transaction amount in USD. Negative for debits, positive for credits. |
| `balance_after` | Account balance after this transaction was applied |

---

### GET /v1/account/usage

Return paginated usage statistics for the authenticated account.

```http
GET /v1/account/usage?start_date=2026-02-01&end_date=2026-02-18&limit=10&offset=0
Authorization: Bearer hpx_live_...
```

#### Query parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_date` | string (ISO 8601 date) | 30 days ago | Filter transactions from this date (inclusive) |
| `end_date` | string (ISO 8601 date) | today | Filter transactions up to this date (inclusive) |
| `limit` | integer | `100` | Maximum records to return |
| `offset` | integer | `0` | Number of records to skip (for pagination) |

Both `limit` and `offset` must be integers; a `400` is returned if either is non-numeric.

#### Response — 200 OK

```json
{
  "success": true,
  "data": {
    "stats": { ... }
  },
  "error": null,
  "meta": { ... }
}
```

The `stats` object structure mirrors the data returned by the underlying `get_user_stats` function, which includes transaction history and aggregate spend for the requested date range.

---

## WebSocket (Real-time Progress)

Connect to the WebSocket endpoint to receive live progress events instead of polling.

### Connection

```
wss://api.hyperplexity.ai/v1/progress?job_id={job_id}&api_key={raw_api_key}
```

| Query parameter | Required | Description |
|-----------------|----------|-------------|
| `job_id` | Yes | The job ID returned by `POST /v1/jobs` |
| `api_key` | Yes | Your raw API key (same value as the Bearer token) |

Authentication is validated at connection time. An invalid key returns HTTP `401` before the WebSocket handshake completes.

### JavaScript example

```javascript
const jobId  = 'session_20260218_103045_abc12345';
const apiKey = 'hpx_live_YOUR_KEY_HERE';

const ws = new WebSocket(
  `wss://api.hyperplexity.ai/v1/progress?job_id=${jobId}&api_key=${apiKey}`
);

ws.onopen = () => {
  console.log('Connected to progress stream');
  // Send periodic pings to keep the connection alive
  setInterval(() => ws.send(JSON.stringify({ type: 'ping' })), 30_000);
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case 'connected':
      console.log('Stream ready for job:', msg.job_id);
      break;

    case 'progress':
      console.log(`Progress: ${msg.progress_percent}% — ${msg.current_step}`);
      break;

    case 'completed':
      console.log('Validation complete! Results at:', msg.results_url);
      ws.close();
      break;

    case 'error':
      console.error('Job failed:', msg.error.message);
      ws.close();
      break;

    case 'pong':
      // Keepalive acknowledged
      break;
  }
};

ws.onerror = (err) => console.error('WebSocket error', err);
ws.onclose = ()  => console.log('Connection closed');
```

### Message types

#### connected

Sent immediately after the WebSocket handshake succeeds.

```json
{
  "type": "connected",
  "job_id": "session_20260218_103045_abc12345",
  "timestamp": "2026-02-18T10:30:52Z"
}
```

#### progress

Sent periodically while the job is processing.

```json
{
  "type": "progress",
  "job_id": "session_20260218_103045_abc12345",
  "progress_percent": 45,
  "current_step": "Validating row 150 of 450",
  "estimated_completion": "2026-02-18T10:45:00Z",
  "timestamp": "2026-02-18T10:35:30Z"
}
```

#### completed

Sent once when the job finishes successfully.

```json
{
  "type": "completed",
  "job_id": "session_20260218_103045_abc12345",
  "status": "completed",
  "results_url": "/v1/jobs/session_20260218_103045_abc12345/results",
  "summary": {
    "rows_processed": 450,
    "run_time_seconds": 863,
    "cost_usd": 11.73
  },
  "timestamp": "2026-02-18T10:46:23Z"
}
```

#### error

Sent if the job fails.

```json
{
  "type": "error",
  "job_id": "session_20260218_103045_abc12345",
  "error": {
    "code": "validation_error",
    "message": "Processing failed"
  },
  "timestamp": "2026-02-18T10:35:12Z"
}
```

#### ping / pong

Client-initiated keepalive. Send `{"type":"ping"}` and the server responds with `{"type":"pong"}`.

### Connection limits

| Limit | Value |
|-------|-------|
| Max concurrent connections per API key | 5 |
| Idle timeout | 15 minutes |
| Recommended ping interval | 30 seconds |

---

## Webhooks

Register a `webhook_url` when creating or approving a job to receive a `POST` notification when the job completes or fails.

### Webhook security

All webhook requests include an HMAC-SHA256 signature in the `X-Hyperplexity-Signature` header. Always verify this signature before acting on the payload.

- Webhook URLs must use **HTTPS**.
- Private IP addresses, `localhost`, and internal hostnames are blocked (SSRF protection).

### Webhook request headers

```
POST https://your-app.com/webhooks/hyperplexity
Content-Type: application/json
X-Hyperplexity-Event: job.completed
X-Hyperplexity-Signature: sha256=abc123def456...
X-Hyperplexity-Job-Id: session_20260218_103045_abc12345
X-Hyperplexity-Timestamp: 1739796383
```

### Payload — job.completed

```json
{
  "event": "job.completed",
  "api_version": "v1",
  "job_id": "session_20260218_103045_abc12345",
  "status": "completed",
  "submitted_at": "2026-02-18T10:30:45Z",
  "completed_at": "2026-02-18T10:46:23Z",
  "run_time_seconds": 863,
  "results": {
    "rows_processed": 450,
    "columns_validated": 8,
    "download_url": "https://s3.amazonaws.com/.../results.zip?...",
    "download_expires_at": "2026-02-18T11:46:23Z"
  },
  "cost": {
    "charged_usd": 11.73
  }
}
```

### Payload — job.failed

```json
{
  "event": "job.failed",
  "api_version": "v1",
  "job_id": "session_20260218_103045_abc12345",
  "status": "failed",
  "submitted_at": "2026-02-18T10:30:45Z",
  "failed_at": "2026-02-18T10:35:12Z",
  "error": {
    "code": "validation_error",
    "message": "Invalid Excel file structure"
  }
}
```

### Signature verification

The signature covers the raw request body bytes, signed with your `webhook_secret` using HMAC-SHA256.

```python
import hmac
import hashlib

def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify the HMAC-SHA256 signature of a Hyperplexity webhook.

    Args:
        payload_body:      Raw request body (bytes, not decoded).
        signature_header:  Value of the X-Hyperplexity-Signature header.
        secret:            Your webhook_secret as provided when creating the job.

    Returns:
        True if the signature is valid.
    """
    expected = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    # Header format: "sha256=<hex_digest>"
    provided = signature_header.split('=', 1)[1]
    return hmac.compare_digest(expected, provided)
```

### Retry policy

| Attempt | Delay |
|---------|-------|
| 1 (initial) | Immediate |
| 2 | ~1 second |
| 3 | ~3 seconds |

Additional SQS-based retries may follow for endpoints that return a non-2xx status. Your endpoint must return `200 OK` within 10 seconds to be considered successful. Return a non-2xx status code to trigger a retry.

---

## Error Reference

| Error code | HTTP status | Description |
|------------|-------------|-------------|
| `missing_api_key` | 401 | No `Authorization: Bearer ...` header present |
| `invalid_api_key` | 401 | Key not found, revoked, or expired |
| `rate_limit_exceeded` | 429 | RPM or RPD limit reached; see `Retry-After` header |
| `missing_fields` | 400 | One or more required request fields are absent |
| `invalid_input` | 400 | A field has an invalid value (e.g., `preview_rows` not an integer) |
| `invalid_file_type` | 400 | `file_type` is not `"excel"` or `"pdf"` |
| `invalid_extension` | 400 | Filename extension does not match `file_type` |
| `invalid_file_size` | 400 | File size is 0 or exceeds the 50 MB limit |
| `missing_filename` | 400 | `filename` field is absent |
| `server_error` | 500 | Unexpected internal error — include `request_id` in support tickets |
| `request_failed` | varies | Generic upstream failure from an action handler |
| `not_found` | 404 | Route does not exist |
| `job_not_found` | 404 | No job found for the given `job_id` |
| `results_not_ready` | 404 | Job not yet completed; poll status first |
| `preview_not_complete` | 409 | Approval attempted before preview finished |
| `validation_already_queued` | 409 | Full validation has already been approved for this job |
| `insufficient_credits` | 402 | Account balance too low to cover the estimated cost |
| `cost_mismatch` | 409 | `approved_cost_usd` does not match the current estimate |
| `file_not_found` | 400 | S3 key not found — file may not have been uploaded yet |
| `config_not_found` | 400 | No validation config found for the session |

---

## Code Examples

### Python SDK Example

A complete client that runs the full workflow: presigned upload → S3 upload → create job → poll preview → approve → poll completion → download results.

```python
import time
import requests

class HyperplexityClient:
    """Minimal synchronous Hyperplexity API client."""

    BASE_URL = "https://api.hyperplexity.ai/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Step 1 — Request a presigned upload URL
    # ------------------------------------------------------------------
    def get_presigned_url(self, filename: str, file_size: int, file_type: str = "excel") -> dict:
        resp = self.session.post(
            f"{self.BASE_URL}/uploads/presigned",
            json={"filename": filename, "file_size": file_size, "file_type": file_type},
        )
        resp.raise_for_status()
        return resp.json()["data"]

    # ------------------------------------------------------------------
    # Step 2 — Upload the file directly to S3
    # ------------------------------------------------------------------
    def upload_to_s3(self, presigned_url: str, filepath: str, content_type: str) -> None:
        with open(filepath, "rb") as fh:
            put_resp = requests.put(
                presigned_url,
                data=fh,
                headers={"Content-Type": content_type},
            )
        put_resp.raise_for_status()

    # ------------------------------------------------------------------
    # Step 3 — Create a validation job
    # ------------------------------------------------------------------
    def create_job(
        self,
        session_id: str,
        s3_key: str,
        config: dict,
        preview_rows: int = 3,
        webhook_url: str = None,
        webhook_secret: str = None,
    ) -> dict:
        payload = {
            "session_id": session_id,
            "s3_key": s3_key,
            "config": config,
            "preview_rows": preview_rows,
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url
            payload["webhook_secret"] = webhook_secret
            payload["notify_method"] = "webhook"

        resp = self.session.post(f"{self.BASE_URL}/jobs", json=payload)
        resp.raise_for_status()
        return resp.json()["data"]

    # ------------------------------------------------------------------
    # Step 4 / 6 — Poll until a target status is reached
    # ------------------------------------------------------------------
    def poll_status(
        self,
        job_id: str,
        until: set,
        interval: int = 10,
        timeout: int = 1800,
    ) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = self.session.get(f"{self.BASE_URL}/jobs/{job_id}")
            resp.raise_for_status()
            data = resp.json()["data"]
            print(f"  [{data['status']}] {data.get('progress_percent', 0)}%"
                  f"  — {data.get('current_step', '')}")
            if data["status"] in until:
                return data
            if data["status"] == "failed":
                raise RuntimeError(f"Job failed: {data.get('current_step')}")
            time.sleep(interval)
        raise TimeoutError(f"Job did not reach {until} within {timeout}s")

    # ------------------------------------------------------------------
    # Step 5 — Approve full validation
    # ------------------------------------------------------------------
    def approve_validation(
        self,
        job_id: str,
        approved_cost_usd: float = None,
        webhook_url: str = None,
        webhook_secret: str = None,
    ) -> dict:
        payload = {}
        if approved_cost_usd is not None:
            payload["approved_cost_usd"] = approved_cost_usd
        if webhook_url:
            payload["webhook_url"] = webhook_url
            payload["webhook_secret"] = webhook_secret

        resp = self.session.post(f"{self.BASE_URL}/jobs/{job_id}/validate", json=payload)
        resp.raise_for_status()
        return resp.json()["data"]

    # ------------------------------------------------------------------
    # Step 7 — Get the download URL
    # ------------------------------------------------------------------
    def get_results(self, job_id: str) -> dict:
        resp = self.session.get(f"{self.BASE_URL}/jobs/{job_id}/results")
        resp.raise_for_status()
        return resp.json()["data"]

    # ------------------------------------------------------------------
    # High-level helper: run the entire workflow
    # ------------------------------------------------------------------
    def validate_file(self, filepath: str, config: dict, preview_rows: int = 3) -> dict:
        import os
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)

        print(f"[1/7] Requesting presigned URL for {filename} ({file_size} bytes) ...")
        presigned = self.get_presigned_url(filename, file_size, "excel")
        print(f"      session_id = {presigned['session_id']}")

        print("[2/7] Uploading file to S3 ...")
        self.upload_to_s3(presigned["presigned_url"], filepath, presigned["content_type"])

        print("[3/7] Creating validation job ...")
        job = self.create_job(
            session_id=presigned["session_id"],
            s3_key=presigned["s3_key"],
            config=config,
            preview_rows=preview_rows,
        )
        job_id = job["job_id"]
        print(f"      job_id = {job_id}")

        print("[4/7] Polling for preview completion ...")
        self.poll_status(job_id, until={"preview_complete"})

        print("[5/7] Approving full validation ...")
        self.approve_validation(job_id)

        print("[6/7] Polling for full validation completion ...")
        self.poll_status(job_id, until={"completed"}, interval=30)

        print("[7/7] Fetching results ...")
        results = self.get_results(job_id)
        print(f"      Download URL: {results['results']['download_url']}")
        print(f"      Rows processed: {results['summary']['rows_processed']}")
        print(f"      Cost: ${results['summary']['cost_usd']:.2f}")
        return results


# -----------------------------------------------------------------------
# Usage
# -----------------------------------------------------------------------
if __name__ == "__main__":
    client = HyperplexityClient("hpx_live_YOUR_KEY_HERE")

    config = {
        "tables": [
            {
                "name": "Companies",
                "columns": {
                    "Company Name": {"validation_type": "text",   "required": True},
                    "Website":      {"validation_type": "url",    "required": False},
                    "Email":        {"validation_type": "email",  "required": True},
                    "Founded Year": {
                        "validation_type": "number",
                        "required": False,
                        "constraints": {"min": 1800, "max": 2026},
                    },
                },
            }
        ]
    }

    results = client.validate_file("companies.xlsx", config)
```

---

### JavaScript Example

```javascript
const BASE_URL = 'https://api.hyperplexity.ai/v1';
const API_KEY  = 'hpx_live_YOUR_KEY_HERE';

const headers = (extra = {}) => ({
  'Authorization': `Bearer ${API_KEY}`,
  'Content-Type': 'application/json',
  ...extra,
});

// -----------------------------------------------------------------------
// Step 1: Request presigned URL
// -----------------------------------------------------------------------
async function getPresignedUrl(filename, fileSize, fileType = 'excel') {
  const res = await fetch(`${BASE_URL}/uploads/presigned`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ filename, file_size: fileSize, file_type: fileType }),
  });
  if (!res.ok) throw new Error(`Presigned URL error: ${res.status}`);
  const { data } = await res.json();
  return data;
}

// -----------------------------------------------------------------------
// Step 2: Upload file directly to S3
// -----------------------------------------------------------------------
async function uploadToS3(presignedUrl, file, contentType) {
  const res = await fetch(presignedUrl, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: file,
  });
  if (!res.ok) throw new Error(`S3 upload failed: ${res.status}`);
}

// -----------------------------------------------------------------------
// Step 3: Create validation job
// -----------------------------------------------------------------------
async function createJob(sessionId, s3Key, config, previewRows = 3) {
  const res = await fetch(`${BASE_URL}/jobs`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({
      session_id: sessionId,
      s3_key: s3Key,
      config,
      preview_rows: previewRows,
    }),
  });
  if (!res.ok) throw new Error(`Create job error: ${res.status}`);
  const { data } = await res.json();
  return data;
}

// -----------------------------------------------------------------------
// Step 4 / 6: Poll until a target status is reached
// -----------------------------------------------------------------------
async function pollStatus(jobId, targetStatuses, intervalMs = 10_000, timeoutMs = 1_800_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${BASE_URL}/jobs/${jobId}`, { headers: headers() });
    if (!res.ok) throw new Error(`Status check error: ${res.status}`);
    const { data } = await res.json();
    console.log(`[${data.status}] ${data.progress_percent ?? 0}% — ${data.current_step ?? ''}`);
    if (targetStatuses.includes(data.status)) return data;
    if (data.status === 'failed') throw new Error(`Job failed: ${data.current_step}`);
    await new Promise(r => setTimeout(r, intervalMs));
  }
  throw new Error(`Timeout waiting for ${targetStatuses}`);
}

// -----------------------------------------------------------------------
// Step 5: Approve full validation
// -----------------------------------------------------------------------
async function approveValidation(jobId, approvedCostUsd = null) {
  const payload = {};
  if (approvedCostUsd !== null) payload.approved_cost_usd = approvedCostUsd;
  const res = await fetch(`${BASE_URL}/jobs/${jobId}/validate`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Approve error: ${res.status}`);
  return (await res.json()).data;
}

// -----------------------------------------------------------------------
// Step 7: Get results
// -----------------------------------------------------------------------
async function getResults(jobId) {
  const res = await fetch(`${BASE_URL}/jobs/${jobId}/results`, { headers: headers() });
  if (!res.ok) throw new Error(`Results error: ${res.status}`);
  return (await res.json()).data;
}

// -----------------------------------------------------------------------
// Full workflow (browser — pass a File object from an <input type="file">)
// -----------------------------------------------------------------------
async function validateFile(file, config) {
  console.log('[1/7] Requesting presigned URL ...');
  const presigned = await getPresignedUrl(file.name, file.size, 'excel');

  console.log('[2/7] Uploading to S3 ...');
  await uploadToS3(presigned.presigned_url, file, presigned.content_type);

  console.log('[3/7] Creating validation job ...');
  const job = await createJob(presigned.session_id, presigned.s3_key, config);
  console.log('job_id:', job.job_id);

  console.log('[4/7] Waiting for preview ...');
  await pollStatus(job.job_id, ['preview_complete']);

  console.log('[5/7] Approving full validation ...');
  await approveValidation(job.job_id);

  console.log('[6/7] Waiting for completion ...');
  await pollStatus(job.job_id, ['completed'], 30_000);

  console.log('[7/7] Fetching results ...');
  const results = await getResults(job.job_id);
  console.log('Download URL:', results.results.download_url);
  return results;
}
```

---

### curl Quickstart

Step-by-step curl commands for the entire validation flow.

```bash
#!/usr/bin/env bash
set -euo pipefail

API_KEY="hpx_live_YOUR_KEY_HERE"
BASE="https://api.hyperplexity.ai/v1"
FILE="companies.xlsx"

# ---- Step 1: Get presigned URL ----
echo "==> Requesting presigned URL ..."
PRESIGNED=$(curl -sf -X POST "$BASE/uploads/presigned" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"filename\": \"$FILE\",
    \"file_size\": $(wc -c < "$FILE"),
    \"file_type\": \"excel\"
  }")

PRESIGNED_URL=$(echo "$PRESIGNED" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['presigned_url'])")
SESSION_ID=$(echo "$PRESIGNED"    | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['session_id'])")
S3_KEY=$(echo "$PRESIGNED"        | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['s3_key'])")
CONTENT_TYPE=$(echo "$PRESIGNED"  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['content_type'])")

echo "    session_id = $SESSION_ID"

# ---- Step 2: Upload to S3 ----
echo "==> Uploading to S3 ..."
curl -sf -X PUT "$PRESIGNED_URL" \
  -H "Content-Type: $CONTENT_TYPE" \
  --data-binary "@$FILE"
echo "    Upload complete."

# ---- Step 3: Create job ----
echo "==> Creating validation job ..."
JOB=$(curl -sf -X POST "$BASE/jobs" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"s3_key\": \"$S3_KEY\",
    \"config\": {
      \"tables\": [{
        \"name\": \"Companies\",
        \"columns\": {
          \"Company Name\": {\"validation_type\": \"text\", \"required\": true},
          \"Website\":      {\"validation_type\": \"url\",  \"required\": false}
        }
      }]
    },
    \"preview_rows\": 3
  }")
JOB_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['job_id'])")
echo "    job_id = $JOB_ID"

# ---- Step 4: Poll for preview_complete ----
echo "==> Polling for preview completion ..."
while true; do
  STATUS=$(curl -sf "$BASE/jobs/$JOB_ID" \
    -H "Authorization: Bearer $API_KEY" \
    | python3 -c "import sys,json; d=json.load(sys.stdin)['data']; print(d['status'], d.get('progress_percent',0))")
  echo "    $STATUS"
  STATE=$(echo "$STATUS" | awk '{print $1}')
  [ "$STATE" = "preview_complete" ] && break
  [ "$STATE" = "failed"           ] && { echo "Job failed."; exit 1; }
  sleep 10
done

# ---- Step 5: Approve full validation ----
echo "==> Approving full validation ..."
curl -sf -X POST "$BASE/jobs/$JOB_ID/validate" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}' > /dev/null
echo "    Approved."

# ---- Step 6: Poll for completed ----
echo "==> Polling for completion ..."
while true; do
  STATUS=$(curl -sf "$BASE/jobs/$JOB_ID" \
    -H "Authorization: Bearer $API_KEY" \
    | python3 -c "import sys,json; d=json.load(sys.stdin)['data']; print(d['status'], d.get('progress_percent',0))")
  echo "    $STATUS"
  STATE=$(echo "$STATUS" | awk '{print $1}')
  [ "$STATE" = "completed" ] && break
  [ "$STATE" = "failed"    ] && { echo "Job failed."; exit 1; }
  sleep 30
done

# ---- Step 7: Get results ----
echo "==> Fetching results ..."
RESULTS=$(curl -sf "$BASE/jobs/$JOB_ID/results" \
  -H "Authorization: Bearer $API_KEY")
DOWNLOAD_URL=$(echo "$RESULTS" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['results']['download_url'])")
ROWS=$(echo "$RESULTS"         | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['summary']['rows_processed'])")
COST=$(echo "$RESULTS"         | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['summary']['cost_usd'])")
echo "    Rows processed : $ROWS"
echo "    Cost           : \$$COST"
echo "    Download URL   : $DOWNLOAD_URL"

# ---- Step 8: Download results ----
echo "==> Downloading results.zip ..."
curl -sf "$DOWNLOAD_URL" -o results.zip
echo "    Saved to results.zip"
```

---

## Config Schema Reference

The `config` object controls which columns are validated and how. Pass it as the `config` field in `POST /v1/jobs` or save a config via the Hyperplexity web UI.

### Top-level structure

```json
{
  "tables": [ ... ],
  "global_settings": { ... }
}
```

### `tables` array

Each entry describes one spreadsheet sheet (or logical table).

```json
{
  "name": "Companies",
  "sheet_name": "Sheet1",
  "columns": { ... }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name for this table (used in reports) |
| `sheet_name` | string | No | Excel sheet name to validate. Defaults to the first sheet if omitted. |
| `columns` | object | Yes | Map of column header strings to column config objects (see below) |

### Column config object

Each key in `columns` is the **exact column header** as it appears in the spreadsheet.

```json
{
  "validation_type": "url",
  "required": false,
  "ai_prompt": "Check if URL is valid and accessible",
  "constraints": {
    "min": 1800,
    "max": 2026
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `validation_type` | string | Yes | Type of validation to apply (see table below) |
| `required` | boolean | No | If `true`, empty cells are marked invalid. Default: `false`. |
| `ai_prompt` | string | No | Custom instruction appended to the AI validation prompt for this column |
| `constraints` | object | No | Type-specific constraints (currently used with `"number"`) |

### Validation types

| `validation_type` | Description |
|-------------------|-------------|
| `"text"` | General text — checks for plausible content |
| `"url"` | URL format validation |
| `"email"` | Email address format and domain validation |
| `"number"` | Numeric value; supports `constraints.min` and `constraints.max` |

### `constraints` object (for `"number"` type)

| Field | Type | Description |
|-------|------|-------------|
| `min` | number | Minimum allowed value (inclusive) |
| `max` | number | Maximum allowed value (inclusive) |

### `global_settings` object

```json
{
  "max_retries": 3,
  "confidence_threshold": 0.7
}
```

| Field | Type | Description |
|-------|------|-------------|
| `max_retries` | integer | Number of times to retry an AI call on transient failure. Default: `3`. |
| `confidence_threshold` | number | Minimum confidence score (0.0–1.0) below which a result is flagged for review. Default: `0.7`. |

### Complete config example

```json
{
  "tables": [
    {
      "name": "Companies",
      "sheet_name": "Sheet1",
      "columns": {
        "Company Name": {
          "validation_type": "text",
          "required": true,
          "ai_prompt": "Verify this is a recognizable company or organization name"
        },
        "Website": {
          "validation_type": "url",
          "required": false
        },
        "Contact Email": {
          "validation_type": "email",
          "required": true
        },
        "Founded Year": {
          "validation_type": "number",
          "required": false,
          "constraints": {
            "min": 1800,
            "max": 2026
          }
        }
      }
    }
  ],
  "global_settings": {
    "max_retries": 3,
    "confidence_threshold": 0.7
  }
}
```
