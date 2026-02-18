# Hyperplexity External API - Design Document

**Version:** 1.0
**Date:** 2026-02-17
**Status:** Design Phase
**Branch:** `api`

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [API Specification](#api-specification)
4. [Authentication & Security](#authentication--security)
5. [Account Management System](#account-management-system)
6. [Implementation Phases](#implementation-phases)
7. [Testing Strategy](#testing-strategy)
8. [Deployment](#deployment)
9. [Appendix](#appendix)

---

## Executive Summary

### Objective
Enable external programmatic access to the Hyperplexity validation service while maintaining existing web UI functionality.

### Design Principles
1. **API-First**: Document complete API spec before implementation
2. **Code Reuse**: 90%+ shared business logic between web UI and API
3. **Async-First**: All long-running operations return immediately (no timeouts)
4. **Multiple Progress Channels**: HTTP polling, WebSockets, and Webhooks
5. **Security**: API key authentication, rate limiting, CORS flexibility
6. **Billing**: Reuse existing prepaid credits system

### Key Deliverables
- RESTful API at `api.hyperplexity.ai/v1`
- API key management system
- Account management UI at `/account`
- Comprehensive API documentation
- WebSocket support for real-time progress
- Webhook notifications for job completion

---

## Architecture Overview

### Dual API Gateway Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                      CLIENT APPLICATIONS                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Web UI     │  │ API Clients  │  │  Internal    │         │
│  │ (Squarespace)│  │ (Developers) │  │  Tools       │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                 │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          │                  │                  │
┌─────────▼──────────────────┼──────────────────┼─────────────────┐
│                            │                  │                 │
│  WEB UI API GATEWAY        │  EXTERNAL API    │                 │
│  app.hyperplexity.ai       │  GATEWAY         │                 │
│                            │  api.hyperplexity.│                │
│  - POST /validate          │  ai/v1           │                 │
│  - Action-based routing    │                  │                 │
│  - JWT auth                │  - RESTful paths │                 │
│  - CORS: Squarespace       │  - API key auth  │                 │
│  - WebSocket (session)     │  - CORS: wildcard│                 │
│                            │  - WebSocket     │                 │
│                            │    (optional)    │                 │
└────────────┬───────────────┴──────────┬───────┴─────────────────┘
             │                          │
             │                          │
             └──────────┬───────────────┘
                        │
             ┌──────────▼──────────┐
             │                     │
             │  INTERFACE LAMBDA   │
             │  (Unified Backend)  │
             │                     │
             │  ┌───────────────┐  │
             │  │ http_handler  │  │  Web UI requests
             │  └───────┬───────┘  │
             │          │          │
             │  ┌───────▼───────┐  │
             │  │ Action Router │  │  Shared routing
             │  └───────┬───────┘  │
             │          │          │
             │  ┌───────▼───────┐  │
             │  │ api_handler   │  │  API requests
             │  └───────────────┘  │
             │                     │
             └──────────┬──────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
│              │ │             │ │            │
│ Config Lambda│ │  Validation │ │   SQS      │
│              │ │  Lambda     │ │  Queues    │
│              │ │             │ │            │
└──────────────┘ └─────────────┘ └────┬───────┘
                                      │
        ┌─────────────────────────────┼─────────────────┐
        │                             │                 │
┌───────▼────────┐ ┌─────────────────▼──┐ ┌───────────▼────────┐
│   DynamoDB     │ │        S3          │ │  WebSocket API     │
│   - api-keys   │ │  - File storage    │ │  (Progress stream) │
│   - sessions   │ │  - Results         │ │                    │
│   - usage      │ │  - Configs         │ │                    │
└────────────────┘ └────────────────────┘ └────────────────────┘
```

### Request Flow Comparison

#### Web UI Flow (Existing)
```
Browser → POST /validate {action: "processExcel", ...}
  ↓
API Gateway 1 (app.hyperplexity.ai)
  ↓
Interface Lambda → http_handler.py
  ↓
JWT auth (session_manager.extract_email_from_request)
  ↓
Route by action field
  ↓
Action handler (process_excel_unified.py)
  ↓
SQS → Background processing
  ↓
WebSocket updates → Browser
  ↓
Email notification when complete
```

#### API Flow (New)
```
API Client → POST /v1/jobs {upload_id: "...", config: {...}}
  ↓
API Gateway 2 (api.hyperplexity.ai/v1)
  ↓
Interface Lambda → api_handler.py
  ↓
API key auth (api_key_manager.authenticate_api_key)
  ↓
Translate RESTful path → action
  ↓
SAME action handler (process_excel_unified.py)
  ↓
SAME SQS → Background processing
  ↓
WebSocket updates (optional) OR Polling OR Webhook
  ↓
Webhook POST when complete (if registered)
```

**Key Insight**: Both flows converge at action handlers - 90%+ code reuse!

---

## API Specification

### Base URL
```
Production: https://api.hyperplexity.ai/v1
Sandbox:    https://api-sandbox.hyperplexity.ai/v1  (future)
```

### Authentication
All endpoints require API key authentication via `Authorization` header:
```
Authorization: Bearer hpx_live_a1b2c3d4e5f6...
```

### Standard Response Envelope
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-02-17T10:30:00Z",
    "api_version": "v1"
  }
}
```

### Error Response Format
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
    "request_id": "req_abc123",
    "timestamp": "2026-02-17T10:30:00Z",
    "api_version": "v1"
  }
}
```

### HTTP Status Codes

| Code | Meaning | Usage |
|------|---------|-------|
| 200 | OK | Successful GET request |
| 201 | Created | Resource created (API key) |
| 202 | Accepted | Job queued successfully |
| 400 | Bad Request | Invalid input, malformed JSON |
| 401 | Unauthorized | Invalid or missing API key |
| 402 | Payment Required | Insufficient credits |
| 403 | Forbidden | API key revoked or lacks permission |
| 404 | Not Found | Job not found or doesn't belong to account |
| 409 | Conflict | Resource conflict (duplicate job) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error (includes request_id for support) |

---

## API Endpoints

### 1. File Upload

#### 1.1 Request Presigned Upload URL

**Endpoint:** `POST /v1/uploads/presigned`

**Purpose:** Get a presigned S3 URL to upload your data file directly to S3, bypassing API Gateway size limits.

**Request:**
```json
{
  "filename": "companies.xlsx",
  "file_size": 2048000,
  "file_type": "excel",
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "upload_id": "upload_a1b2c3d4",
    "session_id": "session_20260217_103045_abc123",
    "presigned_url": "https://s3.amazonaws.com/hyperplexity-storage/results/...",
    "s3_key": "results/hyperplexity.ai/api+org123/session_20260217_103045_abc123/upload_a1b2c3d4_companies.xlsx",
    "expires_at": "2026-02-17T10:35:45Z",
    "upload_method": "PUT",
    "required_headers": {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
  },
  "meta": { ... }
}
```

**File Upload (Direct to S3):**
```bash
# Step 1: Get presigned URL
curl -X POST https://api.hyperplexity.ai/v1/uploads/presigned \
  -H "Authorization: Bearer hpx_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "companies.xlsx",
    "file_size": 2048000,
    "file_type": "excel"
  }'

# Step 2: Upload file directly to S3
curl -X PUT "${presigned_url}" \
  -H "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  --data-binary @companies.xlsx
```

**Rate Limit:** 60 requests/minute

---

### 2. Validation Jobs

#### 2.1 Create Validation Job

**Endpoint:** `POST /v1/jobs`

**Purpose:** Submit a validation job with uploaded file and configuration. Returns immediately with job ID - processing happens asynchronously.

**Request:**
```json
{
  "session_id": "session_20260217_103045_abc123",
  "upload_id": "upload_a1b2c3d4",
  "s3_key": "results/hyperplexity.ai/.../upload_a1b2c3d4_companies.xlsx",
  "config": {
    "tables": [
      {
        "name": "Companies",
        "columns": {
          "Company Name": {
            "validation_type": "text",
            "required": true
          },
          "Website": {
            "validation_type": "url",
            "required": false
          }
        }
      }
    ]
  },
  "preview_rows": 3,
  "webhook_url": "https://your-app.com/webhooks/validation",
  "webhook_secret": "your_webhook_secret_123",
  "notify_method": "both"
}
```

**Field Descriptions:**
- `session_id` - From presigned URL response
- `upload_id` - From presigned URL response
- `s3_key` - From presigned URL response
- `config` - Validation configuration JSON (see Config Schema)
- `preview_rows` - Number of rows to validate in preview (default: 3, max: 10)
- `webhook_url` - Optional HTTPS URL to POST completion notification
- `webhook_secret` - Optional secret for HMAC signature verification
- `notify_method` - `"email"`, `"webhook"`, `"poll"`, or `"both"` (default: `"poll"`)

**Response:** `202 Accepted`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "queued",
    "run_type": "preview",
    "created_at": "2026-02-17T10:30:45Z",
    "urls": {
      "status": "/v1/jobs/session_20260217_103045_abc123",
      "progress": "/v1/jobs/session_20260217_103045_abc123/progress",
      "results": "/v1/jobs/session_20260217_103045_abc123/results",
      "websocket": "wss://api.hyperplexity.ai/v1/progress?job_id=session_20260217_103045_abc123&api_key=hpx_live_xxx"
    },
    "polling": {
      "recommended_interval_seconds": 10,
      "max_wait_seconds": 1800
    }
  },
  "meta": { ... }
}
```

**Rate Limit:** 20 requests/minute

---

#### 2.2 Get Job Status

**Endpoint:** `GET /v1/jobs/{job_id}`

**Purpose:** Poll job status and progress. Call this endpoint repeatedly until status is `completed` or `failed`.

**Response (Queued):** `200 OK`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "queued",
    "run_type": "preview",
    "progress_percent": 0,
    "current_step": "Waiting in queue",
    "submitted_at": "2026-02-17T10:30:45Z",
    "estimated_start": "2026-02-17T10:31:00Z"
  },
  "meta": { ... }
}
```

**Response (Processing):** `200 OK`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "processing",
    "run_type": "preview",
    "progress_percent": 67,
    "current_step": "Validating row 2 of 3",
    "submitted_at": "2026-02-17T10:30:45Z",
    "started_at": "2026-02-17T10:30:52Z",
    "estimated_completion": "2026-02-17T10:31:15Z"
  },
  "meta": { ... }
}
```

**Response (Preview Complete):** `200 OK`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "preview_complete",
    "run_type": "preview",
    "progress_percent": 100,
    "current_step": "Preview validation complete",
    "submitted_at": "2026-02-17T10:30:45Z",
    "started_at": "2026-02-17T10:30:52Z",
    "completed_at": "2026-02-17T10:31:08Z",
    "run_time_seconds": 16,
    "preview_results": {
      "rows_analyzed": 3,
      "total_rows_detected": 450,
      "sample_results": {
        "valid_count": 2,
        "invalid_count": 1,
        "confidence_score": 0.92
      }
    },
    "cost_estimate": {
      "estimated_total_cost_usd": 12.00,
      "estimated_cost_per_row_usd": 0.027,
      "estimated_time_minutes": 8.5,
      "breakdown": {
        "ai_calls": 450,
        "cache_hit_rate": 0.15
      }
    },
    "next_steps": {
      "approve_url": "/v1/jobs/session_20260217_103045_abc123/validate",
      "requires_approval": true
    }
  },
  "meta": { ... }
}
```

**Response (Full Validation Complete):** `200 OK`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "completed",
    "run_type": "validation",
    "progress_percent": 100,
    "submitted_at": "2026-02-17T10:30:45Z",
    "started_at": "2026-02-17T10:32:00Z",
    "completed_at": "2026-02-17T10:46:23Z",
    "run_time_seconds": 863,
    "results": {
      "rows_processed": 450,
      "columns_validated": 8,
      "valid_count": 423,
      "invalid_count": 27,
      "average_confidence": 0.94
    },
    "cost": {
      "charged_usd": 11.73,
      "ai_calls_made": 450,
      "cache_hit_rate": 0.18
    },
    "download": {
      "results_url": "/v1/jobs/session_20260217_103045_abc123/results"
    }
  },
  "meta": { ... }
}
```

**Response (Failed):** `200 OK`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "failed",
    "run_type": "validation",
    "progress_percent": 34,
    "submitted_at": "2026-02-17T10:30:45Z",
    "failed_at": "2026-02-17T10:35:12Z",
    "error": {
      "code": "validation_error",
      "message": "Invalid Excel file structure",
      "details": "Sheet 'Companies' not found. Available sheets: ['Sheet1', 'Data']"
    }
  },
  "meta": { ... }
}
```

**Headers (when processing):**
```
Retry-After: 10
```

**Status Values:**
- `queued` - Job accepted, waiting to start
- `processing` - Actively validating
- `preview_complete` - Preview done, awaiting approval for full validation
- `completed` - Validation complete, results available
- `failed` - Job failed with error

**Rate Limit:** 120 requests/minute

---

#### 2.3 Approve Full Validation

**Endpoint:** `POST /v1/jobs/{job_id}/validate`

**Purpose:** After reviewing preview results and cost estimate, approve the full validation job.

**Request:**
```json
{
  "approved_cost_usd": 12.00,
  "webhook_url": "https://your-app.com/webhooks/validation",
  "webhook_secret": "your_webhook_secret_123"
}
```

**Field Descriptions:**
- `approved_cost_usd` - Must match the estimated cost from preview (prevents surprise charges if estimate changed)
- `webhook_url` - Optional, can override/add webhook for full validation
- `webhook_secret` - Optional webhook HMAC secret

**Response:** `202 Accepted`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "queued",
    "run_type": "validation",
    "approved_cost_usd": 12.00,
    "credits_reserved": 12.00,
    "current_balance_usd": 88.00,
    "urls": {
      "status": "/v1/jobs/session_20260217_103045_abc123",
      "results": "/v1/jobs/session_20260217_103045_abc123/results"
    }
  },
  "meta": { ... }
}
```

**Error Responses:**

**409 Conflict** - Cost mismatch (quote changed)
```json
{
  "success": false,
  "error": {
    "code": "cost_mismatch",
    "message": "Approved cost does not match current estimate",
    "details": {
      "approved_cost_usd": 12.00,
      "current_estimate_usd": 13.50,
      "reason": "Estimate updated based on data analysis"
    }
  },
  "meta": { ... }
}
```

**402 Payment Required** - Insufficient balance
```json
{
  "success": false,
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

**Rate Limit:** 20 requests/minute

---

#### 2.4 Get Job Results

**Endpoint:** `GET /v1/jobs/{job_id}/results`

**Purpose:** Get download URL for completed validation results.

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "job_id": "session_20260217_103045_abc123",
    "status": "completed",
    "results": {
      "download_url": "https://s3.amazonaws.com/hyperplexity-storage/downloads/abc123/results.zip?X-Amz-Expires=3600&...",
      "download_expires_at": "2026-02-17T11:46:23Z",
      "file_format": "zip",
      "file_size_bytes": 1048576,
      "contents": [
        "Companies_validated.xlsx",
        "validation_report.json",
        "summary.txt"
      ]
    },
    "summary": {
      "rows_processed": 450,
      "columns_validated": 8,
      "valid_count": 423,
      "invalid_count": 27,
      "average_confidence": 0.94,
      "run_time_seconds": 863,
      "cost_usd": 11.73
    }
  },
  "meta": { ... }
}
```

**Error Responses:**

**404 Not Found** - Job not complete
```json
{
  "success": false,
  "error": {
    "code": "results_not_ready",
    "message": "Validation results are not yet available",
    "details": {
      "current_status": "processing",
      "progress_percent": 67,
      "status_url": "/v1/jobs/session_20260217_103045_abc123"
    }
  },
  "meta": { ... }
}
```

**Rate Limit:** 60 requests/minute

---

### 3. Account Management

#### 3.1 Get Account Balance

**Endpoint:** `GET /v1/account/balance`

**Purpose:** Check current credit balance and usage statistics.

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "balance_usd": 88.27,
    "currency": "USD",
    "account_status": "active",
    "usage_this_month": {
      "total_spent_usd": 156.73,
      "validations_completed": 12,
      "total_rows_processed": 5400
    },
    "last_transaction": {
      "type": "debit",
      "amount_usd": 11.73,
      "description": "Validation job: session_20260217_103045_abc123",
      "timestamp": "2026-02-17T10:46:23Z"
    }
  },
  "meta": { ... }
}
```

**Rate Limit:** 60 requests/minute

---

#### 3.2 Get Account Usage History

**Endpoint:** `GET /v1/account/usage`

**Purpose:** Get detailed usage and billing history.

**Query Parameters:**
- `start_date` - ISO 8601 date (default: 30 days ago)
- `end_date` - ISO 8601 date (default: today)
- `limit` - Number of records (default: 100, max: 1000)
- `offset` - Pagination offset (default: 0)

**Request:**
```
GET /v1/account/usage?start_date=2026-02-01&end_date=2026-02-17&limit=10
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "period": {
      "start_date": "2026-02-01",
      "end_date": "2026-02-17"
    },
    "summary": {
      "total_spent_usd": 156.73,
      "total_validations": 12,
      "total_rows_processed": 5400,
      "average_cost_per_validation": 13.06
    },
    "transactions": [
      {
        "transaction_id": "txn_abc123",
        "type": "debit",
        "amount_usd": 11.73,
        "job_id": "session_20260217_103045_abc123",
        "description": "Validation: 450 rows",
        "timestamp": "2026-02-17T10:46:23Z"
      },
      {
        "transaction_id": "txn_abc122",
        "type": "credit",
        "amount_usd": 100.00,
        "description": "Account recharge via Squarespace",
        "timestamp": "2026-02-15T14:20:00Z"
      }
    ],
    "pagination": {
      "limit": 10,
      "offset": 0,
      "total_count": 47,
      "has_more": true
    }
  },
  "meta": { ... }
}
```

**Rate Limit:** 60 requests/minute

---

### 4. WebSocket (Real-time Progress)

**Endpoint:** `wss://api.hyperplexity.ai/v1/progress`

**Purpose:** Receive real-time progress updates for jobs via WebSocket connection.

**Connection:**
```javascript
const ws = new WebSocket(
  'wss://api.hyperplexity.ai/v1/progress?job_id=session_xxx&api_key=hpx_live_xxx'
);

ws.onopen = () => {
  console.log('Connected to job progress stream');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Progress update:', message);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Connection closed');
};
```

**Message Types:**

**Connected:**
```json
{
  "type": "connected",
  "job_id": "session_xxx",
  "timestamp": "2026-02-17T10:30:52Z"
}
```

**Progress Update:**
```json
{
  "type": "progress",
  "job_id": "session_xxx",
  "progress_percent": 45,
  "current_step": "Validating row 150 of 450",
  "estimated_completion": "2026-02-17T10:45:00Z",
  "timestamp": "2026-02-17T10:35:30Z"
}
```

**Completion:**
```json
{
  "type": "completed",
  "job_id": "session_xxx",
  "status": "completed",
  "results_url": "/v1/jobs/session_xxx/results",
  "summary": {
    "rows_processed": 450,
    "run_time_seconds": 863,
    "cost_usd": 11.73
  },
  "timestamp": "2026-02-17T10:46:23Z"
}
```

**Error:**
```json
{
  "type": "error",
  "job_id": "session_xxx",
  "error": {
    "code": "validation_error",
    "message": "Processing failed"
  },
  "timestamp": "2026-02-17T10:35:12Z"
}
```

**Ping/Pong (Keepalive):**
```json
// Client sends
{"type": "ping"}

// Server responds
{"type": "pong"}
```

**Connection Limits:**
- Max 5 concurrent WebSocket connections per API key
- Idle timeout: 15 minutes
- Ping interval: 30 seconds recommended

---

### 5. Webhooks (Event Notifications)

**Purpose:** Receive HTTP POST notifications when jobs complete.

**Configuration:** Provide `webhook_url` and optional `webhook_secret` when creating/approving jobs.

**Security:** All webhooks include HMAC-SHA256 signature for verification.

**Webhook Request (Job Complete):**
```
POST https://your-app.com/webhooks/validation
Content-Type: application/json
X-Hyperplexity-Event: job.completed
X-Hyperplexity-Signature: sha256=abc123def456...
X-Hyperplexity-Job-Id: session_20260217_103045_abc123
X-Hyperplexity-Timestamp: 1739796383

{
  "event": "job.completed",
  "api_version": "v1",
  "job_id": "session_20260217_103045_abc123",
  "status": "completed",
  "submitted_at": "2026-02-17T10:30:45Z",
  "completed_at": "2026-02-17T10:46:23Z",
  "run_time_seconds": 863,
  "results": {
    "rows_processed": 450,
    "columns_validated": 8,
    "download_url": "https://s3.amazonaws.com/.../results.zip?...",
    "download_expires_at": "2026-02-17T11:46:23Z"
  },
  "cost": {
    "charged_usd": 11.73
  }
}
```

**Webhook Request (Job Failed):**
```
POST https://your-app.com/webhooks/validation
Content-Type: application/json
X-Hyperplexity-Event: job.failed
X-Hyperplexity-Signature: sha256=abc123def456...
X-Hyperplexity-Job-Id: session_20260217_103045_abc123
X-Hyperplexity-Timestamp: 1739796383

{
  "event": "job.failed",
  "api_version": "v1",
  "job_id": "session_20260217_103045_abc123",
  "status": "failed",
  "submitted_at": "2026-02-17T10:30:45Z",
  "failed_at": "2026-02-17T10:35:12Z",
  "error": {
    "code": "validation_error",
    "message": "Invalid Excel file structure"
  }
}
```

**Signature Verification (Python):**
```python
import hmac
import hashlib

def verify_webhook_signature(payload_body, signature_header, secret):
    """
    Verify webhook signature

    Args:
        payload_body: Raw request body (bytes)
        signature_header: Value of X-Hyperplexity-Signature header
        secret: Your webhook secret

    Returns:
        bool: True if signature is valid
    """
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    # signature_header format: "sha256=abc123..."
    provided_signature = signature_header.split('=', 1)[1]

    return hmac.compare_digest(expected_signature, provided_signature)
```

**Webhook Retry Logic:**
- Retry on non-2xx response
- Exponential backoff: 60s, 300s, 900s
- Max 3 attempts
- Timeout: 10 seconds per attempt

**Expected Response:**
Your webhook endpoint should return `200 OK` to acknowledge receipt.

**Security Requirements:**
- Webhook URL must use HTTPS
- No private IP addresses (SSRF protection)
- No localhost or internal domains

---

## Authentication & Security

### API Key Format

```
Production:  hpx_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
Test:        hpx_test_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
Internal:    hpx_int_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
```

**Components:**
- Prefix: `hpx_` (Hyperplexity)
- Tier: `live_` (production) / `test_` (sandbox) / `int_` (internal)
- Random: 40 characters (240 bits entropy)

**Security:**
- Keys are hashed with HMAC-SHA256 before storage
- Raw key shown only once upon creation
- Prefix stored for user display (`hpx_live_a1b2c3d4...`)

### API Key Storage

**DynamoDB Table:** `perplexity-validator-api-keys`

```json
{
  "api_key_hash": "sha256_hash_of_full_key",
  "key_prefix": "hpx_live_a1b2c3d4",
  "email": "user@example.com",
  "key_name": "Production API Key",
  "tier": "live",
  "scopes": ["validate", "config", "account:read"],
  "rate_limit_rpm": 60,
  "rate_limit_rpd": 1000,
  "created_at": "2026-02-17T10:00:00Z",
  "last_used_at": "2026-02-17T10:30:45Z",
  "expires_at": null,
  "is_active": true,
  "revoked_at": null,
  "revoked_reason": null,
  "ip_whitelist": [],
  "cors_origins": ["*"],
  "metadata": {
    "created_via": "web_ui",
    "user_agent": "Mozilla/5.0..."
  }
}
```

### Rate Limiting

**Per-Key Limits (Default):**

| Tier | Requests/Minute | Requests/Day | Notes |
|------|-----------------|--------------|-------|
| `live` | 60 | 1,000 | Standard developer tier |
| `live` (enterprise) | 300 | 10,000 | Contact sales |
| `test` | 10 | 100 | Intentionally restricted |
| `int` (internal) | 600 | unlimited | No daily cap |

**Rate Limit Headers:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 47
X-RateLimit-Reset: 1739836800
```

**429 Response:**
```json
{
  "success": false,
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Too many requests. Please retry after 42 seconds.",
    "details": {
      "limit": 60,
      "window": "minute",
      "retry_after_seconds": 42,
      "reset_at": "2026-02-17T10:32:00Z"
    }
  },
  "meta": { ... }
}
```

### CORS Policy

**Default:** Wildcard (`*`) for all API keys

**Custom (Future):** Per-key configuration
```json
{
  "cors_origins": [
    "https://app.example.com",
    "https://dev.example.com"
  ]
}
```

### Security Features

1. **HTTPS Only** - No HTTP connections accepted
2. **API Key Hashing** - HMAC-SHA256, never store raw keys
3. **IP Whitelisting** - Optional per-key IP restrictions
4. **Webhook SSRF Protection** - No private IPs, localhost, or internal domains
5. **HMAC Webhook Signatures** - Client-verifiable authenticity
6. **Rate Limiting** - Per-key burst and sustained limits
7. **Audit Logging** - All API key usage tracked
8. **Anomaly Detection** - Alert on unusual usage patterns

---

## Account Management System

### Overview

Web UI page at `/account` for managing API keys, viewing usage, and recharging credits.

### URL-Based Behavior

**Page URLs:**
- `/` - Main validation interface (existing)
- `/account` - Account management dashboard (new)

**Detection:**
```javascript
// frontend/src/js/01-init.js
if (window.location.pathname === '/account' || window.location.hash === '#account') {
  // Load account management UI
  initAccountPage();
} else {
  // Load main validation UI (existing)
  initMainApp();
}
```

### Account Page Features

#### 1. General Account Info
- Current balance display
- Usage this month (spend, validations, rows)
- Account status (active, suspended, etc.)
- Email address
- Account created date

#### 2. API Keys Section

**Display:**
- List of all API keys (active and revoked)
- For each key show:
  - Key prefix (`hpx_live_a1b2c3d4...`)
  - Name/label
  - Tier (live/test)
  - Created date
  - Last used date
  - Status (active/revoked)
  - Scopes/permissions
  - Usage stats (requests today, this month)

**Actions:**
- **Create New Key** button
  - Modal with fields:
    - Key name (required)
    - Tier (live/test)
    - Scopes (checkboxes)
    - IP whitelist (optional, comma-separated)
    - Expiration (optional, date picker)
  - On success: Show raw key ONCE in copyable modal with warning
  - After dismissal: Only prefix shown
- **Revoke Key** button per key
  - Confirmation dialog
  - Optional revocation reason
- **View Usage** link per key
  - Detailed usage statistics

#### 3. Usage & Billing Section

**Displays:**
- Current month spend breakdown
- Validation history table (last 20)
- Transaction history (credits/debits)
- Cost trends chart (daily spend)

**Filters:**
- Date range picker
- Transaction type (all/credits/debits)
- Export as CSV button

#### 4. Recharge Section

**Display:**
- Current balance (prominent)
- Recharge amount selector ($10, $50, $100, custom)
- Payment method (redirect to Squarespace or Stripe)

**Flow:**
1. User selects amount
2. Click "Recharge Account"
3. Redirect to payment processor
4. On success: Return to /account with success message
5. Balance updates immediately

### API Actions for Account Page

All use existing JWT authentication (web UI users):

| Action | HTTP Method | Endpoint | Purpose |
|--------|-------------|----------|---------|
| `createApiKey` | POST | /validate | Generate new API key |
| `listApiKeys` | POST | /validate | List user's API keys |
| `revokeApiKey` | POST | /validate | Revoke a key |
| `updateApiKey` | POST | /validate | Update key metadata |
| `getApiKeyUsage` | POST | /validate | Get per-key usage stats |
| `getAccountBalance` | POST | /validate | Get current balance (existing) |
| `getUserStats` | POST | /validate | Get usage history (existing) |

### UI Mockup

```
┌──────────────────────────────────────────────────────────────┐
│  Hyperplexity - Account Management                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Account Overview                                    │   │
│  │  ─────────────────                                   │   │
│  │  Email: user@example.com                             │   │
│  │  Current Balance: $88.27 USD      [Recharge Account] │   │
│  │  This Month: $156.73 spent • 12 validations          │   │
│  │  Account Status: Active since Feb 1, 2026            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  API Keys                          [+ New API Key]   │   │
│  │  ─────────                                            │   │
│  │                                                       │   │
│  │  📌 Production API Key                                │   │
│  │     hpx_live_a1b2c3d4...                              │   │
│  │     Created: Feb 5, 2026 • Last used: 2 hours ago    │   │
│  │     Tier: live • Scopes: validate, account:read      │   │
│  │     Usage today: 47 requests                          │   │
│  │     [View Usage] [Revoke]                             │   │
│  │                                                       │   │
│  │  📌 Test API Key                                      │   │
│  │     hpx_test_x9y8z7w6...                              │   │
│  │     Created: Feb 3, 2026 • Last used: never          │   │
│  │     Tier: test • Scopes: validate                    │   │
│  │     [View Usage] [Revoke]                             │   │
│  │                                                       │   │
│  │  ❌ Revoked Key (Feb 10, 2026)                        │   │
│  │     hpx_live_k5j4h3g2...                              │   │
│  │     Reason: Security rotation                         │   │
│  │                                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Usage & Billing                                     │   │
│  │  ────────────────                                     │   │
│  │                                                       │   │
│  │  [Date Range: Last 30 days ▼] [Export CSV]           │   │
│  │                                                       │   │
│  │  Recent Validations:                                  │   │
│  │  ┌─────────┬──────────┬──────┬────────┬─────────┐   │   │
│  │  │ Date    │ Job ID   │ Rows │ Cost   │ Status  │   │   │
│  │  ├─────────┼──────────┼──────┼────────┼─────────┤   │   │
│  │  │ Feb 17  │ sess_abc │ 450  │ $11.73 │ ✓ Done  │   │   │
│  │  │ Feb 16  │ sess_def │ 320  │ $8.50  │ ✓ Done  │   │   │
│  │  │ Feb 15  │ sess_ghi │ 890  │ $19.20 │ ✓ Done  │   │   │
│  │  └─────────┴──────────┴──────┴────────┴─────────┘   │   │
│  │                                                       │   │
│  │  Transaction History:                                 │   │
│  │  • Feb 17: -$11.73 (Validation)                       │   │
│  │  • Feb 16: -$8.50 (Validation)                        │   │
│  │  • Feb 15: +$100.00 (Recharge via Squarespace)       │   │
│  │                                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 0: Branch & Infrastructure Setup
**Status:** ✅ COMPLETE (2026-02-18)
**Branch:** `api`

**Completed:**
1. ✅ `api` branch created from `master`
2. ✅ API design document created (`docs/EXTERNAL_API_DESIGN.md`)
3. ✅ DynamoDB table creation code added to `deployment/create_interface_package.py`
4. ✅ SSM parameter auto-provisioning added to `deployment/create_interface_package.py`

**Deferred to Phase 2 (requires code before infra):**
- Second API Gateway in AWS (needs `api_handler.py` deployed first)

---

### Phase 1: API Key Infrastructure
**Status:** ✅ COMPLETE (2026-02-18)
**Commit:** `2fa274b0`

**Files Created:**
1. `src/lambdas/interface/utils/api_key_manager.py`
   - `generate_api_key(tier)` — `hpx_{tier}_{40 url-safe chars}`
   - `hash_api_key(raw_key)` — HMAC-SHA256 via SSM secret
   - `authenticate_api_key(raw_key)` — DynamoDB lookup + active/expiry check
   - `create_api_key_record(...)`, `list_api_keys(email)`, `revoke_api_key(...)`, `update_api_key(...)`, `get_api_key_usage(...)`
   - SSM secret cached in-process; env var `API_KEY_HMAC_SECRET` overrides for local dev

2. `src/lambdas/interface/actions/api_key_management.py`
   - Dispatches: `createApiKey`, `listApiKeys`, `revokeApiKey`, `updateApiKey`, `getApiKeyUsage`
   - Max 10 active keys per user enforced
   - Scope validation on both create and update
   - Revoked-key guard on update

**Files Modified:**
1. `src/shared/dynamodb_schemas.py`
   - Added `create_api_keys_table()` — PAY_PER_REQUEST, `email-index` GSI
   - Added `create_api_key_usage_table()` — PAY_PER_REQUEST, composite key `(api_key_hash, window)`, TTL on `ttl` attribute

2. `src/lambdas/interface/handlers/http_handler.py`
   - Added 5 API key actions to protected-action routing block (lazy-loaded)

3. `deployment/create_interface_package.py`
   - `setup_dynamodb_tables()` — creates both API key tables
   - `setup_ssm_parameters()` — creates `/perplexity-validator/api-key-hmac-secret` if absent
   - `LAMBDA_CONFIG` — adds `API_KEY_HMAC_SECRET_PARAM` env var

**Implementation Notes (changes from original plan):**
- Display prefix is 18 chars (`hpx_live_` + 9 random chars), not 16 as originally implied
- `rate_limit_rpd: 0` means unlimited for `int`-tier keys — downstream rate-limit code must treat 0 as no cap
- `last_used_at` updated synchronously on each auth call (small latency cost); refactor to async in Phase 6 if needed
- 6 bugs fixed post-implementation (see commit `2fa274b0`): BillingMode in GSI spec, TTL-before-waiter, unused imports, implicit conditions import, missing scope validation on update, missing revoked-key guard on update

**Deliverables:**
- ✅ API key CRUD available via existing web UI (JWT auth)
- ✅ Keys can authenticate future external API requests
- ✅ DynamoDB + SSM provisioning integrated into deploy script

---

### Phase 2: RESTful API Handler
**Status:** 🔲 NEXT
**Dependencies:** Phase 1 ✅

**Context — how the Lambda currently routes:**
`interface_lambda_function.py` detects the event source by `'httpMethod' in event` (REST API v1 payload format). A second API Gateway can be distinguished by comparing `event['requestContext']['apiId']` to the env var `API_GATEWAY_EXTERNAL_API_ID`. HTTP API v2 events use `'version': '2.0'` instead of `'httpMethod'`.

**Files to Create:**
1. `src/lambdas/interface/handlers/api_handler.py`
   - Authenticate via `api_key_manager.authenticate_api_key()` (Bearer token from `Authorization` header)
   - Route RESTful paths → existing action handlers:

     | Method | Path | → Action / Handler |
     |--------|------|--------------------|
     | POST | `/v1/uploads/presigned` | `presigned_upload.request_presigned_url()` |
     | POST | `/v1/jobs` | `start_preview.handle_start_preview()` |
     | GET | `/v1/jobs/{job_id}` | `status_check.handle_get_status()` |
     | POST | `/v1/jobs/{job_id}/validate` | `start_preview.handle_approve_validation()` (new function) |
     | GET | `/v1/jobs/{job_id}/results` | `status_check.handle_get_results()` (new function) |
     | GET | `/v1/account/balance` | `account_balance.handle()` |
     | GET | `/v1/account/usage` | `user_stats.handle()` |

   - Wrap all responses in standard envelope `{success, data, error, meta}`
   - Return proper HTTP status codes (202 for queued jobs, 402 for insufficient credits, etc.)
   - Add `X-RateLimit-*` headers on every response
   - Add `Retry-After` header when job is processing

2. `src/lambdas/interface/utils/rate_limiter_api.py`
   - Per-key rate limiting using `perplexity-validator-api-key-usage` table
   - Sliding window: minute + day counters via atomic `ADD` on `request_count`
   - Returns `(allowed: bool, remaining: int, reset_at: str)`
   - `0` in `rate_limit_rpd` means unlimited (internal keys)

**Files to Modify:**
1. `src/interface_lambda_function.py`
   - Add detection for external API Gateway: check `event.get('requestContext', {}).get('apiId') == os.environ.get('API_GATEWAY_EXTERNAL_API_ID')`
   - Route matching events to `api_handler.handle(event, context)` instead of `http_handler.handle()`

2. `src/lambdas/interface/actions/start_preview.py`
   - Add `handle_approve_validation(request_data, context)` — approves preview → queues full run
   - Persist `webhook_url` + `webhook_secret` to DynamoDB run record (for Phase 3)
   - Return standard API envelope from `handle_start_preview()` when called via API context

3. `src/lambdas/interface/actions/status_check.py`
   - Add `handle_get_results(request_data, context)` — returns presigned download URL if `status == completed`
   - Enhance existing status response to include `progress_percent`, `estimated_completion`, `cost_estimate`

4. `deployment/create_interface_package.py`
   - Add `API_GATEWAY_EXTERNAL_API_ID` to `LAMBDA_CONFIG` env vars (resolved at deploy time, same pattern as `WEBSOCKET_API_URL`)
   - Add `deploy_external_api_gateway()` function using the existing `setup_api_gateway()` as a template

**New env vars needed in Lambda:**
```
API_GATEWAY_EXTERNAL_API_ID=<resolved at deploy time>
```

**Endpoints to implement:**
- `POST /v1/uploads/presigned`
- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `POST /v1/jobs/{job_id}/validate`
- `GET /v1/jobs/{job_id}/results`
- `GET /v1/account/balance`
- `GET /v1/account/usage`

**Testing:**
- Auth: valid key → 200; revoked key → 401; expired key → 401; wrong prefix → 401
- Rate limit: exceed RPM → 429 with `Retry-After`
- Insufficient balance: submit job with $0 balance → 402
- Full flow: presigned → upload → POST /v1/jobs → poll → approve → poll → GET results
- Error responses: missing fields → 400; unknown job_id → 404

**Deliverables:**
- External API Gateway live at `api.hyperplexity.ai/v1`
- Full validation workflow accessible via API key
- Rate limiting enforced per-key

---

### Phase 3: Async Notifications
**Timeline:** Days 8-10
**Dependencies:** Phase 2

**Files to Create:**
1. `/src/shared/webhook_client.py`
   - Webhook delivery with HMAC signing
   - SSRF protection
   - Retry logic

**Files to Modify:**
1. `/src/shared/dynamodb_schemas.py`
   - Add webhook fields to run records
   - Add webhook helper functions

2. `/src/lambdas/interface/actions/status_check.py`
   - Enhance response schema for API
   - Add `Retry-After` headers

3. `/src/lambdas/interface/handlers/background_handler.py`
   - Add webhook delivery on completion
   - Add `_deliver_webhook_notification()` helper

4. `/src/lambdas/interface/handlers/sqs_handler.py`
   - Add webhook retry routing

5. `/src/lambdas/websocket/websocket_handler.py`
   - Add API key authentication for WebSocket
   - Support `api_key` query parameter

**Features Implemented:**
- Webhook notifications
- Webhook signature verification
- Webhook retry logic (3 attempts)
- Enhanced polling responses
- WebSocket support for API clients (optional)

**Testing:**
- Test webhook delivery on completion
- Test webhook signature generation
- Test retry logic on failure
- Test SSRF protection
- Test WebSocket with API key auth

**Deliverables:**
- Multiple notification channels working
- Webhooks with retry logic
- WebSocket accessible via API key

---

### Phase 4: Account Management UI
**Timeline:** Days 11-14
**Dependencies:** Phase 1

**Files to Modify:**
1. `/frontend/src/js/01-init.js`
   - Add URL detection for `/account`
   - Route to account page initialization

2. `/frontend/src/js/14-account.js`
   - Add API key management section
   - Add key creation modal
   - Add key revocation flow
   - Add usage statistics display

3. `/frontend/src/html/index.html` (or template)
   - Add account page structure
   - Add account page styles

**Features Implemented:**
- API key list display
- Create new key modal
- Show raw key once on creation
- Revoke key with confirmation
- View per-key usage statistics
- General account info display
- Transaction history
- Usage charts

**Testing:**
- UI tests for key creation flow
- UI tests for key revocation
- Test that raw key shown only once
- Test usage statistics accuracy

**Deliverables:**
- Complete account management UI
- Users can self-service API keys
- Usage visibility for transparency

---

### Phase 5: Documentation & Polish
**Timeline:** Days 15-16
**Dependencies:** Phases 2-4

**Documentation to Create:**
1. `docs/API.md` - External API documentation
   - Getting started guide
   - Authentication
   - Endpoint reference
   - Code examples (Python, JavaScript, curl)
   - Error handling
   - Webhook verification examples
   - Rate limiting info

2. `docs/API_KEY_MANAGEMENT.md` - Internal operations guide
   - Key security model
   - Rotation procedures
   - Revocation procedures
   - Abuse monitoring
   - Support procedures

3. `docs/WEBHOOKS.md` - Webhook integration guide
   - Webhook event types
   - Signature verification
   - Best practices
   - Example implementations

**Code Polish:**
- Add comprehensive logging
- Add CloudWatch metrics
- Add error monitoring
- Code cleanup and comments

**Testing:**
- End-to-end integration tests
- Load testing (100 concurrent requests)
- Security testing (penetration testing)
- Documentation accuracy review

**Deliverables:**
- Complete API documentation
- Internal operations guide
- Production-ready code

---

### Phase 6: Launch Preparation
**Timeline:** Days 17-18
**Dependencies:** All previous phases

**Tasks:**
1. Security review
   - Penetration testing
   - API key leakage testing
   - SSRF testing
   - Rate limit testing

2. Performance testing
   - Load test: 1000 requests/minute
   - WebSocket connection limits
   - DynamoDB read/write capacity
   - Lambda concurrent execution limits

3. Monitoring setup
   - CloudWatch dashboards
   - Alarms for errors
   - Alarms for rate limit abuse
   - Usage metrics

4. Beta testing
   - Internal team testing
   - Select beta testers (if applicable)
   - Feedback collection

5. Launch checklist
   - Documentation published
   - API Gateway live
   - Monitoring active
   - Support procedures documented
   - Announcement prepared

**Deliverables:**
- Production-ready system
- Monitoring in place
- Beta feedback incorporated
- Launch plan finalized

---

## Testing Strategy

### Unit Tests

**API Key Manager** (`test_api_key_manager.py`):
- Key generation format validation
- HMAC hashing correctness
- Authentication success/failure
- Scope validation
- IP whitelist checking
- Key expiration handling

**Webhook Client** (`test_webhook_client.py`):
- HMAC signature generation
- SSRF protection (reject private IPs)
- URL validation (HTTPS only)
- Payload size limits
- Retry logic

### Integration Tests

**API Flow Tests** (`test_api_flow.py`):
```python
def test_complete_validation_flow():
    # 1. Create API key
    api_key = create_test_api_key()

    # 2. Request presigned URL
    presigned = request_presigned_url(api_key, "test.xlsx", 1024)

    # 3. Upload file to S3
    upload_file_to_s3(presigned['presigned_url'], "fixtures/test.xlsx")

    # 4. Submit validation job
    job = create_validation_job(api_key, presigned, test_config)
    assert job['status'] == 'queued'

    # 5. Poll until complete
    status = poll_until_complete(api_key, job['job_id'], timeout=300)
    assert status['status'] == 'completed'

    # 6. Get results
    results = get_job_results(api_key, job['job_id'])
    assert 'download_url' in results

    # 7. Verify balance deducted
    balance_after = get_account_balance(api_key)
    assert balance_after < initial_balance
```

**Webhook Tests** (`test_webhooks.py`):
```python
def test_webhook_delivery():
    # Set up mock webhook server
    webhook_server = MockWebhookServer()

    # Submit job with webhook
    job = create_validation_job(
        api_key,
        presigned,
        config,
        webhook_url=webhook_server.url,
        webhook_secret="test_secret"
    )

    # Wait for job completion
    wait_for_completion(job['job_id'])

    # Verify webhook received
    webhook = webhook_server.get_received_webhook()
    assert webhook is not None
    assert webhook['event'] == 'job.completed'

    # Verify signature
    assert verify_webhook_signature(
        webhook['body'],
        webhook['headers']['X-Hyperplexity-Signature'],
        "test_secret"
    )
```

### Load Tests

**Rate Limiting Test:**
```python
def test_rate_limiting():
    # Attempt 100 requests in 1 minute (limit is 60/min)
    api_key = create_test_api_key(rate_limit_rpm=60)

    responses = []
    for i in range(100):
        resp = get_account_balance(api_key)
        responses.append(resp.status_code)

    # First 60 should succeed
    assert responses[:60].count(200) == 60

    # Remaining should be rate limited
    assert responses[60:].count(429) == 40
```

**Concurrent Jobs Test:**
```python
async def test_concurrent_validations():
    # Submit 50 jobs concurrently
    jobs = []
    for i in range(50):
        job = await submit_validation_job(api_key, f"test_{i}.xlsx")
        jobs.append(job)

    # All should be queued successfully
    assert all(job['status'] == 'queued' for job in jobs)

    # Wait for all to complete
    results = await asyncio.gather(*[
        poll_until_complete(api_key, job['job_id'])
        for job in jobs
    ])

    # All should complete successfully
    assert all(r['status'] == 'completed' for r in results)
```

### Security Tests

**API Key Leakage:**
- Verify raw keys never in logs
- Verify raw keys never in error responses
- Verify raw keys never in CloudWatch

**SSRF Protection:**
```python
def test_ssrf_protection():
    # Attempt webhook to private IPs
    private_urls = [
        "http://127.0.0.1/webhook",
        "http://localhost/webhook",
        "http://10.0.0.1/webhook",
        "http://192.168.1.1/webhook",
        "http://172.16.0.1/webhook"
    ]

    for url in private_urls:
        job = create_validation_job(
            api_key, presigned, config,
            webhook_url=url
        )
        assert job['error']['code'] == 'invalid_webhook_url'
```

---

## Deployment

### Infrastructure (AWS)

**API Gateways:**
1. **Web UI Gateway** (existing)
   - Endpoint: `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod`
   - Routes: `/`, `/validate`, `/health`
   - Integrated with Interface Lambda

2. **External API Gateway** (new)
   - Endpoint: `https://api.hyperplexity.ai` (custom domain)
   - Base path: `/v1`
   - Routes: `/v1/uploads/*`, `/v1/jobs/*`, `/v1/account/*`
   - Integrated with SAME Interface Lambda
   - CORS: Wildcard

**Lambda Functions:**
- Interface Lambda (existing, modified)
- Config Lambda (existing, unchanged)
- Validation Lambda (existing, unchanged)

**DynamoDB Tables (new):**
- `perplexity-validator-api-keys`
- `perplexity-validator-api-key-usage`

**SSM Parameters (new):**
- `/perplexity-validator/api-key-hmac-secret`

**WebSocket API:**
- Endpoint: `wss://api.hyperplexity.ai/v1/progress`
- Supports both session-based (web UI) and API key auth

### Deployment Script Updates

**File:** `/src/create_interface_package.py`

Add support for deploying both API Gateways:

```python
# create_interface_package.py (modifications)

def deploy_api_gateways():
    """Deploy both web UI and external API gateways"""

    # Existing web UI gateway
    deploy_web_ui_gateway()

    # New external API gateway
    deploy_external_api_gateway()

def deploy_external_api_gateway():
    """Create/update external API gateway"""

    api_gateway = boto3.client('apigatewayv2')

    # Create REST API
    api = api_gateway.create_api(
        Name='hyperplexity-external-api',
        ProtocolType='HTTP',
        CorsConfiguration={
            'AllowOrigins': ['*'],
            'AllowMethods': ['GET', 'POST', 'OPTIONS'],
            'AllowHeaders': ['Authorization', 'Content-Type']
        }
    )

    # Create routes
    routes = [
        ('POST', '/v1/uploads/presigned'),
        ('POST', '/v1/jobs'),
        ('GET', '/v1/jobs/{job_id}'),
        ('POST', '/v1/jobs/{job_id}/validate'),
        ('GET', '/v1/jobs/{job_id}/results'),
        ('GET', '/v1/account/balance'),
        ('GET', '/v1/account/usage')
    ]

    for method, path in routes:
        create_route(api['ApiId'], method, path, lambda_arn)

    # Create custom domain
    create_custom_domain('api.hyperplexity.ai', api['ApiId'])
```

### Environment Variables

**Interface Lambda:**
```bash
# Existing
S3_UNIFIED_BUCKET=hyperplexity-storage
JWT_SECRET_KEY=<from_ssm>
DEPLOYMENT_ENVIRONMENT=prod

# New
API_GATEWAY_WEB_UI_ID=abc123xyz
API_GATEWAY_EXTERNAL_API_ID=def456uvw
API_KEY_HMAC_SECRET=<from_ssm>
```

### Rollback Plan

1. **API Gateway**: Keep old version, update DNS to point back
2. **Lambda**: Use versioning and aliases, instant rollback
3. **DynamoDB**: Tables are additive, no schema changes to existing
4. **Frontend**: Deploy account page as feature flag, can disable instantly

---

## Appendix

### A. Configuration Schema

**Validation Config Structure:**
```json
{
  "version": "1.0",
  "tables": [
    {
      "name": "Companies",
      "sheet_name": "Sheet1",
      "columns": {
        "Company Name": {
          "validation_type": "text",
          "required": true,
          "ai_prompt": "Verify this is a valid company name"
        },
        "Website": {
          "validation_type": "url",
          "required": false,
          "ai_prompt": "Check if URL is valid and accessible"
        },
        "Email": {
          "validation_type": "email",
          "required": true,
          "ai_prompt": "Validate email format and domain"
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

### B. Example API Usage (Python)

```python
import requests
import hmac
import hashlib
import time

class HyperplexityClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.hyperplexity.ai/v1"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def validate_file(self, filepath, config, webhook_url=None, webhook_secret=None):
        """Complete validation workflow"""

        # Step 1: Get presigned URL
        with open(filepath, 'rb') as f:
            file_size = len(f.read())

        presigned_resp = requests.post(
            f"{self.base_url}/uploads/presigned",
            headers=self._headers(),
            json={
                "filename": filepath.split('/')[-1],
                "file_size": file_size,
                "file_type": "excel"
            }
        )
        presigned_resp.raise_for_status()
        presigned_data = presigned_resp.json()['data']

        # Step 2: Upload to S3
        with open(filepath, 'rb') as f:
            upload_resp = requests.put(
                presigned_data['presigned_url'],
                data=f,
                headers={'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
            )
        upload_resp.raise_for_status()

        # Step 3: Create validation job
        job_resp = requests.post(
            f"{self.base_url}/jobs",
            headers=self._headers(),
            json={
                "session_id": presigned_data['session_id'],
                "upload_id": presigned_data['upload_id'],
                "s3_key": presigned_data['s3_key'],
                "config": config,
                "preview_rows": 3,
                "webhook_url": webhook_url,
                "webhook_secret": webhook_secret,
                "notify_method": "webhook" if webhook_url else "poll"
            }
        )
        job_resp.raise_for_status()
        job_data = job_resp.json()['data']

        print(f"Job created: {job_data['job_id']}")
        print(f"Status URL: {job_data['urls']['status']}")

        if webhook_url:
            print(f"Webhook will be called at: {webhook_url}")
            return job_data

        # Step 4: Poll for preview completion
        job_id = job_data['job_id']
        while True:
            status_resp = requests.get(
                f"{self.base_url}/jobs/{job_id}",
                headers=self._headers()
            )
            status_resp.raise_for_status()
            status = status_resp.json()['data']

            print(f"Status: {status['status']} ({status['progress_percent']}%)")

            if status['status'] == 'preview_complete':
                print(f"Preview complete! Estimated cost: ${status['cost_estimate']['estimated_total_cost_usd']}")
                break
            elif status['status'] == 'failed':
                raise Exception(f"Job failed: {status['error']}")

            time.sleep(10)

        # Step 5: Approve full validation
        approve_resp = requests.post(
            f"{self.base_url}/jobs/{job_id}/validate",
            headers=self._headers(),
            json={
                "approved_cost_usd": status['cost_estimate']['estimated_total_cost_usd']
            }
        )
        approve_resp.raise_for_status()

        print("Full validation started...")

        # Step 6: Poll for completion
        while True:
            status_resp = requests.get(
                f"{self.base_url}/jobs/{job_id}",
                headers=self._headers()
            )
            status_resp.raise_for_status()
            status = status_resp.json()['data']

            print(f"Status: {status['status']} ({status['progress_percent']}%)")

            if status['status'] == 'completed':
                print("Validation complete!")
                break
            elif status['status'] == 'failed':
                raise Exception(f"Job failed: {status['error']}")

            time.sleep(30)

        # Step 7: Get results
        results_resp = requests.get(
            f"{self.base_url}/jobs/{job_id}/results",
            headers=self._headers()
        )
        results_resp.raise_for_status()
        results = results_resp.json()['data']

        print(f"Download results: {results['results']['download_url']}")
        print(f"Cost: ${results['summary']['cost_usd']}")

        return results

# Usage
client = HyperplexityClient("hpx_live_your_api_key_here")

config = {
    "tables": [{
        "name": "Companies",
        "columns": {
            "Company Name": {"validation_type": "text", "required": True},
            "Website": {"validation_type": "url", "required": False}
        }
    }]
}

results = client.validate_file("companies.xlsx", config)
```

### C. Webhook Verification (Python)

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)

WEBHOOK_SECRET = "your_webhook_secret_123"

@app.route('/webhooks/validation', methods=['POST'])
def handle_webhook():
    # Verify signature
    signature_header = request.headers.get('X-Hyperplexity-Signature')
    if not signature_header:
        return jsonify({"error": "Missing signature"}), 401

    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        request.data,
        hashlib.sha256
    ).hexdigest()

    provided_signature = signature_header.split('=', 1)[1]

    if not hmac.compare_digest(expected_signature, provided_signature):
        return jsonify({"error": "Invalid signature"}), 401

    # Process webhook
    payload = request.json

    if payload['event'] == 'job.completed':
        job_id = payload['job_id']
        download_url = payload['results']['download_url']

        print(f"Job {job_id} completed!")
        print(f"Download: {download_url}")

        # Process results (download, parse, store, etc.)
        # ...

    elif payload['event'] == 'job.failed':
        job_id = payload['job_id']
        error = payload['error']

        print(f"Job {job_id} failed: {error['message']}")

    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    app.run(port=5000)
```

---

## Document Revision History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-02-17 | Initial design document | System |
| 1.1 | 2026-02-18 | Mark Phase 0 & Phase 1 complete; record implementation details and deviations; expand Phase 2 with exact routing table, gateway detection approach, new files (`api_handler.py`, `rate_limiter_api.py`), and new action functions needed; fix `.split('=')` → `.split('=', 1)` in webhook signature examples | System |

---

**End of Design Document**
