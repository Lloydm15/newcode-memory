#!/bin/bash
# Hook: Stop
# Automatically stores conversation exchanges in newcode memory.
# Reads the user prompt saved by capture-prompt.sh and the assistant's
# last response from the hook input, then POSTs to /ingest and /feedback.

# Server URL — override with NEWCODE_SERVER_URL env var
SERVER_URL="${NEWCODE_SERVER_URL:-http://localhost:4000}"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
ASSISTANT_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // empty')

if [ -z "$SESSION_ID" ] || [ -z "$ASSISTANT_MSG" ]; then
  exit 0
fi

TMPDIR="${TMPDIR:-/tmp}"

# Read saved user prompt (already cleaned by capture-prompt.sh)
PROMPT_FILE="${TMPDIR}/newcode-prompt-${SESSION_ID}"
if [ ! -f "$PROMPT_FILE" ]; then
  exit 0
fi
USER_MSG=$(cat "$PROMPT_FILE")

# Strip system tags from assistant message too, in case any leak through
ASSISTANT_MSG=$(echo "$ASSISTANT_MSG" \
  | sed '/<system-reminder>/,/<\/system-reminder>/d' \
  | sed '/<task-notification>/,/<\/task-notification>/d' \
  | sed '/<ide_opened_file>/,/<\/ide_opened_file>/d' \
  | sed '/<ide_selection>/,/<\/ide_selection>/d' \
  | sed '/^[[:space:]]*$/d')

# Skip if either side is empty after cleaning
if [ -z "$USER_MSG" ] || [ -z "$ASSISTANT_MSG" ]; then
  exit 0
fi

# Skip trivial exchanges (very short messages like "ok", "yes", "no")
if [ ${#USER_MSG} -lt 10 ] && [ ${#ASSISTANT_MSG} -lt 50 ]; then
  exit 0
fi

# Use the MCP server's conversation ID if available (aligns with retrieval_log entries).
# Falls back to session-based ID if MCP server hasn't started.
MCP_CONVID_FILE="${TMPDIR}/newcode-mcp-convid"
if [ -f "$MCP_CONVID_FILE" ]; then
  CONV_ID=$(cat "$MCP_CONVID_FILE")
else
  CONV_ID="claude-code-${SESSION_ID}"
fi

# Machine identifier — hostname of whatever computer is running this hook
MACHINE_NAME=$(hostname 2>/dev/null || echo "unknown")

# POST to newcode ingest endpoint
curl -s -X POST "${SERVER_URL}/ingest" \
  -H "Content-Type: application/json" \
  --max-time 10 \
  -d "$(jq -n \
    --arg user "$USER_MSG" \
    --arg assistant "$ASSISTANT_MSG" \
    --arg conv_id "$CONV_ID" \
    --arg machine "$MACHINE_NAME" \
    '{
      messages: [
        {role: "user", content: $user},
        {role: "assistant", content: $assistant}
      ],
      user_id: "lloyd",
      conversation_id: $conv_id,
      source_machine: $machine
    }')" > /dev/null 2>&1 || true

# Run the feedback judge
curl -s -X POST "${SERVER_URL}/feedback" \
  -H "Content-Type: application/json" \
  --max-time 30 \
  -d "$(jq -n \
    --arg conv_id "$CONV_ID" \
    --arg query "$USER_MSG" \
    --arg response "$ASSISTANT_MSG" \
    '{
      conversation_id: $conv_id,
      user_id: "lloyd",
      query_text: $query,
      response_text: $response
    }')" > /dev/null 2>&1 || true

exit 0
