#!/usr/bin/env bash
# Stop hook: Claude can't end a turn with `make check` failing.
#
# - No changes in the working tree: nothing to check, so conversation-only turns stay fast.
# - First failure: exit 2, which sends the output to Claude and keeps it working.
# - Failing again on the retry (stop_hook_active): let the turn end, and warn the user,
#   so a failure that needs a human can't loop forever.
set -uo pipefail

input="$(cat)"
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
    exit 0
fi

if output="$(make check 2>&1)"; then
    exit 0
fi

retrying="$(printf '%s' "$input" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("stop_hook_active", False))' 2>/dev/null)"
if [ "$retrying" = "True" ]; then
    printf '{"systemMessage": "make check is still failing after one retry; the turn ended anyway."}\n'
    exit 0
fi

{
    echo "make check failed. Fix it before finishing. Last 80 lines:"
    printf '%s\n' "$output" | tail -n 80
} >&2
exit 2
