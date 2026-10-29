# Binary & Model Tools Directory

Binary executables and model weights (such as `deep-filter` and Whisper `.pt` models) are **NOT stored directly in this repository** to keep the project lightweight and fast to clone.

Instead, ReelForge automatically:
1. Detects tools in your system PATH.
2. Checks the user cache at `~/.cache/reelforge/bin/`.
3. Downloads precompiled binaries/models dynamically on demand if requested.
4. Falls back seamlessly to built-in FFmpeg filters if offline.
