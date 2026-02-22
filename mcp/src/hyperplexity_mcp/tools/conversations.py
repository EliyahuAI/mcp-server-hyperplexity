"""Conversation tools: start_table_maker, start_upload_interview,
get_conversation, send_conversation_reply, refine_config.
"""

from __future__ import annotations

import json
from typing import Optional

from mcp import types

from hyperplexity_mcp.client import get_client
from hyperplexity_mcp.guidance import build_guidance


def register(server):
    client = get_client()

    @server.tool()
    def start_table_maker(message: str) -> list[types.TextContent]:
        """Start a Table Maker conversation to generate a research table.

        Describe the table you want in natural language, e.g.:
        'Create a table of AI startups that raised Series A in 2024 with columns:
        company name, funding amount, investors, product description.'
        """
        data = client.post("/conversations/table-maker", json={"message": message})
        data["_guidance"] = build_guidance("start_table_maker", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def start_upload_interview(
        session_id: str,
        message: Optional[str] = None,
    ) -> list[types.TextContent]:
        """Start an AI interview to build a validation config for an uploaded file.

        The AI will ask questions about your columns and validation goals.
        Optionally provide an initial message to pre-fill context.
        """
        payload: dict = {"session_id": session_id}
        if message:
            payload["message"] = message

        data = client.post("/conversations/upload-interview", json=payload)
        data["_guidance"] = build_guidance("start_upload_interview", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def get_conversation(
        conversation_id: str,
        session_id: str,
    ) -> list[types.TextContent]:
        """Poll a conversation for new messages or a status change.

        Key statuses:
          processing       → poll again in ~8s
          user_reply_needed → send_conversation_reply
          next_step.action = submit_preview → create_job(session_id)
        """
        data = client.get(f"/conversations/{conversation_id}", params={"session_id": session_id})
        data.setdefault("conversation_id", conversation_id)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("get_conversation", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def send_conversation_reply(
        conversation_id: str,
        session_id: str,
        message: str,
    ) -> list[types.TextContent]:
        """Send a user reply in an ongoing conversation (interview or table-maker).

        After sending, poll get_conversation for the AI's next response.
        """
        payload = {"session_id": session_id, "message": message}
        data = client.post(f"/conversations/{conversation_id}/message", json=payload)
        data.setdefault("conversation_id", conversation_id)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("send_conversation_reply", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    @server.tool()
    def refine_config(
        conversation_id: str,
        session_id: str,
        instructions: str,
    ) -> list[types.TextContent]:
        """Refine the generated validation config using natural language instructions.

        Example instructions:
        'Add a column for LinkedIn URL. Remove the revenue column. Make email validation stricter.'
        """
        payload = {"session_id": session_id, "instructions": instructions}
        data = client.post(f"/conversations/{conversation_id}/refine-config", json=payload)
        data.setdefault("conversation_id", conversation_id)
        data.setdefault("session_id", session_id)
        data["_guidance"] = build_guidance("refine_config", data)
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
