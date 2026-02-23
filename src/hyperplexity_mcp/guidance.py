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
    # External API returns "matches" (not "config_matches")
    matches = data.get("matches") or data.get("config_matches") or []
    best_score = matches[0].get("match_score", 0) if matches else 0

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
                {
                    "tool": "start_upload_interview",
                    "params": {"session_id": session_id, "message": ""},
                    "note": "Optional: start an AI interview to build or modify a config instead.",
                },
            ],
        }
    else:
        return {
            "summary": (
                "Upload confirmed. No strong prior config match — start an AI interview "
                "to generate a config, or provide one manually."
            ),
            "next_steps": [
                {
                    "tool": "start_upload_interview",
                    "params": {"session_id": session_id, "message": ""},
                    "note": "Recommended: AI-guided interview to create a validation config.",
                },
                {
                    "tool": "create_job",
                    "params": {
                        "session_id": session_id,
                        "config": "<paste config JSON here>",
                    },
                    "note": "Alternative: supply your own config JSON directly.",
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
    # the original table maker run (not the preview job).  Direct the agent to
    # get_job_messages (which shows live progress_update messages) and then
    # approve_validation (a 409 means still in progress — wait and retry).
    if job_id.startswith("session_") and run_type == "preview":
        return {
            "summary": (
                f"Preview job created (status={status}). "
                "IMPORTANT: get_job_status may return stale table maker data (status=completed, "
                "current_step='Config Generation') for this session ID — this reflects the "
                "table maker run, not the preview. "
                "Use get_job_messages to track live preview progress instead. "
                "When messages show completion (card_id='preview', 100%), call get_job_status — "
                "it should now return status=preview_complete with cost_estimate and config_id. "
                "Save config_id for future reruns. Then call approve_validation with approved_cost_usd."
            ),
            "next_steps": [
                {
                    "tool": "get_job_messages",
                    "params": {"job_id": job_id},
                    "note": (
                        "Monitor progress_update messages (card_id='preview') for real-time "
                        "progress. Keep polling until messages show 100% or stop arriving."
                    ),
                },
                {
                    "tool": "get_job_status",
                    "params": {"job_id": job_id},
                    "note": (
                        "After messages indicate completion, call this to get preview_complete "
                        "state with cost_estimate and config_id."
                    ),
                },
            ],
        }

    return {
        "summary": f"Job created (status={status}). Poll for status updates.",
        "next_steps": [
            {
                "tool": "get_job_status",
                "params": {"job_id": job_id},
                "note": "Poll every 10s until status changes from 'queued' or 'processing'.",
            }
        ],
    }


def _guidance_get_job_status(data: dict) -> dict:
    job_id = data.get("job_id", "")
    status = data.get("status", "")

    if status in ("queued", "processing"):
        return {
            "summary": f"Job is {status}. Keep polling.",
            "next_steps": [
                {
                    "tool": "get_job_status",
                    "params": {"job_id": job_id},
                    "note": "Poll again in ~10 seconds.",
                },
                {
                    "tool": "get_job_messages",
                    "params": {"job_id": job_id},
                    "note": "Optional: fetch live progress messages from the job.",
                },
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
        # Fix #2: table maker jobs complete with "Config Generation" in current_step.
        # Their results live in the web viewer, not the /results endpoint.
        current_step = data.get("current_step", "")
        if "Config Generation" in current_step:
            # Table maker has finished and written the validation config to S3.
            # create_job(session_id=...) will now succeed.
            # After the preview completes, get_job_status returns preview_complete with:
            #   - config_id  — save this for future reruns
            #   - cost_estimate.estimated_total_cost_usd — pass as approved_cost_usd to approve_validation
            #   - preview_results.download_url — review the 3 preview rows before approving
            return {
                "summary": (
                    "Table maker complete. The validation config is now saved. "
                    "Call create_job to start a preview (required before full validation). "
                    "After preview_complete: review the rows, note the config_id and estimated cost, "
                    "then call approve_validation to run full validation on all rows."
                ),
                "next_steps": [
                    {
                        "tool": "create_job",
                        "params": {"session_id": job_id},
                        "note": (
                            "The config was generated by the table maker and is now stored in the session."
                        ),
                    }
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
    }
    if found_urls:
        result["found_urls"] = found_urls
    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _guidance_approve_validation(data: dict) -> dict:
    job_id = data.get("job_id", "")
    status = data.get("status", "")
    return {
        "summary": f"Validation approved. Job is now {status}. Poll for completion.",
        "next_steps": [
            {
                "tool": "get_job_status",
                "params": {"job_id": job_id},
                "note": "Poll every 10-15s. Status will move to 'completed' when done.",
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
        "summary": "Update-table job started. Poll for status.",
        "next_steps": [
            {
                "tool": "get_job_status",
                "params": {"job_id": job_id},
                "note": "Poll until completed.",
            }
        ],
    }


def _guidance_reference_check(data: dict) -> dict:
    job_id = data.get("job_id", "")
    return {
        "summary": "Reference-check job started. Poll for status.",
        "next_steps": [
            {
                "tool": "get_job_status",
                "params": {"job_id": job_id},
                "note": "Poll until completed, then call get_reference_results.",
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
            "summary": "Table-maker finished immediately. Fetch the conversation for results.",
            "next_steps": [
                {
                    "tool": "get_conversation",
                    "params": {"conversation_id": conv_id, "session_id": session_id},
                    "note": "Retrieve the completed table and any next-step instructions.",
                }
            ],
        }

    # Default: still processing (status == "processing" or unknown)
    return {
        "summary": "Table-maker conversation started. Poll for its response.",
        "next_steps": [
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Poll every 8s while status is 'processing'.",
            }
        ],
    }


def _guidance_start_upload_interview(data: dict) -> dict:
    conv_id = data.get("conversation_id", "")
    session_id = data.get("session_id", "")
    return {
        "summary": "Upload interview started. Poll the conversation for the AI's first question.",
        "next_steps": [
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Poll every 8s while status is 'processing'.",
            }
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
            "summary": "Conversation is still processing. Poll again in 8s.",
            "next_steps": [
                {
                    "tool": "get_conversation",
                    "params": {"conversation_id": conv_id, "session_id": session_id},
                    "note": "Poll every 8 seconds.",
                }
            ],
        }

    action = next_step.get("action", "")
    if action == "submit_preview":
        trigger_execution = data.get("trigger_execution") or next_step.get("trigger_execution")
        if trigger_execution:
            # The table maker is NOW RUNNING — it has NOT completed yet.
            # The validation config is written to S3 only when execution finishes.
            # DO NOT call create_job yet — it will fail with missing_config because
            # the config doesn't exist until "Config Generation completed" appears
            # in get_job_status.  Poll get_job_status until that state, then call
            # create_job (the next step will appear in its guidance automatically).
            return {
                "summary": (
                    "Table maker row generation is now running. "
                    "DO NOT call create_job yet — the validation config is saved only when "
                    "the table maker finishes (typically 3–10 minutes). "
                    "Poll get_job_status every 15s until status=completed AND "
                    "current_step contains 'Config Generation completed'. "
                    "The guidance on that response will tell you to call create_job."
                ),
                "next_steps": [
                    {
                        "tool": "get_job_status",
                        "params": {"job_id": session_id},
                        "note": (
                            "Poll every 15s. Wait for status='completed' AND "
                            "'Config Generation' in current_step before calling create_job."
                        ),
                    },
                ],
            }
        else:
            # Upload-interview flow: config is already stored; create the preview job.
            return {
                "summary": (
                    "Interview complete. The session holds the generated config. "
                    "Create a preview job to validate a sample before running the full set."
                ),
                "next_steps": [
                    {
                        "tool": "create_job",
                        "params": {"session_id": session_id},
                        "note": "The config is embedded in the session.",
                    },
                    {
                        "tool": "refine_config",
                        "params": {
                            "conversation_id": conv_id,
                            "session_id": session_id,
                            "instructions": "<describe changes>",
                        },
                        "note": "Optional: refine the config before creating a job.",
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
        "summary": "Reply sent. Poll the conversation for the AI's next message.",
        "next_steps": [
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Poll every 8s while the AI is processing.",
            }
        ],
    }


def _guidance_refine_config(data: dict) -> dict:
    conv_id = data.get("conversation_id", "")
    session_id = data.get("session_id", "")
    return {
        "summary": "Config refinement submitted. Poll the conversation for the result.",
        "next_steps": [
            {
                "tool": "get_conversation",
                "params": {"conversation_id": conv_id, "session_id": session_id},
                "note": "Poll every 8s for the refined config response.",
            }
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
    "get_job_messages": _guidance_get_job_messages,
    "approve_validation": _guidance_approve_validation,
    "get_results": _guidance_get_results,
    "get_reference_results": _guidance_get_reference_results,
    "update_table": _guidance_update_table,
    "reference_check": _guidance_reference_check,
    "start_table_maker": _guidance_start_table_maker,
    "start_upload_interview": _guidance_start_upload_interview,
    "get_conversation": _guidance_get_conversation,
    "send_conversation_reply": _guidance_send_conversation_reply,
    "refine_config": _guidance_refine_config,
    "get_balance": _guidance_get_balance,
    "get_usage": _guidance_get_usage,
}
