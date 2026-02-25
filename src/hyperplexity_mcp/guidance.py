"""
guidance.py — builds the _guidance block injected into every tool response.

Entry point:
    build_guidance(tool_name: str, api_data: dict) -> dict

Each per-tool function returns a dict with:
    "summary"    — one sentence describing where we are in the workflow
    "next_steps" — list of {"tool", "params", "note"} dicts
"""

from __future__ import annotations

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

    # Server auto-started an upload interview (API session, no strong match).
    # conversation_id is present in the response — just poll it.
    if conv_id and data.get("interview_auto_started"):
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
                        "When the interview finishes (status=approved, trigger_config_generation=true), "
                        "call create_job(session_id) to start the preview — "
                        "the preview is NOT auto-queued for upload-interview sessions."
                    ),
                },
                {
                    "tool": "get_conversation",
                    "params": {"conversation_id": conv_id, "session_id": session_id},
                    "note": "Fallback: one-shot poll — re-call every 15s manually.",
                },
            ],
        }

    if best_score >= 0.85:
        config_id = matches[0].get("config_id", "")
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
                    "params": {"job_id": job_id},
                    "note": (
                        "Preferred: blocks until terminal state with live progress. "
                        "Returns the same payload as get_job_status."
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

        # Fix #5: surface preview Excel download URL if present.
        prev_url = (data.get("preview_results") or {}).get("download_url", "")

        next_steps = [
            {
                "tool": "approve_validation",
                "params": {"job_id": job_id, "approved_cost_usd": cost},
                "note": (
                    f"Review preview_results.download_url first, then approve. "
                    f"Estimated cost: ${cost}."
                ),
            }
        ]
        if refine_session:
            next_steps.append({
                "tool": "refine_config",
                "params": {
                    "conversation_id": refine_session,
                    "session_id": session_id,
                    "instructions": "<describe the changes you want>",
                },
                "note": "Optional: refine column mappings before approving.",
            })

        summary = (
            f"Preview complete. Estimated cost: ${cost}. "
            + (f"config_id for future reruns: {config_id}. " if config_id else "")
            + "Approve to start full processing."
        )
        if prev_url:
            summary += f" Preview Excel download: {prev_url}"

        return {
            "summary": summary,
            "next_steps": next_steps,
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
        "summary": f"Validation approved. Job is now {status}. Use wait_for_job to track completion.",
        "next_steps": [
            {
                "tool": "wait_for_job",
                "params": {"job_id": job_id},
                "note": (
                    "Preferred: blocks until completed with live progress notifications. "
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
        "1. results.metadata is the full table_metadata.json — already embedded inline in "
        "this response. It is your primary machine-readable source of truth for every "
        "validated cell." if has_metadata else
        "1. results.metadata_url (presigned S3 URL) points to table_metadata.json — the "
        "structured JSON file containing every validated cell's full detail. "
        "Download it to access per-cell validation details.",
        "2. results.metadata structure:",
        "   • table_name  — display name of the validated table",
        "   • columns[]   — list of validated columns with importance, description, notes",
        "   • rows[]      — one entry per row. Each row has cells[] array (positional, aligned to columns[]):",
        "       cells[i].display_value      — formatted value with confidence emoji prefix",
        "       cells[i].full_value         — raw validated/corrected value",
        "       cells[i].confidence         — HIGH / MEDIUM / LOW / ID",
        "       cells[i].comment.validator_explanation — why the value was accepted/changed",
        "       cells[i].comment.qc_reasoning          — QC layer reasoning",
        "       cells[i].comment.key_citation          — the single most important citation",
        "       cells[i].comment.sources[]             — [{title, url, snippet}] supporting sources",
        "   jq extraction: .results.metadata | {cols: (.columns | map(.name)), rows: (.rows | map(.cells | map(.display_value)))}",
        "3. results.download_url is the enriched Excel file — every cell has the same "
        "validation detail embedded as hyperlinks and comments. Use it when you need "
        "a self-contained file to share or analyse offline.",
        "4. Always share results.interactive_viewer_url with human stakeholders — "
        "it renders sources, citations, and confidence scores in a clean UI that is "
        "far easier to navigate than raw JSON or spreadsheet formulas.",
        "5. If the response was too large and saved to a file, use jq to extract key fields: "
        "jq '.result[0].text | fromjson | .results.metadata | "
        "{cols: (.columns | map(.name)), rows: (.rows | map(.cells | map(.display_value)))}' <file>",
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
    }


def _guidance_get_reference_results(data: dict) -> dict:
    return {
        "summary": "Reference results fetched. Workflow complete.",
        "next_steps": [],
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
    return {
        "summary": "Reference-check job started. Use wait_for_job to track completion.",
        "next_steps": [
            {
                "tool": "wait_for_job",
                "params": {"job_id": job_id},
                "note": "Blocks until completed with live progress. Then call get_reference_results.",
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

    # Default: still processing (status == "processing" or unknown)
    return {
        "summary": "Table-maker conversation started. Wait for the AI's response.",
        "next_steps": [
            {
                "tool": "wait_for_conversation",
                "params": {
                    "conversation_id": conv_id,
                    "session_id": session_id,
                    "expected_seconds": 150,
                },
                "note": (
                    "Preferred: blocks with synthetic progress until the AI presents a table "
                    "structure or asks a clarifying question. First turn typically takes 2–3 min."
                ),
            },
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Fallback: one-shot poll — re-call every 15s manually.",
            },
        ],
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
    if action == "submit_preview":
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
            row_count_warning = ""
            if target_rows and int(target_rows) > 0:
                row_count_warning = (
                    f" WARNING: You requested {target_rows} rows, but the table builder may "
                    f"produce significantly more if it finds additional candidates — row count "
                    f"is not strictly enforced by the backend. Cost is proportional to actual "
                    f"rows built and is only visible at preview_complete. If this is a concern, "
                    f"reconsider the request scope before the table builder finishes."
                )
            return {
                "summary": (
                    "Table is being built. A preview validation job will start automatically "
                    "once the table maker finishes (typically 3–10 minutes). "
                    "Do NOT call create_job() — the preview is auto-queued. "
                    "Use wait_for_job(session_id) — it detects the phase transition and "
                    "tracks both the table-maker and preview phases with live progress."
                    + row_count_warning
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
        else:
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

    # Upload-interview terminal state: status=approved + trigger_config_generation=true.
    # The config has been generated; the preview is NOT auto-queued — agent must call create_job.
    if status == "approved" and data.get("trigger_config_generation"):
        return {
            "summary": (
                "Upload interview complete. The validation config has been generated and approved. "
                "Call create_job(session_id) now to start the 3-row preview — "
                "the preview is NOT auto-queued for upload-interview sessions."
            ),
            "next_steps": [
                {
                    "tool": "create_job",
                    "params": {"session_id": session_id},
                    "note": (
                        "Starts a 3-row preview using the generated config. "
                        "After preview_complete, review the results and call approve_validation."
                    ),
                },
                {
                    "tool": "refine_config",
                    "params": {
                        "conversation_id": conv_id,
                        "session_id": session_id,
                        "instructions": "<describe changes>",
                    },
                    "note": "Optional: refine the config before starting the preview.",
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
