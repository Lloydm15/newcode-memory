"""
MCP server for newcode memory system.
Exposes tools for Claude Code: retrieve memories, store conversations, run feedback.
Runs via stdio transport (Claude Code spawns this as a subprocess).

Calls the newcode HTTP API instead of using Mem0 directly.
"""

import json
import os
import socket
import sys
import tempfile
from uuid import uuid4

import httpx
from mcp.server.fastmcp import FastMCP

# Server URL — set via environment variable or default to localhost
API_BASE = os.environ.get("NEWCODE_SERVER_URL", "http://localhost:4000")

# Machine identifier — hostname of whatever computer is running this MCP server
_MACHINE_NAME = socket.gethostname()

# Session-level conversation ID — all tool calls in one MCP session share the same ID.
_session_conversation_id = str(uuid4())

# Write the conversation ID to a temp file so hooks can use the same ID.
_CONVID_FILE = os.path.join(tempfile.gettempdir(), "newcode-mcp-convid")
try:
    with open(_CONVID_FILE, "w") as f:
        f.write(_session_conversation_id)
except OSError:
    pass

mcp = FastMCP("newcode-memory")


@mcp.tool()
async def retrieve_memories(query: str, user_id: str = "lloyd") -> str:
    """
    Search for memories relevant to a query.
    Returns memories ranked by relevance with feedback adjustments.
    Call this before responding to get context from past conversations.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_BASE}/retrieve", json={
            "query": query,
            "user_id": user_id,
            "conversation_id": _session_conversation_id,
        })
        data = r.json()

    memories = data.get("memories", [])

    if not memories:
        return json.dumps({"memories": [], "conversation_id": _session_conversation_id})

    return json.dumps({
        "memories": [
            {"memory": m["memory"], "score": round(m["score"], 3), "rank": m["rank"]}
            for m in memories
        ],
        "conversation_id": _session_conversation_id,
    })


@mcp.tool()
async def store_conversation(
    user_message: str,
    assistant_response: str,
    user_id: str = "lloyd",
    conversation_id: str = "",
) -> str:
    """
    Store memories from a conversation exchange.
    Extracts facts, preferences, and rules from both the user message and assistant response.
    Call this after responding to save what was learned.

    IMPORTANT: Pass the COMPLETE user message and COMPLETE assistant response.
    Do NOT summarize or truncate. The full text is needed for accurate memory extraction.
    """
    conv_id = conversation_id if conversation_id else _session_conversation_id

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{API_BASE}/ingest", json={
            "messages": [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_response},
            ],
            "user_id": user_id,
            "conversation_id": conv_id,
            "source_machine": _MACHINE_NAME,
        })
        data = r.json()

    return json.dumps({"status": data.get("status", "stored"), "conversation_id": conv_id})


@mcp.tool()
async def judge_memories(
    conversation_id: str,
    query_text: str,
    response_text: str,
    user_id: str = "lloyd",
) -> str:
    """
    Run the feedback judge on memories retrieved during a conversation.
    Evaluates whether each retrieved memory was useful, correct, or irrelevant.
    Call this after responding to improve future retrieval.
    """
    conv_id = conversation_id if conversation_id else _session_conversation_id

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{API_BASE}/feedback", json={
            "conversation_id": conv_id,
            "user_id": user_id,
            "query_text": query_text,
            "response_text": response_text,
        })
        data = r.json()

    return json.dumps({"status": data.get("status", "judged"), "conversation_id": conv_id})


if __name__ == "__main__":
    mcp.run(transport="stdio")
