#!/usr/bin/env bash
# Islam AI ReelForge — macOS & Linux Launcher
set -e

echo "==============================================================================="
echo "               🎬 Welcome to Islam AI ReelForge"
echo "        Zero-Click AI Video & Reels Editor for Content Creators"
echo "==============================================================================="
echo ""

if [ -z "$1" ]; then
    read -p "Drag and drop your video file here (or type path): " VIDEO_PATH
else
    VIDEO_PATH="$1"
fi

# Clean path
VIDEO_PATH=$(echo "$VIDEO_PATH" | tr -d "'\"")

if [ ! -f "$VIDEO_PATH" ]; then
    echo "❌ Error: File not found: $VIDEO_PATH"
    exit 1
fi

echo "🚀 Starting ReelForge Pipeline..."
python3 reelforge.py "$VIDEO_PATH" --capcut

echo "==============================================================================="
echo "✅ Finished! Your mastered video is ready in workspace_reel/ad-master.mp4"
echo "==============================================================================="
