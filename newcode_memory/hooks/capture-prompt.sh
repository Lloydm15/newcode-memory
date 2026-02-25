#!/bin/bash
# Hook: UserPromptSubmit
# Saves the user's prompt to a temp file keyed by session ID.
# The Stop hook picks this up to send both sides to /ingest.

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

if [ -z "$SESSION_ID" ] || [ -z "$PROMPT" ]; then
  exit 0
fi

# Strip system tags — these are injected by Claude Code, not typed by the user
CLEAN=$(echo "$PROMPT" \
  | sed '/<system-reminder>/,/<\/system-reminder>/d' \
  | sed '/<ide_opened_file>/,/<\/ide_opened_file>/d' \
  | sed '/<ide_selection>/,/<\/ide_selection>/d' \
  | sed '/<task-notification>/,/<\/task-notification>/d' \
  | sed '/^[[:space:]]*$/d')

# After stripping, skip if nothing meaningful remains
if [ -z "$CLEAN" ] || [ ${#CLEAN} -lt 5 ]; then
  exit 0
fi

# Save cleaned prompt for the Stop hook to pick up
TMPDIR="${TMPDIR:-/tmp}"
echo "$CLEAN" > "${TMPDIR}/newcode-prompt-${SESSION_ID}"
exit 0
