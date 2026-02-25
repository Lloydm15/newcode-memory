#!/usr/bin/env python3
"""
Hook: UserPromptSubmit
Saves the user's prompt to a temp file keyed by session ID.
The Stop hook picks this up to send both sides to /ingest.
Works on Windows, macOS, and Linux.
"""

import json
import os
import re
import sys
import tempfile


def strip_system_tags(text: str) -> str:
    patterns = [
        r'<system-reminder>.*?</system-reminder>',
        r'<ide_opened_file>.*?</ide_opened_file>',
        r'<ide_selection>.*?</ide_selection>',
        r'<task-notification>.*?</task-notification>',
    ]
    for p in patterns:
        text = re.sub(p, '', text, flags=re.DOTALL)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    session_id = data.get('session_id', '')
    prompt = data.get('prompt', '')

    if not session_id or not prompt:
        sys.exit(0)

    clean = strip_system_tags(prompt)
    if not clean or len(clean) < 5:
        sys.exit(0)

    tmpdir = tempfile.gettempdir()
    prompt_file = os.path.join(tmpdir, f'newcode-prompt-{session_id}')
    try:
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(clean)
    except OSError:
        pass


if __name__ == '__main__':
    main()
