# Hyperplexity Webhooks — Integration Guide

## Overview

Webhooks let Hyperplexity push a notification to your server the moment a validation job finishes or fails. Instead of repeatedly calling `GET /v1/jobs/{job_id}` to check progress (polling), you register an HTTPS endpoint and Hyperplexity calls it for you.

**When to use webhooks vs polling**

| Situation | Recommendation |
|-----------|---------------|
| Jobs that run for seconds to minutes | Webhooks — no wasted requests |
| Short-lived scripts or one-off jobs | Polling is simpler |
| Server-side integrations | Webhooks |
| Browser-based UIs | WebSocket progress updates or polling |

Webhooks fire on two events:

- `job.completed` — full validation finished successfully
- `job.failed` — the job encountered an unrecoverable error

Webhooks are **per-job** and are configured by supplying `webhook_url` and an optional `webhook_secret` when you create or approve a job. They are not global account settings.

---

## Configuring Webhooks

### On job creation — `POST /v1/jobs`

Pass `webhook_url` and `webhook_secret` in the request body:

```json
{
  "session_id": "session_20260217_103045_abc123",
  "s3_key": "uploads/.../companies.xlsx",
  "config": { ... },
  "preview_rows": 3,
  "webhook_url": "https://your-app.com/webhooks/hyperplexity",
  "webhook_secret": "whsec_your_random_secret_here"
}
```

### On validation approval — `POST /v1/jobs/{job_id}/validate`

You can supply (or override) the webhook when approving full validation. This is useful if you did not set a webhook at job creation, or if you want a different endpoint for the completion event:

```json
{
  "approved_cost_usd": 1.25,
  "webhook_url": "https://your-app.com/webhooks/hyperplexity",
  "webhook_secret": "whsec_your_random_secret_here"
}
```

If both calls supply a `webhook_url`, the value on `/validate` takes precedence for the `job.completed` / `job.failed` events.

### Security requirements for the URL

- The URL **must** use `https://`. Requests with `http://` are rejected before the job is even queued.
- Private IP ranges, localhost, and loopback addresses are blocked (see [Security Requirements](#security-requirements)).
- The URL must be publicly reachable from the internet.

### The `webhook_secret`

The secret is optional but **strongly recommended**. It is used to compute an HMAC-SHA256 signature over the request body so that your endpoint can verify the request genuinely came from Hyperplexity. Choose a random string of at least 32 characters; treat it like a password and store it in an environment variable or secrets manager.

---

## Event Types

All webhook requests are `HTTP POST` with `Content-Type: application/json`.

### `job.completed`

Fired when a full validation job finishes successfully.

**Example HTTP request**

```
POST https://your-app.com/webhooks/hyperplexity HTTP/1.1
Content-Type: application/json
User-Agent: Hyperplexity-Webhook/1.0
X-Hyperplexity-Event: job.completed
X-Hyperplexity-Signature: sha256=a3f1b2c9d4e5f67890ab12cd34ef5678901234abcdef567890abcdef12345678
X-Hyperplexity-Timestamp: 1739800000
```

**JSON body**

```json
{
  "event": "job.completed",
  "api_version": "v1",
  "job_id": "session_20260217_103045_abc123",
  "status": "completed",
  "submitted_at": "2026-02-17T10:30:45.123456+00:00",
  "completed_at": "2026-02-17T10:34:12.789012+00:00",
  "results": {
    "rows_processed": 250
  },
  "cost": {
    "charged_usd": 1.25
  }
}
```

**Field reference**

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Always `"job.completed"` |
| `api_version` | string | API version that produced this event (`"v1"`) |
| `job_id` | string | The job identifier (same as `session_id`) |
| `status` | string | Always `"completed"` |
| `submitted_at` | string (ISO 8601) | When the job was originally created |
| `completed_at` | string (ISO 8601) | UTC timestamp when the job finished |
| `results.rows_processed` | integer | Number of rows validated |
| `cost.charged_usd` | number | Amount charged to your account balance in USD |

---

### `job.failed`

Fired when a full validation job encounters an unrecoverable error.

**Example HTTP request**

```
POST https://your-app.com/webhooks/hyperplexity HTTP/1.1
Content-Type: application/json
User-Agent: Hyperplexity-Webhook/1.0
X-Hyperplexity-Event: job.failed
X-Hyperplexity-Signature: sha256=b9e2a1f4c3d6e78901bc23de45fa6789012345bcdef678901bcdef23456789ab
X-Hyperplexity-Timestamp: 1739800500
```

**JSON body**

```json
{
  "event": "job.failed",
  "api_version": "v1",
  "job_id": "session_20260217_103045_abc123",
  "status": "failed",
  "submitted_at": "2026-02-17T10:30:45.123456+00:00",
  "failed_at": "2026-02-17T10:35:02.456789+00:00",
  "error": {
    "code": "validation_error",
    "message": "Failed to process input file: column 'email' not found"
  }
}
```

**Field reference**

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Always `"job.failed"` |
| `api_version` | string | API version that produced this event (`"v1"`) |
| `job_id` | string | The job identifier |
| `status` | string | Always `"failed"` |
| `submitted_at` | string (ISO 8601) | When the job was originally created |
| `failed_at` | string (ISO 8601) | UTC timestamp when the failure was detected |
| `error.code` | string | Machine-readable error code |
| `error.message` | string | Human-readable description (capped at 500 characters) |

---

## Signature Verification

Every webhook request that was configured with a `webhook_secret` includes an `X-Hyperplexity-Signature` header:

```
X-Hyperplexity-Signature: sha256=<hexdigest>
```

The signature is an **HMAC-SHA256** digest of the raw request body bytes, keyed with the `webhook_secret` you provided. The algorithm:

1. Take the raw bytes of the request body exactly as received (before any JSON parsing).
2. Compute `HMAC-SHA256(key=webhook_secret.encode('utf-8'), msg=body_bytes)`.
3. Hex-encode the digest.
4. Compare it to the value after `sha256=` in the header using a **timing-safe** comparison function.

**Always verify signatures.** Treat any webhook that fails verification as untrusted and return `401`.

### Verification examples

#### Python (Flask)

```python
import hashlib
import hmac
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET = "whsec_your_random_secret_here"  # load from env in production


def verify_signature(body_bytes: bytes, signature_header: str) -> bool:
    """Return True if the signature header matches the expected HMAC."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    provided_digest = signature_header.split("=", 1)[1]
    expected_digest = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_digest, provided_digest)


@app.route("/webhooks/hyperplexity", methods=["POST"])
def handle_webhook():
    # 1. Read raw bytes BEFORE letting Flask parse JSON
    body_bytes = request.get_data()

    # 2. Verify the signature
    signature_header = request.headers.get("X-Hyperplexity-Signature", "")
    if not verify_signature(body_bytes, signature_header):
        return jsonify({"error": "Invalid signature"}), 401

    # 3. Parse and handle the event
    event = request.get_json()
    event_type = event.get("event")
    job_id = event.get("job_id")

    if event_type == "job.completed":
        rows = event["results"]["rows_processed"]
        cost = event["cost"]["charged_usd"]
        print(f"Job {job_id} completed: {rows} rows, ${cost:.4f} charged")
        # TODO: trigger your post-processing logic
    elif event_type == "job.failed":
        error = event.get("error", {})
        print(f"Job {job_id} failed: [{error.get('code')}] {error.get('message')}")
        # TODO: alert your team or retry job submission

    # 4. Return 2xx quickly — do heavy work asynchronously
    return jsonify({"received": True}), 200
```

#### Node.js (Express)

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET; // e.g. "whsec_your_random_secret_here"

// Use express.raw() to capture the body as a Buffer BEFORE JSON parsing
app.post('/webhooks/hyperplexity', express.raw({ type: 'application/json' }), (req, res) => {
  const signatureHeader = req.headers['x-hyperplexity-signature'] || '';

  // 1. Verify the signature
  if (!signatureHeader.startsWith('sha256=')) {
    return res.status(401).json({ error: 'Missing or malformed signature' });
  }

  const providedDigest = signatureHeader.slice('sha256='.length);
  const expectedDigest = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(req.body) // req.body is a Buffer because of express.raw()
    .digest('hex');

  if (!crypto.timingSafeEqual(Buffer.from(expectedDigest), Buffer.from(providedDigest))) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // 2. Parse and handle the event
  const event = JSON.parse(req.body.toString('utf-8'));
  const { event: eventType, job_id: jobId } = event;

  if (eventType === 'job.completed') {
    const { rows_processed } = event.results;
    const { charged_usd } = event.cost;
    console.log(`Job ${jobId} completed: ${rows_processed} rows, $${charged_usd} charged`);
    // TODO: enqueue post-processing task
  } else if (eventType === 'job.failed') {
    const { code, message } = event.error;
    console.error(`Job ${jobId} failed: [${code}] ${message}`);
    // TODO: alert or retry
  }

  // 3. Acknowledge immediately
  res.status(200).json({ received: true });
});

app.listen(3000);
```

#### Python (Django)

```python
import hashlib
import hmac
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import os

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


@csrf_exempt
@require_POST
def hyperplexity_webhook(request):
    body_bytes = request.body  # Django gives you raw bytes here

    signature_header = request.META.get("HTTP_X_HYPERPLEXITY_SIGNATURE", "")
    if not signature_header.startswith("sha256="):
        return JsonResponse({"error": "Missing signature"}, status=401)

    provided_digest = signature_header.split("=", 1)[1]
    expected_digest = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_digest, provided_digest):
        return JsonResponse({"error": "Invalid signature"}, status=401)

    event = json.loads(body_bytes)
    # dispatch to your handlers ...

    return JsonResponse({"received": True}, status=200)
```

---

## Retry Logic

Hyperplexity makes up to **3 total delivery attempts** per webhook event. The retry strategy has two layers:

### Layer 1 — Inline retries (within Lambda execution)

On the first delivery attempt, `webhook_client.py` makes up to 3 HTTP calls inside the same Lambda invocation with short delays between them:

| Attempt | Wait before attempt |
|---------|-------------------|
| 1 | None — immediate |
| 2 | 1 second |
| 3 | 3 seconds |

If all 3 inline attempts return a non-2xx response (or time out), the delivery is considered failed for this Lambda execution.

### Layer 2 — SQS-based retries (across Lambda executions)

When inline delivery fails, a `webhook_retry` message can be enqueued to SQS, which triggers an independent Lambda execution to attempt delivery again. Each SQS-based retry uses the same inline 3-attempt logic (attempt 1 with no wait, attempt 2 after 1 s, attempt 3 after 3 s).

The SQS delivery schedule (from the design specification) uses exponential backoff between SQS attempts:

| SQS attempt | Delay before invocation |
|-------------|------------------------|
| 1 | 60 seconds |
| 2 | 300 seconds (5 minutes) |
| 3 | 900 seconds (15 minutes) |

### Delivery guarantees

- Each attempt has a **10-second HTTP timeout**.
- The maximum payload size is **1 MB**. Payloads exceeding this limit are dropped without delivery.
- After all attempts are exhausted, the webhook is **dropped**. Hyperplexity does not retain undelivered webhooks. Use `GET /v1/jobs/{job_id}` or `GET /v1/jobs/{job_id}/results` to retrieve job outcomes regardless of webhook delivery status.
- **Your endpoint must return a 2xx status code** to acknowledge receipt. Any other response code (3xx, 4xx, 5xx) or a connection timeout is treated as a failure and triggers a retry.

---

## Security Requirements

### HTTPS only

`webhook_url` must begin with `https://`. Any URL using `http://` is rejected immediately with a validation error before the job is accepted.

### SSRF protection

Hyperplexity resolves the hostname of your `webhook_url` before making any HTTP call. If the resolved IP address falls into any of the following categories, the delivery is blocked:

| Blocked range | Example |
|---------------|---------|
| Loopback | `127.0.0.0/8`, `::1` |
| Private (RFC 1918) | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` |
| Link-local | `169.254.0.0/16` (AWS metadata endpoint, etc.) |
| Reserved / multicast | Various |
| Literal hostnames | `localhost`, `127.0.0.1`, `0.0.0.0`, `::1` |

This protection is enforced by `webhook_client._is_private_address()` using Python's `ipaddress` module. DNS resolution is performed fresh for each delivery attempt.

If DNS resolution fails (NXDOMAIN, timeout, etc.), the URL is treated as potentially valid and delivery is attempted — this is a deliberate trade-off that favours availability over strict SSRF prevention for transient DNS failures.

---

## Best Practices

1. **Always verify the signature before processing.**
   An unverified webhook could be a replay attack or a spoofed request. Return `401` immediately if the signature is missing or wrong.

2. **Return 200 quickly — do heavy work asynchronously.**
   Hyperplexity waits up to 10 seconds for a response. If your handler takes longer than that, the delivery is treated as a timeout and retried. Enqueue the event to a background queue (Celery, BullMQ, SQS, etc.) and return `200` immediately.

3. **Handle duplicate deliveries using `job_id`.**
   Network retries mean your endpoint may receive the same event more than once. Make your handler idempotent by keying on `job_id`. For example, upsert a row in your database rather than inserting unconditionally.

4. **Log the raw payload and signature before parsing.**
   This makes debugging signature mismatches much easier. Log the bytes as received, not the parsed JSON — body parsing can silently change whitespace or encoding.

5. **Use a different `webhook_secret` per environment.**
   Use distinct secrets for development, staging, and production so that a compromised secret in one environment does not affect others. Store secrets in your secrets manager, not in source code.

6. **Monitor your endpoint's error rate.**
   Track 4xx and 5xx response rates on your webhook endpoint. Sustained failures will exhaust retries and cause events to be dropped. Set up an alert if your webhook endpoint starts returning errors.

---

## Testing Webhooks Locally

Your development machine is not publicly reachable, so you need a tunneling tool to expose a local port over HTTPS.

**Using ngrok:**

```bash
# Install ngrok from https://ngrok.com and authenticate once
ngrok http 5000
```

ngrok prints a forwarding URL such as `https://a1b2c3d4.ngrok.io`. Use that as your `webhook_url` in test job submissions.

**Example test job:**

```bash
curl -X POST https://api.hyperplexity.ai/v1/jobs \
  -H "X-API-Key: hpx_live_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_test_webhook_001",
    "s3_key": "uploads/.../sample.xlsx",
    "preview_rows": 3,
    "webhook_url": "https://a1b2c3d4.ngrok.io/webhooks/hyperplexity",
    "webhook_secret": "dev_test_secret"
  }'
```

Using only 3 preview rows keeps the job fast and the cost zero during testing.

**Alternatives to ngrok:** [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/), [localtunnel](https://github.com/localtunnel/localtunnel), or [Tailscale Funnel](https://tailscale.com/kb/1223/funnel/).

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Webhook never fires | Job not completing, or webhook set only on preview (not `/validate`) | Check job status via `GET /v1/jobs/{job_id}`. Webhooks fire on full validation, not on preview. Ensure `webhook_url` was passed to `/validate`. |
| `401` — signature mismatch | Wrong `webhook_secret`, or body was parsed/re-encoded before verification | Log the raw body bytes received. Ensure you read the raw request body before any JSON parsing. Confirm the secret matches what was sent to the API exactly. |
| Timeouts / retries arriving | Your handler is taking longer than 10 s | Return `200` immediately and process the event asynchronously. |
| Duplicate events received | Network-level retry reached your endpoint multiple times | Use `job_id` for idempotency — check if you have already processed this job before doing any work. |
| `webhook_url` rejected at job creation | URL uses `http://` or resolves to a private IP | Switch to `https://`. If testing locally, use ngrok or another tunnel. |
| No signature header | `webhook_secret` was not provided when the job was created | Re-submit with a `webhook_secret`. Without a secret, the `X-Hyperplexity-Signature` header is omitted. |
| Payload exceeds size limit | Unusual — payloads are normally small | If you are seeing this, contact support. The 1 MB limit is a hard cap; oversized payloads are dropped. |
