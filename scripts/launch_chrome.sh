#!/usr/bin/env bash
# ==============================================================================
# launch_chrome.sh - Launch Chrome with CDP Remote Debugging on macOS
# ==============================================================================

PORT=9222
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_PROFILE="$HOME/Library/Application Support/Google/Chrome"
AGENT_PROFILE="$HOME/Library/Application Support/Google/Chrome/StealthJobAgentProfile"

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

USE_REAL_PROFILE=false
if [ "$1" == "--real" ] || [ "$1" == "--default" ]; then
    USE_REAL_PROFILE=true
fi

if [ "$USE_REAL_PROFILE" = true ]; then
    echo "🚀 Launching Chrome using your REAL DEFAULT PROFILE (already logged in!)..."
    echo "⚠️ NOTE: Please make sure regular Chrome was closed first (Cmd + Q)."
    
    exec "$CHROME_BIN" \
        --remote-debugging-port=${PORT} \
        --disable-blink-features=AutomationControlled \
        --restore-last-session \
        "https://www.linkedin.com/jobs" > /dev/null 2>&1 &
else
    echo "🚀 Launching Chrome with dedicated Stealth Profile..."
    echo "📂 Profile: ${AGENT_PROFILE}"
    echo ""
    echo "💡 IMPORTANT FOR LOGIN:"
    echo "   • On LinkedIn, log in using your EMAIL & PASSWORD."
    echo "   • DO NOT click 'Sign in with Google' (Google blocks remote debugging with a blank screen)."
    echo "   • Alternatively, run: bash scripts/launch_chrome.sh --real to use your already-logged-in profile."
    echo ""

    mkdir -p "$AGENT_PROFILE"

    exec "$CHROME_BIN" \
        --remote-debugging-port=${PORT} \
        --user-data-dir="${AGENT_PROFILE}" \
        --disable-blink-features=AutomationControlled \
        --no-first-run \
        --no-default-browser-check \
        --restore-last-session \
        "https://www.linkedin.com/jobs" > /dev/null 2>&1 &
fi

sleep 2

if curl -s "http://127.0.0.1:${PORT}/json/version" > /dev/null 2>&1; then
    echo "🎉 Chrome successfully started on http://127.0.0.1:${PORT}"
else
    echo "⚠️ Chrome started. Port 9222 will be active once Chrome opens."
fi
