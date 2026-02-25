#!/usr/bin/env python3
"""
Hook: Stop
Automatically stores conversation exchanges in newcode memory.
Reads the user prompt saved by capture-prompt.py and the assistant's
last response from the hook input, then POSTs to /ingest and /feedback.
Works on Windows, macOS, and Linux.
"""

import json
import os
import re
import socket
import sys
import tempfile
import urllib.request
import urllib.error


def strip_system_tags(text: str) -> str:
    patterns = [
        r'<system-reminder>.*?</system-reminder>',
        r'<ide_opened_file>.*?</ide_opened_file>',
        r'<ide_selection>.*?</ide_selection>',
        r'<task-notification>.*?</task-notification>',
    ]
    for p in patterns:
        text = re.sub(p, '', text, flags=re.DOTALL)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


def post_json(url: str, payload: dict, timeout: int = 15) -> None:
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except Exception:
        pass


def main():
    server_url = os.environ.get('NEWCODE_SERVER_URL', 'http://localhost:4000')

    # Parse --server arg if provided
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == '--server' and i + 1 < len(args):
            server_url = args[i + 1]

    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    session_id = data.get('session_id', '')
    assistant_msg = data.get('last_assistant_message', '')

    if not session_id or not assistant_msg:
        sys.exit(0)

    tmpdir = tempfile.gettempdir()

    # Read saved user prompt
    prompt_file = os.path.join(tmpdir, f'newcode-prompt-{session_id}')
    if not os.path.exists(prompt_file):
        sys.exit(0)

    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            user_msg = f.read().strip()
    except OSError:
        sys.exit(0)

    assistant_msg = strip_system_tags(assistant_msg)

    if not user_msg or not assistant_msg:
        sys.exit(0)

    # Skip trivial exchanges
    if len(user_msg) < 10 and len(assistant_msg) < 50:
        sys.exit(0)

    # Use MCP server's conversation ID if available
    mcp_convid_file = os.path.join(tmpdir, 'newcode-mcp-convid')
    if os.path.exists(mcp_convid_file):
        try:
            with open(mcp_convid_file, 'r', encoding='utf-8') as f:
                conv_id = f.read().strip()
        except OSError:
            conv_id = f'claude-code-{session_id}'
    else:
        conv_id = f'claude-code-{session_id}'

    machine_name = socket.gethostname()

    # POST to /ingest
    post_json(f'{server_url}/ingest', {
        'messages': [
            {'role': 'user', 'content': user_msg},
            {'role': 'assistant', 'content': assistant_msg},
        ],
        'user_id': 'lloyd',
        'conversation_id': conv_id,
        'source_machine': machine_name,
    }, timeout=10)

    # POST to /feedback
    post_json(f'{server_url}/feedback', {
        'conversation_id': conv_id,
        'user_id': 'lloyd',
        'query_text': user_msg,
        'response_text': assistant_msg,
    }, timeout=30)


if __name__ == '__main__':
    main()
