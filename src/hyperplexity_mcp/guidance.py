"""
guidance.py — builds the _guidance block injected into every tool response.

Entry point:
    build_guidance(tool_name: str, api_data: dict) -> dict

Each per-tool function returns a dict with:
    "summary"    — one sentence describing where we are in the workflow
    "next_steps" — list of {"tool", "params", "note"} dicts
"""

from __future__ import annotations

import json
from typing import Callable


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_guidance(tool_name: str, api_data: dict) -> dict:
    """Dispatch to the per-tool guidance builder."""
    builder = _BUILDERS.get(tool_name)
    if builder is None:
        return {"summary": f"No guidance defined for tool '{tool_name}'.", "next_steps": []}
    try:
        return builder(api_data)
    except Exception as exc:  # never let guidance crash the tool
        return {"summary": f"Guidance error: {exc}", "next_steps": []}


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

def _guidance_upload_file(data: dict) -> dict:
    session_id = data.get("session_id", "")
    s3_key = data.get("s3_key", "")
    filename = data.get("filename", "")
    return {
        "summary": f"File uploaded to S3. Call confirm_upload to register it with the session.",
        "next_steps": [
            {
                "tool": "confirm_upload",
                "params": {
                    "session_id": session_id,
                    "s3_key": s3_key,
                    "filename": filename,
                },
                "note": "Confirm the upload so the backend indexes the file and detects prior configs.",
            }
        ],
    }


def _guidance_confirm_upload(data: dict) -> dict:
    session_id = data.get("session_id", "")
    conv_id = data.get("conversation_id", "")
    # External API returns "matches" (not "config_matches")
    matches = data.get("matches") or data.get("config_matches") or []
    best_score = matches[0].get("match_score", 0) if matches else 0

    s3_key = data.get("s3_key", "")
    reference_check_option = {
        "tool": "reference_check",
        "params": {"s3_key": s3_key} if s3_key else {"text": "<inline text>"},
        "note": (
            "ALTERNATIVE PATH — if you want to fact-check/verify claims in this document: "
            "call reference_check directly. There is NO interview, NO config step. "
            "Phase 1 (extraction, free) runs automatically; poll with wait_for_job until "
            "preview_complete, then call approve_validation to start Phase 2 (validation, charged). "
            "Pass auto_approve=True to skip the approval gate and run straight through."
        ),
    }

    # Explicit config_id provided OR strong auto-match found — preview already queued.
    if data.get("preview_queued"):
        job_id = data.get("job_id", session_id)
        config_id_used = data.get("config_id_used", "")
        return {
            "summary": (
                f"Upload confirmed. Preview auto-queued using config {config_id_used}. "
                "Call wait_for_job to track progress."
            ),
            "next_steps": [
                {
                    "tool": "wait_for_job",
                    "params": {"job_id": job_id, "timeout_seconds": 600},
                    "note": "Preview is queued. Do NOT call create_job — it was already done.",
                },
                reference_check_option,
            ],
        }

    # Server auto-started an upload interview (API session, no strong match).
    # conversation_id is present in the response — just poll it.
    if conv_id and data.get("interview_auto_started"):
        instructions_mode = bool(data.get("instructions_mode"))

        if instructions_mode:
            # instructions= was passed: AI skips Q&A and generates config directly.
            # Preview is auto-triggered after config generation.
            # Use wait_for_job — no conversation polling needed.
            return {
                "summary": (
                    "Upload confirmed. instructions= provided — the AI is generating the "
                    "validation config directly from the table structure and your instructions "
                    "(no clarifying questions). Preview will auto-trigger after config "
                    f"generation. conversation_id: {conv_id}"
                ),
                "next_steps": [
                    {
                        "tool": "wait_for_job",
                        "params": {
                            "job_id": session_id,
                            "timeout_seconds": 600,
                            "warmup_seconds": 300,
                        },
                        "note": (
                            "Config is being generated automatically (~2–3 min), then preview "
                            "runs (~3–5 min). timeout_seconds=600 covers both phases. "
                            "warmup_seconds=300 shows synthetic progress during the initial "
                            "silent phase (internal interview + config gen produce no messages). "
                            "wait_for_job tracks the config-generation intermediate step then "
                            "the preview automatically. Do NOT call create_job() or "
                            "wait_for_conversation."
                        ),
                    },
                    reference_check_option,
                ],
            }

        # No instructions: normal interactive interview — AI may ask questions.
        return {
            "summary": (
                "Upload confirmed. No strong config match found — an AI interview has been "
                "automatically started to build a validation config. "
                f"conversation_id: {conv_id}"
            ),
            "next_steps": [
                {
                    "tool": "wait_for_conversation",
                    "params": {
                        "conversation_id": conv_id,
                        "session_id": session_id,
                        "expected_seconds": 120,
                    },
                    "note": (
                        "Preferred: blocks with synthetic progress until the AI asks a question. "
                        "Answer questions via send_conversation_reply. "
                        "When the interview finishes (trigger_config_generation=true or "
                        "status=approved), call wait_for_job(session_id) directly — "
                        "it waits for config generation to complete, then tracks the preview "
                        "phase automatically until preview_complete. Do NOT call create_job()."
                    ),
                },
                {
                    "tool": "get_conversation",
                    "params": {"conversation_id": conv_id, "session_id": session_id},
                    "note": "Fallback: one-shot poll — re-call every 15s manually.",
                },
                reference_check_option,
            ],
        }

    if best_score >= 0.85:
        config_id = matches[0].get("config_id", "")

        # Non-API path (human/app) — present the option to reuse the matched config.
        # (API path with preview_queued=True is handled above.)
        return {
            "summary": (
                f"Upload confirmed. A prior config matches with score {best_score:.2f}. "
                "You can reuse it directly."
            ),
            "next_steps": [
                {
                    "tool": "create_job",
                    "params": {"session_id": session_id, "config_id": config_id},
                    "note": "Creates a preview job using the matched config. Fastest path.",
                },
                reference_check_option,
            ],
        }
    else:
        return {
            "summary": (
                "Upload confirmed. No strong prior config match. "
                "Use create_job with a known config_id, or supply a config directly."
            ),
            "next_steps": [
                {
                    "tool": "create_job",
                    "params": {
                        "session_id": session_id,
                        "config": "<paste config JSON here>",
                    },
                    "note": "Supply your own config JSON directly.",
                },
                reference_check_option,
            ],
        }


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def _guidance_create_job(data: dict) -> dict:
    job_id = data.get("job_id", "")
    status = data.get("status", "")
    run_type = data.get("run_type", "")

    # Issue 3: for table maker session IDs, get_job_status returns stale data from
    # the original table maker run (not the preview job). Drive from messages via
    # wait_for_job, which uses the messages endpoint as the primary progress source
    # and only calls get_job_status once a terminal state is confirmed.
    if job_id.startswith("session_") and run_type == "preview":
        return {
            "summary": (
                f"Preview job created (status={status}). "
                "IMPORTANT: get_job_status may return stale table maker data (status=completed, "
                "current_step='Config Generation') — this reflects the table maker run, not the "
                "preview. The messages endpoint is authoritative for real-time progress. "
                "Use wait_for_job to wait for preview_complete with live progress notifications; "
                "it drives from messages and retries status confirmation automatically. "
                "Save config_id from the result for future reruns, then call approve_validation."
            ),
            "next_steps": [
                {
                    "tool": "wait_for_job",
                    "params": {"job_id": job_id},
                    "note": (
                        "Preferred: blocks until preview_complete, emitting live progress from "
                        "messages. Returns the same payload as get_job_status."
                    ),
                },
                {
                    "tool": "get_job_messages",
                    "params": {"job_id": job_id},
                    "note": (
                        "Fallback: manually poll messages (card_id='preview') for real-time "
                        "progress, then call get_job_status once messages show 100%."
                    ),
                },
            ],
        }

    return {
        "summary": f"Job created (status={status}). Use wait_for_job to track completion.",
        "next_steps": [
            {
                "tool": "wait_for_job",
                "params": {"job_id": job_id},
                "note": (
                    "Preferred: blocks until preview_complete with live progress notifications. "
                    "Returns the full status payload including cost_estimate and config_id."
                ),
            }
        ],
    }


def _guidance_get_job_status(data: dict) -> dict:
    job_id = data.get("job_id", "")
    status = data.get("status", "")

    if status in ("queued", "processing"):
        return {
            "summary": (
                f"Job is {status}. Use wait_for_job to block until a terminal state — "
                "it drives from the messages endpoint (more reliable than status polling) "
                "and emits live MCP progress notifications."
            ),
            "next_steps": [
                {
                    "tool": "wait_for_job",
                    "params": {"job_id": job_id, "timeout_seconds": 1800},
                    "note": (
                        "Preferred: blocks until terminal state with live progress. "
                        "If this is a full validation (post-approve_validation), set "
                        "timeout_seconds = max(900, estimated_validation_time_seconds * 2) "
                        "using the estimate from the preview_complete response — full "
                        "validations can exceed 15 min for large tables. "
                        "1800 shown here is a safe default when the estimate is unavailable."
                    ),
                },
                {
                    "tool": "get_job_status",
                    "params": {"job_id": job_id},
                    "note": "Fallback: one-shot poll — re-call every ~20 seconds manually.",
                },
            ],
            "notes": [
                "session_id and job_id are the same value — this is by design. "
                "The status endpoint always reflects the most recent run for this session "
                "(config-gen → preview → validation as the pipeline advances)."
            ],
        }

    if status == "preview_complete" and data.get("claims_summary"):
        # Reference-check preview_complete: 3-claim validation preview done, waiting for approval.
        # preview_results.markdown_table is the validated 3-claim sample (inline, lifted by wait_for_job).
        # preview_claims_markdown is the full extracted claim list (unvalidated, for context).
        claims = data.get("claims_summary") or {}
        cost_est = data.get("cost_estimate") or {}
        cost = cost_est.get("estimated_total_cost_usd") or 0
        est_time_s = cost_est.get("estimated_validation_time_seconds")
        time_label = (
            f"~{round(int(est_time_s) / 60)} min" if est_time_s and int(est_time_s) >= 60
            else (f"~{est_time_s}s" if est_time_s else "")
        )
        prev_results = data.get("preview_results") or {}
        validated_md = prev_results.get("markdown_table", "")
        claims_list_md = data.get("preview_claims_markdown", "")
        total = claims.get("total", "?")

        if validated_md:
            summary = (
                f"Reference-check preview complete. START HERE — review "
                f"preview_results.markdown_table (inline, first 3 claims validated with "
                f"support level, confidence, and citations). {total} claims total. "
                f"Cost to validate all: ${cost}."
                + (f" Estimated time: {time_label}." if time_label else "")
            )
        elif claims_list_md:
            summary = (
                f"Reference-check extraction complete. {total} claims extracted. "
                f"Review preview_claims_markdown before approving. "
                f"Estimated validation cost: ${cost}."
                + (f" Estimated time: {time_label}." if time_label else "")
            )
        else:
            summary = (
                f"Reference-check extraction complete. "
                f"{total} claims found "
                f"({claims.get('with_references', '?')} with citations, "
                f"{claims.get('without_references', '?')} without). "
                f"Estimated validation cost: ${cost}."
                + (f" Estimated time: {time_label}." if time_label else "")
            )
        result = {
            "summary": summary,
            "claims_summary": claims,
            "cost_estimate": cost_est,
            "next_steps": [
                {
                    "tool": "approve_validation",
                    "params": {"job_id": job_id, "approved_cost_usd": cost},
                    "note": (
                        f"Approve to validate all {total} claims. "
                        f"Cost: ${cost}."
                        + (f" Estimated time: {time_label}." if time_label else "")
                    ),
                },
                {
                    "tool": "get_reference_results",
                    "params": {"job_id": job_id},
                    "note": "After validation completes, fetch results here (inline markdown_table included).",
                    "when": "after validation completes (status=completed)",
                },
            ],
        }
        return result

    if status == "preview_complete":
        # External API: cost lives in cost_estimate.estimated_total_cost_usd
        cost_est = data.get("cost_estimate") or {}
        cost = (cost_est.get("estimated_total_cost_usd")
                or data.get("estimated_cost_usd")
                or data.get("cost_usd")
                or 0)
        config_id = data.get("config_id", "")
        refine_session = data.get("refine_session_id") or data.get("conversation_id", "")
        session_id = data.get("session_id", "")

        # Surface preview results if present.
        _prev_results = data.get("preview_results") or {}
        prev_url = _prev_results.get("download_url", "")
        prev_metadata_url = _prev_results.get("metadata_url", "")
        prev_markdown = _prev_results.get("markdown_table", "")

        # Issue #6: surface estimated full-validation time and compute a safe timeout.
        # Full validations can run well beyond 15 min for large tables, so the
        # timeout for the wait_for_job call AFTER approve_validation should be
        # 2× the estimate rather than a fixed cap.  Minimum floor: 900s.
        est_time_s = cost_est.get("estimated_validation_time_seconds")
        if est_time_s:
            try:
                est_time_s = int(est_time_s)
                time_label = (
                    f"~{round(est_time_s / 60)} min" if est_time_s >= 60
                    else f"~{est_time_s}s"
                )
                suggested_timeout = max(900, est_time_s * 2)
            except (ValueError, TypeError):
                est_time_s = None
                time_label = ""
                suggested_timeout = 900
        else:
            time_label = ""
            suggested_timeout = 900

        approve_note = (
            "Decision point — review the inline "
            + ("preview_results.markdown_table (full per-cell detail for all 3 preview rows). "
               if prev_markdown else
               "preview_table (3-row sample with confidence signals). ")
            + "Download links are in preview_results if needed. "
            + f"Estimated cost: ${cost}."
            + (f" Estimated time: {time_label}." if time_label else "")
            + f" After approval, call wait_for_job with timeout_seconds={suggested_timeout} "
            f"(2× the time estimate, min 900)."
        )

        next_steps = [
            {
                "tool": "approve_validation",
                "params": {"job_id": job_id, "approved_cost_usd": cost},
                "note": approve_note,
            },
            {
                "tool": "wait_for_job",
                "params": {"job_id": job_id, "timeout_seconds": suggested_timeout},
                "note": (
                    "Call this AFTER approve_validation returns. "
                    + (f"timeout_seconds={suggested_timeout} = 2× the {time_label} estimate. "
                       if time_label else "timeout_seconds=900 (default; increase if table is large). ")
                    + "Returns the final status payload; then call get_results."
                ),
                "when": "after approve_validation",
            },
            {
                "tool": "refine_config",
                "params": {
                    "conversation_id": refine_session if refine_session else "<conversation_id from confirm_upload or start_table_maker>",
                    "session_id": session_id,
                    "instructions": "<describe the changes you want>",
                },
                "note": (
                    "Not satisfied with the preview? Call refine_config to adjust columns or "
                    "validation approach before approving."
                    + (" Use the conversation_id from your initial confirm_upload or "
                       "start_table_maker call." if not refine_session else "")
                ),
            },
        ]

        if prev_markdown:
            summary = (
                f"Preview complete (3 rows). START HERE — review preview_results.markdown_table "
                f"(inline, full per-cell confidence and citations for all 3 rows). Cost: ${cost}. "
                + (f"Estimated full-run time: {time_label}. " if time_label else "")
                + (f"After approving, use timeout_seconds={suggested_timeout} for wait_for_job. " if est_time_s else "")
                + (f"config_id for future reruns: {config_id}. " if config_id else "")
                + "Download links are in preview_results."
            )
        else:
            summary = (
                f"Preview complete (3 rows). Review the inline preview_table for confidence signals "
                f"and cost (${cost}) before approving. Download links are in preview_results."
                + (f" Estimated full-run time: {time_label}." if time_label else "")
                + (f" After approving, use timeout_seconds={suggested_timeout} for wait_for_job." if est_time_s else "")
                + (f" config_id for future reruns: {config_id}." if config_id else "")
            )

        return {
            "summary": summary,
            "next_steps": next_steps,
            "no_approval_gate": True,
            "agent_note": (
                "The agent can review the preview_table (included inline) and call "
                "approve_validation directly — no human approval is required unless you want it."
            ),
        }

    if status == "completed":
        # Table maker / config-gen jobs complete with an intermediate current_step.
        # Their results live in the web viewer, not the /results endpoint.
        # Use case-insensitive substring match to handle backend variations such as
        # "Configuration generation completed successfully." vs "Config Generation".
        current_step = data.get("current_step", "")
        if any(s in current_step.lower() for s in (
            "config generation", "configuration generation",
            "table making", "table maker",
        )):
            # Table maker has finished. For API sessions the preview is already
            # auto-queued — do NOT call create_job(). wait_for_job handles this
            # phase transition automatically (detects intermediate complete, resets,
            # and continues polling into the preview phase).
            return {
                "summary": (
                    "Table maker complete (intermediate phase). A preview validation job has been "
                    "automatically queued. Do NOT call create_job() — the preview is already running. "
                    "Use wait_for_job to track the preview phase with live progress; it detects this "
                    "phase boundary automatically and keeps polling until preview_complete."
                ),
                "next_steps": [
                    {
                        "tool": "wait_for_job",
                        "params": {"job_id": job_id},
                        "note": (
                            "Preferred: detects the phase transition and blocks until preview_complete, "
                            "emitting live progress. Returns the full status payload with cost_estimate."
                        ),
                    },
                    {
                        "tool": "get_job_status",
                        "params": {"job_id": job_id},
                        "note": (
                            "Fallback: poll every 20s until status == 'preview_complete', "
                            "then call approve_validation."
                        ),
                    },
                ],
            }
        return {
            "summary": "Job completed successfully. Fetch your results.",
            "next_steps": [
                {
                    "tool": "get_results",
                    "params": {"job_id": job_id},
                    "note": "Download the enriched/validated output.",
                },
                {
                    "tool": "get_reference_results",
                    "params": {"job_id": job_id},
                    "note": "Optional: fetch reference-check sub-results if applicable.",
                },
            ],
            "output_files": {
                "markdown_table": "Self-contained markdown in metadata.markdown_table — full data table with _row_key column, confidence icons, viewer URL, and citation navigation guide. Read this first.",
                "excel_file": "XLSX file with sources and citations embedded in cell comments — ideal for sharing with humans.",
                "metadata_json": "Complete table_metadata.json — per-cell confidence, citations, sources, and validator reasoning, keyed by row_key.",
            },
        }

    if status == "failed":
        error = data.get("error") or data.get("message") or "Unknown error"
        return {
            "summary": f"Job failed: {error}. No further actions available.",
            "next_steps": [],
        }

    # Unknown / other status
    return {
        "summary": f"Job status is '{status}'. Poll again or check messages.",
        "next_steps": [
            {
                "tool": "get_job_status",
                "params": {"job_id": job_id},
                "note": "Poll again in a few seconds.",
            }
        ],
    }


def _guidance_get_job_messages(data: dict) -> dict:
    job_id = data.get("job_id", "")
    messages = data.get("messages") or []
    # External API returns last_seq at the top level of the messages response;
    # individual messages use "_seq".  Prefer top-level last_seq.
    last_seq = data.get("last_seq")
    if last_seq is None and messages:
        last_seq = messages[-1].get("_seq") or messages[-1].get("seq")
    params = {"job_id": job_id}
    if last_seq is not None:
        params["since_seq"] = last_seq

    # Fix #3: scan message payloads for viewer/download URLs buried in message_data.
    _URL_KEYS = ("download_url", "viewer_url", "interactive_viewer_url")
    found_urls: dict[str, str] = {}
    for msg in messages:
        msg_data = msg.get("message_data") or msg.get("data") or {}
        if isinstance(msg_data, dict):
            for key in _URL_KEYS:
                val = msg_data.get(key)
                if val and key not in found_urls:
                    found_urls[key] = val

    # Issue #6: collect distinct card_ids present in this batch so agents can
    # understand the multi-card interleaving and why _seq numbers appear to jump.
    card_ids: list[str] = []
    for msg in messages:
        cid = msg.get("card_id") or msg.get("cardId", "")
        if cid and cid not in card_ids:
            card_ids.append(cid)

    summary = f"Fetched {len(messages)} message(s). Continue polling job status."
    if found_urls:
        url_str = "; ".join(f"{k}: {v}" for k, v in found_urls.items())
        summary += f" URLs found in messages — {url_str}"

    result: dict = {
        "summary": summary,
        "next_steps": [
            {
                "tool": "get_job_messages",
                "params": params,
                "note": "Pass since_seq to get only new messages.",
            },
            {
                "tool": "get_job_status",
                "params": {"job_id": job_id},
                "note": "Check overall job status.",
            },
        ],
        "notes": [
            (
                "MULTI-CARD INTERLEAVING: card_ids_present[] in this response lists every "
                "pipeline stage (e.g. 'preview', 'config-gen', 'table-maker-{conv_id}') that "
                "emitted messages in this batch. Each card has its own independent _seq counter "
                "— apparent gaps in sequence numbers are normal and expected."
            ),
            (
                "CONFIDENCE INDICATOR: confidence_score in progress messages is an aggregate "
                "quality signal used internally to color the UI progress bar. It is NOT the "
                "per-cell HIGH / MEDIUM / LOW confidence rating in the final results — do not "
                "interpret it as a per-row confidence score."
            ),
        ],
    }
    if found_urls:
        result["found_urls"] = found_urls
    if card_ids:
        result["card_ids_present"] = card_ids
    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _guidance_approve_validation(data: dict) -> dict:
    job_id = data.get("job_id", "")
    status = data.get("status", "")
    return {
        "summary": (
            f"Validation approved. Job is now {status}. "
            "Use wait_for_job with a generous timeout — full validations can exceed 15 minutes "
            "for large tables. Set timeout_seconds = 2× the estimated_validation_time_seconds "
            "you received in the preview_complete response (minimum 900)."
        ),
        "next_steps": [
            {
                "tool": "wait_for_job",
                "params": {"job_id": job_id, "timeout_seconds": 1800},
                "note": (
                    "IMPORTANT: override timeout_seconds = max(900, estimated_validation_time_seconds * 2) "
                    "if you have the estimate from the preview_complete response "
                    "(cost_estimate.estimated_validation_time_seconds). "
                    "Full validations can run well beyond 15 min for large tables — 1800 shown here "
                    "is a safe default when the estimate is unavailable. "
                    "Returns the final status payload; then call get_results."
                ),
            }
        ],
    }


def _guidance_get_results(data: dict) -> dict:
    result_info  = data.get("results") or {}
    job_info     = data.get("job_info") or {}
    summary      = data.get("summary") or {}
    viewer_url   = result_info.get("interactive_viewer_url", "")
    download_url = result_info.get("download_url", "")
    metadata_url = result_info.get("metadata_url", "")
    rows         = summary.get("rows_processed", "?")
    cols         = summary.get("columns_validated", "?")
    cost         = summary.get("cost_usd", "?")
    table_name   = job_info.get("input_table_name", "")

    summary_parts = [
        f"Validation complete: {rows} rows, {cols} columns validated" +
        (f" — {table_name}" if table_name else "") +
        (f" (cost: ${cost})" if cost != "?" else "") + "."
    ]
    if viewer_url:
        summary_parts.append(
            f"Share the interactive viewer with humans — it is the best way to "
            f"communicate this research: {viewer_url}"
        )

    has_metadata = bool(result_info.get("metadata"))
    notes = [
        "HOW TO READ THE RESULTS:",
        "1. START HERE — read results.markdown_table (lifted directly into this response). "
        "It is a self-contained markdown document with: the full validated data table "
        "(all rows, full values, _row_key as the last column), configuration notes, "
        "confidence key, viewer/download links, and instructions for navigating citations. "
        "Designed to be read directly — no JSON parsing required." if not has_metadata else
        "1. START HERE — results.markdown_table is already embedded in this response. "
        "It is a self-contained markdown document with the full validated data table "
        "(all rows, full values, _row_key as last column), configuration notes, "
        "confidence key, viewer/download links, and citation navigation guide. Read it first.",
        "2. To look up sources, citations, and validator reasoning for any cell: take the row's "
        "_row_key from the markdown table and find that row in metadata.rows[] — "
        "rows[].cells[column_name].comment contains validator_explanation, qc_reasoning, "
        "key_citation, and sources[] ({title, url, snippet}).",
        "3. results.download_url is the enriched Excel file with validation detail in cell comments. "
        "Use it when you need a file to share with humans offline.",
        "4. Always share results.interactive_viewer_url with human stakeholders — "
        "it renders sources, citations, and confidence scores in a clean UI that is "
        "far easier to navigate than raw JSON or spreadsheet formulas.",
        "5. Column definitions and validation approaches can be refined — share "
        "results.interactive_viewer_url and ask the human to use Refine Configuration, "
        "or call refine_config with updated instructions.",
    ]

    return {
        "summary": " ".join(summary_parts),
        "next_steps": [
            {
                "tool": "get_reference_results",
                "params": {"job_id": job_info.get("job_id", data.get("job_id", ""))},
                "note": "Optional: fetch reference-check sub-results if a reference document was provided.",
            }
        ] if job_info.get("has_reference_results") else [],
        "notes": notes,
        "key_urls": {
            k: v for k, v in {
                "interactive_viewer": viewer_url,
                "download_excel":     download_url,
                "metadata":           metadata_url,
            }.items() if v
        },
        "output_files": {
            "markdown_table": "Self-contained markdown in metadata.markdown_table — full data table with _row_key column, confidence icons, viewer URL, and citation navigation guide. Read this first.",
            "excel_file": "XLSX file with sources and citations embedded in cell comments — ideal for sharing with humans.",
            "metadata_json": "Complete table_metadata.json — per-cell data keyed by row_key. Each cell: cells[col].value (validated value), .confidence (HIGH/MEDIUM/LOW/ID), .comment.validator_explanation, .comment.key_citation, .comment.sources[]. Use .value — legacy files may use .full_value, both are equivalent.",
        },
    }


def _guidance_get_reference_results(data: dict) -> dict:
    results      = data.get("results") or {}
    viewer_url   = results.get("interactive_viewer_url", "")
    has_markdown = bool(results.get("markdown_table"))
    has_metadata = bool(results.get("metadata"))
    return {
        "summary": "Reference check complete. Review results.markdown_table (inline) for per-claim support levels, confidence, and citations.",
        "notes": [
            (
                "1. START HERE — results.markdown_table is embedded inline. Full validated "
                "claims table with support levels (SUPPORTED / PARTIAL / UNSUPPORTED / UNVERIFIABLE), "
                "confidence icons, viewer/download links, and citation navigation guide. Read this first."
                if has_markdown else
                "1. START HERE — results.markdown_table was not embedded (metadata fetch may have failed). "
                "Check results.metadata_fetch_error; or download results.metadata_url manually."
            ),
            "2. For full per-claim citations: results.metadata.rows[].cells[col].comment contains "
            "validator_explanation, key_citation, and sources[] ({title, url, snippet})."
            if has_metadata else
            "2. Per-claim citation detail is in the metadata JSON at results.metadata_url.",
            "3. Download links are in results (download_url, metadata_url) if needed for offline sharing.",
            "4. Share results.interactive_viewer_url with human stakeholders — "
            "it renders sources and confidence scores in a clean UI.",
        ],
        "key_urls": {k: v for k, v in {
            "interactive_viewer": viewer_url,
        }.items() if v},
        "next_steps": [
            {"note": "Share interactive_viewer_url with human stakeholders — it renders sources and confidence scores in a clean UI."}
        ] if viewer_url else [],
    }


# ---------------------------------------------------------------------------
# Job Actions
# ---------------------------------------------------------------------------

def _guidance_update_table(data: dict) -> dict:
    job_id = data.get("job_id", "")
    return {
        "summary": "Update-table job started. Use wait_for_job to track completion.",
        "next_steps": [
            {
                "tool": "wait_for_job",
                "params": {"job_id": job_id},
                "note": "Blocks until completed with live progress. Then call get_results.",
            }
        ],
    }


def _guidance_reference_check(data: dict) -> dict:
    job_id = data.get("job_id", "")
    auto_approve = bool(data.get("auto_approve", False))

    min_claims_note = "Hyperplexity is designed for text with 4 or more factual claims. Fewer claims may produce low-quality results."

    if auto_approve:
        return {
            "summary": (
                "Reference-check job started with auto_approve=True. "
                "Phase 1 (claim extraction) runs first, then Phase 2 (validation) is "
                "queued automatically — no approval step needed. "
                "Poll with wait_for_job until status=completed, then call get_results "
                "or get_reference_results."
            ),
            "phases": ["extraction (free)", "validation (charged, auto-approved)"],
            "min_claims_note": min_claims_note,
            "messages_note": "get_job_messages is empty for reference checks — use wait_for_job or get_job_status.",
            "next_steps": [
                {
                    "tool": "wait_for_job",
                    "params": {"job_id": job_id, "timeout_seconds": 900},
                    "note": "Waits for completed. Then call get_results (XLSX + interactive viewer + metadata).",
                }
            ],
        }

    return {
        "summary": (
            "Reference-check job started. Phase 1 (claim extraction, free) runs first, "
            "then a 3-row preview validates sample claims automatically. "
            "wait_for_job stops at preview_complete — review preview_table (3 validated "
            "sample claims with support level and citations) and cost_estimate, then call "
            "approve_validation to run full claim validation (Phase 2, charged)."
        ),
        "phases": ["extraction (free)", "preview validation (free, auto-triggered)", "approval gate", "validation (charged)"],
        "min_claims_note": min_claims_note,
        "auto_approve_note": "Pass auto_approve=True to skip the approval gate and run straight through to completed.",
        "messages_note": "get_job_messages is empty for reference checks — use wait_for_job or get_job_status.",
        "next_steps": [
            {
                "tool": "wait_for_job",
                "params": {"job_id": job_id},
                "note": "Waits for preview_complete. Review preview_table + cost_estimate, then call approve_validation.",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def _guidance_start_table_maker(data: dict) -> dict:
    conv_id = data.get("conversation_id", "")
    session_id = data.get("session_id", "")
    status = data.get("status", "")

    if status == "completed":
        return {
            "summary": "Table-maker conversation started (completed immediately). Fetch the conversation for results.",
            "next_steps": [
                {
                    "tool": "get_conversation",
                    "params": {"conversation_id": conv_id, "session_id": session_id},
                    "note": "Retrieve the completed conversation and any next-step instructions.",
                }
            ],
        }

    auto_start = bool(data.get("auto_start"))

    # Default: still processing (status == "processing" or unknown)
    if auto_start:
        conv_summary = (
            "Table-maker started with auto_start=True — the AI skips questions and "
            "structure-confirmation, outputting trigger_execution=true directly. "
            "One wait_for_conversation call is all that's needed before switching to wait_for_job."
        )
        conv_expected = 90   # single direct mode-3 turn; no multi-turn Q&A
        conv_note = (
            "With auto_start=True there is exactly ONE conversation turn. "
            "The AI skips questions and structure-confirmation and returns "
            "trigger_execution=true immediately. Expected ~60–90s. "
            "After this call returns, switch to wait_for_job(session_id)."
        )
    else:
        conv_summary = "Table-maker conversation started. Wait for the AI's response."
        conv_expected = 150  # may ask questions + present structure
        conv_note = (
            "Preferred: blocks with synthetic progress until the AI presents a table "
            "structure or asks a clarifying question. First turn typically takes 2–3 min."
        )

    cost_note = (
        "Table building and the 3-row preview are free. Full validation is charged "
        "at approve_validation — you see the cost estimate at preview_complete "
        "before anything is billed. If balance is insufficient, approve_validation "
        "returns an insufficient_balance error with the required amount."
    )

    return {
        "summary": conv_summary,
        "cost_note": cost_note,
        "next_steps": [
            {
                "tool": "wait_for_conversation",
                "params": {
                    "conversation_id": conv_id,
                    "session_id": session_id,
                    "expected_seconds": conv_expected,
                },
                "note": conv_note,
            },
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Fallback: one-shot poll — re-call every 15s manually.",
            },
        ],
        "cost_guidance": (
            "Tables start at ~$2 minimum. Standard validation is ~$0.05 per validated cell "
            "(rows × validated columns). Advanced tables routed to more sophisticated models "
            "can be up to ~$0.25/cell. Cost is minimized by limiting validated columns to only "
            "those that need research, enrichment, or verification — you can scope this during "
            "the conversation, or use refine_config after the preview to adjust column selection "
            "before approving. Exact cost is confirmed at preview_complete."
        ),
        "workflow": {
            "fire_and_forget_capable": True,
            "note": (
                "After preview completes, the agent can auto-approve and proceed to full "
                "validation without human intervention. Review the inline preview_table in "
                "the preview_complete response."
            ),
        },
    }


def _guidance_get_conversation(data: dict) -> dict:
    conv_id = data.get("conversation_id", "")
    session_id = data.get("session_id", "")
    status = data.get("status", "")
    user_reply_needed = data.get("user_reply_needed", False)
    next_step = data.get("next_step") or {}

    # user_reply_needed takes priority: the AI has finished its turn and is
    # explicitly waiting for the user.  Check this before status=="processing"
    # to avoid trapping agents in a poll loop when a reply is required.
    if user_reply_needed:
        last_message = ""
        # last_ai_message is the authoritative source — may be a JSON-encoded
        # string (parse it) or a dict.  Fall back to messages list if absent.
        raw = data.get("last_ai_message")
        if raw:
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    last_message = (parsed.get("ai_message")
                                    or parsed.get("content") or "")
                except Exception:
                    last_message = raw  # treat as plain text
            elif isinstance(raw, dict):
                last_message = raw.get("ai_message") or raw.get("content") or ""
        if not last_message:
            messages = data.get("messages") or []
            if messages:
                last_message = messages[-1].get("content", "")
        return {
            "summary": f"AI is waiting for your reply. Question: {last_message}",
            "next_steps": [
                {
                    "tool": "send_conversation_reply",
                    "params": {
                        "conversation_id": conv_id,
                        "session_id": session_id,
                        "message": "<your answer here>",
                    },
                    "note": "Answer the AI's question to continue the interview.",
                }
            ],
        }

    if status == "processing":
        return {
            "summary": (
                "Conversation is still processing. "
                "Use wait_for_conversation for a live progress indicator."
            ),
            "next_steps": [
                {
                    "tool": "wait_for_conversation",
                    "params": {
                        "conversation_id": conv_id,
                        "session_id": session_id,
                    },
                    "note": (
                        "Preferred: blocks with synthetic time-based progress until the AI "
                        "responds. No token cost while waiting."
                    ),
                },
                {
                    "tool": "get_conversation",
                    "params": {"conversation_id": conv_id, "session_id": session_id},
                    "note": "Fallback: one-shot poll — re-call every 15s manually.",
                },
            ],
        }

    action = next_step.get("action", "")

    # Check trigger_execution directly from data — next_step.action may have been
    # patched to "wait" by the MCP layer to resolve the submit_preview conflict,
    # but data.trigger_execution is never mutated and is the authoritative signal.
    trigger_execution = data.get("trigger_execution") or next_step.get("trigger_execution")

    if trigger_execution:
        if conv_id.startswith("refine_"):
            # Config refinement complete — the table was already built.
            # A new preview has been automatically queued with the refined config.
            return {
                "summary": (
                    "Config refinement complete. A new preview validation job has been "
                    "automatically queued with the updated config. "
                    "Do NOT call create_job(). "
                    "Use wait_for_job(session_id) to track the preview with live progress."
                ),
                "next_steps": [
                    {
                        "tool": "wait_for_job",
                        "params": {"job_id": session_id},
                        "note": (
                            "Preferred: blocks until preview_complete with live progress. "
                            "Then review cost_estimate and call approve_validation."
                        ),
                    },
                ],
            }
        # The table maker is NOW RUNNING. Once complete, a preview validation
        # job is automatically queued for API sessions — do NOT call create_job().
        # wait_for_job handles the phase transition (table-maker → preview) automatically.
        target_rows = data.get("target_row_count")
        cost_hint = ""
        if target_rows:
            try:
                rows = int(target_rows)
                if rows > 0:
                    # Rough cost range: $2 minimum; ~$0.05/cell standard, ~$0.25/cell advanced.
                    # Try to get actual column count from conversation data; fall back to
                    # typical 4–6 column range if the response doesn't include column info.
                    cols = None
                    config = data.get("config") or {}
                    col_list = (
                        config.get("columns")
                        or data.get("columns")
                        or data.get("validated_columns")
                        or []
                    )
                    if col_list and isinstance(col_list, list):
                        cols = len(col_list)
                    elif data.get("column_count"):
                        try:
                            cols = int(data["column_count"])
                        except (ValueError, TypeError):
                            pass

                    if cols and cols > 0:
                        low = max(2.0, rows * cols * 0.05)
                        high = rows * cols * 0.25
                        cost_hint = (
                            f" BALLPARK COST: {rows} rows × {cols} columns ≈ ${low:.2f}–${high:.2f} "
                            f"(~$0.05/cell standard, ~$0.25/cell advanced, $2 minimum). "
                            f"Column count may shift slightly — lock in at preview_complete after reviewing output."
                        )
                    else:
                        low = max(2.0, rows * 4 * 0.05)
                        high = rows * 6 * 0.25
                        cost_hint = (
                            f" BALLPARK COST: {rows} rows × ~4–6 columns ≈ ${low:.0f}–${high:.0f} "
                            f"(column count finalizes after preview; "
                            f"~$0.05/cell standard, ~$0.25/cell advanced, $2 minimum). "
                            f"Lock in at preview_complete after reviewing output."
                        )
            except (ValueError, TypeError):
                pass
        return {
            "summary": (
                "Table is being built. A preview validation job will start automatically "
                "once the table maker finishes (typically 5–30 minutes; complex research "
                "requests may take longer). "
                "Do NOT call create_job() — the preview is auto-queued. "
                "Use wait_for_job(session_id) — it detects the phase transition and "
                "tracks both the table-maker and preview phases with live progress. "
                "If wait_for_job times out, call it again — the job is still running."
                + cost_hint
            ),
            "next_steps": [
                {
                    "tool": "wait_for_job",
                    "params": {"job_id": session_id},
                    "note": (
                        "Preferred: handles the table-maker → preview phase boundary "
                        "automatically. Blocks until preview_complete, then call "
                        "approve_validation."
                    ),
                },
            ],
        }

    if action == "submit_preview":
        # Upload-interview flow: config is generated and a preview job is
        # automatically queued for API sessions. Do NOT call create_job().
        # Use wait_for_job to track the preview phase with live progress.
        return {
            "summary": (
                "Interview complete. The config has been generated and a preview job "
                "has been automatically queued. "
                "Do NOT call create_job() — the preview is already running. "
                "Use wait_for_job(session_id) to track it with live progress "
                "until preview_complete, then call approve_validation."
            ),
            "agent_note": (
                "The AI's ai_message may contain a confirmation prompt such as "
                "'Click confirm or say yes to proceed!' — ignore it. "
                "The interview is already status=approved with user_reply_needed=false. "
                "No reply is needed. Call wait_for_job(session_id) directly."
            ),
            "next_steps": [
                {
                    "tool": "wait_for_job",
                    "params": {"job_id": session_id},
                    "note": (
                        "Preferred: blocks until preview_complete with live progress. "
                        "Returns the full status payload; then call approve_validation."
                    ),
                },
                {
                    "tool": "refine_config",
                    "params": {
                        "conversation_id": conv_id,
                        "session_id": session_id,
                        "instructions": "<describe changes>",
                    },
                    "note": "Optional: refine the config before the preview completes.",
                },
            ],
        }

    # Issue 7: execution_ready with an action other than submit_preview — handle explicitly.
    if status == "execution_ready":
        return {
            "summary": (
                f"Conversation is execution_ready (next_step.action='{action}'). "
                "Review next_step for the required action and follow its instructions."
            ),
            "next_steps": [
                {
                    "tool": "send_conversation_reply",
                    "params": {
                        "conversation_id": conv_id,
                        "session_id": session_id,
                        "message": "<follow next_step.action instructions>",
                    },
                    "note": (
                        f"next_step.action is '{action}' — inspect the full next_step object "
                        "for required params and body before calling."
                    ),
                }
            ],
        }

    # Upload-interview terminal state: status=approved.
    # Config generation is running in the background; preview is auto-queued once it
    # finishes — do NOT call create_job(). Switch to wait_for_job(session_id).
    # NOTE: The backend API does not expose trigger_config_generation in the
    # response — only the internal S3 state has it. status="approved" alone is
    # sufficient because only upload interviews reach this state.
    if status == "approved":
        return {
            "summary": (
                "Upload interview complete. Config generation is running automatically in the "
                "background. A preview job will be auto-queued once the config is ready — "
                "do NOT call create_job(). Use wait_for_job(session_id) to track the preview."
            ),
            "agent_note": (
                "The AI's ai_message may contain a confirmation prompt such as "
                "'Click confirm or say yes to proceed!' — ignore it. "
                "The interview is already status=approved with user_reply_needed=false. "
                "No reply is needed. Call wait_for_job(session_id) directly."
            ),
            "next_steps": [
                {
                    "tool": "wait_for_job",
                    "params": {"job_id": session_id},
                    "note": (
                        "Preferred: blocks until preview_complete with live progress. "
                        "Config generation + preview typically takes 60–120s. "
                        "Then call approve_validation."
                    ),
                },
            ],
        }

    # Completed / other
    return {
        "summary": f"Conversation status: {status}. Check next_step for instructions.",
        "next_steps": [
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Poll again if status is still in progress.",
            }
        ],
    }


def _guidance_send_conversation_reply(data: dict) -> dict:
    conv_id = data.get("conversation_id", "")
    session_id = data.get("session_id", "")
    return {
        "summary": "Reply sent. Wait for the AI's next message.",
        "next_steps": [
            {
                "tool": "wait_for_conversation",
                "params": {
                    "conversation_id": conv_id,
                    "session_id": session_id,
                    "expected_seconds": 60,
                },
                "note": (
                    "Preferred: blocks with synthetic progress. "
                    "Simple confirmations ('yes') typically resolve in 30–90s."
                ),
            },
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Fallback: one-shot poll — re-call every 15s manually.",
            },
        ],
    }


def _guidance_refine_config(data: dict) -> dict:
    conv_id = data.get("conversation_id", "")
    session_id = data.get("session_id", "")
    return {
        "summary": "Config refinement submitted. Wait for the updated config.",
        "next_steps": [
            {
                "tool": "wait_for_conversation",
                "params": {
                    "conversation_id": conv_id,
                    "session_id": session_id,
                    "expected_seconds": 90,
                },
                "note": "Preferred: blocks with synthetic progress until the refined config is ready.",
            },
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Fallback: one-shot poll — re-call every 15s manually.",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

def _guidance_get_balance(data: dict) -> dict:
    balance = data.get("balance_usd") or data.get("balance", "unknown")
    return {
        "summary": f"Account balance: ${balance}.",
        "next_steps": [],
    }


def _guidance_get_usage(data: dict) -> dict:
    total = data.get("total_cost_usd") or data.get("total", "unknown")
    return {
        "summary": f"Usage data fetched. Total cost in range: ${total}.",
        "next_steps": [],
    }


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_BUILDERS: dict[str, Callable] = {
    "upload_file": _guidance_upload_file,
    "confirm_upload": _guidance_confirm_upload,
    "create_job": _guidance_create_job,
    "get_job_status": _guidance_get_job_status,
    "wait_for_job": _guidance_get_job_status,  # same payload shape — reuse builder
    "get_job_messages": _guidance_get_job_messages,
    "approve_validation": _guidance_approve_validation,
    "get_results": _guidance_get_results,
    "get_reference_results": _guidance_get_reference_results,
    "update_table": _guidance_update_table,
    "reference_check": _guidance_reference_check,
    "start_table_maker": _guidance_start_table_maker,
    "get_conversation": _guidance_get_conversation,
    "send_conversation_reply": _guidance_send_conversation_reply,
    "refine_config": _guidance_refine_config,
    "get_balance": _guidance_get_balance,
    "get_usage": _guidance_get_usage,
}
