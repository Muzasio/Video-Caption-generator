#!/usr/bin/env bash
# Scan the repo for personal info before a push. Exit 1 if anything is found.
# Usage: bash check-clean.sh
set -euo pipefail
cd "$(dirname "$0")"

# Built at runtime so this script itself never holds personal info.
patterns=(
    "/home/[A-Za-z0-9_-]+"
    "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b"
    "PrivateKey[[:space:]]*=[[:space:]]*[A-Za-z0-9+/]{20,}"
)
[ -n "${USER:-}" ] && patterns+=("\b${USER}\b")
host="$(cat /etc/hostname 2>/dev/null || true)"
[ -n "$host" ] && patterns+=("\b${host}\b")

# 0.0.0.0 and 127.x are not personal; check-clean.sh itself is the list.
found=0
for p in "${patterns[@]}"; do
    if grep -rInE --exclude-dir=.git --exclude=check-clean.sh -- "$p" . \
        | grep -vE '\b(0\.0\.0\.0|127\.[0-9.]+)\b'; then
        found=1
    fi
done

for f in .env ./*.key ./*.pem; do
    [ -e "$f" ] && { echo "Secret-looking file in repo: $f"; found=1; }
done

if [ "$found" -eq 0 ]; then
    echo "Clean: no personal info found."
else
    echo "Personal info found above. Fix before pushing." >&2
    exit 1
fi
