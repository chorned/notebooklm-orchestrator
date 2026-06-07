#!/bin/bash
# =====================================================================
# PODCAST ENGINE - AUTONOMOUS BOOTSTRAPPER
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

# 1. Ensure a clean environment
if [ ! -d "venv" ]; then
    echo "⚠️  Building fresh sandbox..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip

    echo "📦 Installing required dependencies..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "✅ Environment ready."

# 2. Launch the Orchestrator
# We use 'exec' so Python completely takes over the process,
# ensuring clean exits when you press Ctrl+C.
echo "🚀 Starting Podcast Engine Worker..."
exec python3 podcast_worker.py