#!/bin/bash
# Monthly Google Ads invoice: starts Brave, runs run-month, quits Brave.
# Called by launchd on the 2nd of each month.

set -euo pipefail

LOG_DIR="$HOME/.gmail/logs"
mkdir -p "$LOG_DIR"

# Start Brave with remote debugging
"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  --remote-debugging-port=9222 \
  --no-first-run \
  --disable-extensions \
  > "$LOG_DIR/brave-stdout.log" 2> "$LOG_DIR/brave-stderr.log" &

BRAVE_PID=$!
echo "Brave started (PID $BRAVE_PID)" >> "$LOG_DIR/monthly.log"

# Wait for Brave to be ready
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    echo "Brave ready after ${i}s" >> "$LOG_DIR/monthly.log"
    break
  fi
  sleep 1
done

# Activate mamba env and run
source "$HOME/Software/miniforge3/etc/profile.d/conda.sh" 2>/dev/null || true
eval "$(conda shell.bash hook)"
conda activate invoice-admin

export GOOGLEADS_GMAIL_OAUTH_TOKEN="$HOME/.gmail/gmail_readonly_token.json"
export GOOGLEADS_GMAIL_SMTP_APP_PASSWORD_FILE="$HOME/.gmail/gmail-smtp-app-password"
export GOOGLEADS_GMAIL_SMTP_USER="chaehan.so@gmail.com"
export GOOGLEADS_BROWSER_DEBUGGER_ADDRESS="127.0.0.1:9222"

echo "Running run-month..." >> "$LOG_DIR/monthly.log"
cd "$HOME/Software/Prototypes/invoice-admin"
invoice send --yes >> "$LOG_DIR/monthly.log" 2>&1

echo "Done. Stopping Brave..." >> "$LOG_DIR/monthly.log"
kill "$BRAVE_PID" 2>/dev/null || true
