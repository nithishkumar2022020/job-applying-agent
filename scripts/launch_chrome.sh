#!/usr/bin/env bash
# ==============================================================================
# launch_chrome.sh - Launch Chrome with CDP Remote Debugging on macOS
# ==============================================================================
# This script launches your genuine Google Chrome instance with remote debugging
# enabled on port 9222. When you log into LinkedIn, Greenhouse, Lever, etc. in
# this Chrome window, all session cookies and anti-bot trust scores are preserved.
# ==============================================================================

PORT=9222
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_DATA_DIR="$HOME/Library/Application Support/Google/Chrome/StealthJobAgentProfile"

echo "🔍 Checking if Chrome is already running on port ${PORT}..."
if curl -s "http://127.0.0.1:${PORT}/json/version" > /dev/null 2>&1; then
    echo "✅ Chrome CDP is ALREADY active on port ${PORT}!"
    echo "   You can immediately run the agent."
    exit 0
fi

if [ ! -f "$CHROME_BIN" ]; then
    echo "❌ Error: Google Chrome not found at $CHROME_BIN"
    exit 1
fi

echo "🚀 Launching Chrome with CDP enabled on port ${PORT}..."
echo "📂 Profile Directory: ${USER_DATA_DIR}"
echo ""
echo "💡 TIP: Log in to LinkedIn and your target job sites in this Chrome window."
echo "        Your login cookies, 2FA, and sessions will remain permanently active."
echo ""

mkdir -p "$USER_DATA_DIR"

exec "$CHROME_BIN" \
    --remote-debugging-port=${PORT} \
    --user-data-dir="${USER_DATA_DIR}" \
    --no-first-run \
    --no-default-browser-check \
    --restore-last-session \
    "https://www.linkedin.com/jobs" > /dev/null 2>&1 &

sleep 2

if curl -s "http://127.0.0.1:${PORT}/json/version" > /dev/null 2>&1; then
    echo "🎉 Chrome successfully started and listening on http://127.0.0.1:${PORT}"
else
    echo "⚠️ Chrome started. Please ensure port ${PORT} is accessible."
fi
