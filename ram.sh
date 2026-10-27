#!/usr/bin/env bash
# Video AI Studio — Onboarding Launcher for macOS & Linux
set -e

echo "==============================================================================="
echo "               🎬 Video AI Studio — Onboarding Launcher"
echo "==============================================================================="
echo ""
echo "🚀 Starting Onboarding Web Server at http://127.0.0.1:4321/ ..."
echo "🌐 Your default web browser will open automatically."
echo "💡 Set your style, colors, and font in the browser, then summon your AI agent!"
echo "🤖 Tell your agent: 'منتج هذا الفيديو' or 'make a reel from this video'"
echo ""
echo "Press Ctrl+C to terminate the onboarding server."
echo "==============================================================================="

python3 scripts/00_onboard.py serve --keep-alive --port 4321
