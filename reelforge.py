# -*- coding: utf-8 -*-
"""
===================================================================================
ReelForge AI — Zero-Click AI Video & Reels Editor
Autonomous AI-driven Video Production Engine
===================================================================================
Automates high-retention video editing directly from code:
- Removes dead air & stutters automatically
- Transcribes with word-level Arabic timestamps using high-tier Whisper
- Adds kinetic Arabic captions with customizable styling (Default: Sleek Slate & Sky Blue, Cairo font)
- Dynamic camera zooms and face-tracking reframe
- Broadcast audio mastering to -14.0 LUFS
- Multi-platform exports: Final MP4 + CapCut Project
- First-frame cover injection (0.1s) respecting the 1080x1080 safe zone
===================================================================================
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path

# Fix Windows console UTF-8 output
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
FONTS_DIR = ROOT_DIR / "motion" / "fonts"

# Universal, modern, neutral default theme (Slate Dark & Sky Blue)
DEFAULT_THEME = {
    "bg": "#0F172A",       # Deep Slate Dark
    "ink": "#F8FAFC",      # Crisp White Text
    "acc": "#38BDF8",      # Sky Blue Accent
    "clay": "#0284C7",     # Accent Secondary
    "mut": "#94A3B8",      # Muted Subtext
    "font": "Cairo",       # Universal Arabic Font
    "capStyle": "card",    # High-contrast modern card caption style
    "grade": False,
    "faceAnchor": 0.30
}

def banner():
    print(r"""
===============================================================================
       ____           __ ______                       ___    ____ 
      / __ \___  ___ / // ____/___  _________ ____   /   |  /  _/ 
     / /_/ / _ \/ _ \/ // /_  / __ \/ ___/ __ `/ _ \ / /| |  / /   
    / _, _/  __/  __/ // __/ / /_/ / /  / /_/ /  __// ___ |_/ /    
   /_/ |_|\___/\___/_//_/    \____/_/   \__, /\___//_/  |_/___/    
                                       /____/                      
                  Autonomous AI Video & Reels Engine               
===============================================================================
    """)

def check_dependencies():
    """Verify system prerequisites (ffmpeg, node, python)."""
    missing = []
    for cmd in ["ffmpeg", "ffprobe", "node"]:
        if not shutil.which(cmd):
            missing.append(cmd)
    if missing:
        print(f"⚠️  Missing prerequisites: {', '.join(missing)}")
        print("Please ensure FFmpeg and Node.js are installed and in your system PATH.")
        if "ffmpeg" in missing:
            print("  - Install FFmpeg: https://ffmpeg.org/download.html")
        if "node" in missing:
            print("  - Install Node.js: https://nodejs.org/")
        return False
    return True

def setup_workdir(video_path, work_dir, theme_override=None):
    """Initializes workspace directory and sets up theme & configuration."""
    work = Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    
    # Check if a user profile exists from onboarding
    home_profile = Path.home() / ".video-ad-editor" / "profile.json"
    theme_data = DEFAULT_THEME.copy()
    
    if home_profile.exists():
        try:
            p = json.loads(home_profile.read_text(encoding="utf-8"))
            idn = p.get("identity") or {}
            cols = idn.get("colors")
            if cols:
                theme_data.update(cols)
            if p.get("font") and p["font"] != "auto":
                theme_data["font"] = p["font"]
            if p.get("capStyle") and p["capStyle"] != "auto":
                theme_data["capStyle"] = p["capStyle"]
        except Exception:
            pass

    # Copy source video
    src_video = work / "src.mp4"
    if not src_video.exists():
        print(f"📁 Copying source video into workspace -> {src_video}")
        shutil.copy2(video_path, src_video)
        
    # Write theme.json
    theme_file = work / "theme.json"
    if theme_override:
        theme_data.update(theme_override)
    with open(theme_file, "w", encoding="utf-8") as f:
        json.dump(theme_data, f, ensure_ascii=False, indent=2)
        
    return work, src_video

def extract_audio(src_video, work):
    """Extracts high quality audio for silence detection and transcription."""
    a_wav = work / "a.wav"
    if not a_wav.exists():
        print("🔊 Extracting audio from video...")
        cmd = [
            "ffmpeg", "-v", "error", "-y",
            "-i", str(src_video),
            "-vn", "-ar", "16000", "-ac", "1",
            str(a_wav)
        ]
        subprocess.run(cmd, check=True)
    return a_wav

def denoise_audio(work, strength=0.85, engine="auto"):
    """Intelligently cleans background noise (AC, street, hiss) via AI DeepFilterNet / FFmpeg FFT."""
    denoise_script = SCRIPTS_DIR / "02c_denoise.py"
    if denoise_script.exists():
        print(f"🧹 Running intelligent audio denoising (Engine: {engine}, Strength: {strength})...")
        cmd = [sys.executable, str(denoise_script), str(work), "--engine", engine, "--strength", str(strength)]
        try:
            subprocess.run(cmd, check=True)
        except Exception as e:
            print(f"⚠️ Audio denoising skipped or non-fatal error: {e}. Continuing pipeline.")

def run_silence_cut(work):
    """Analyzes audio and generates cut.json to eliminate dead air."""
    print("✂️  Analyzing silences and hesitations...")
    cut_script = SCRIPTS_DIR / "01_cut_plan.py"
    if cut_script.exists():
        cmd = [sys.executable, str(cut_script), str(work)]
        subprocess.run(cmd, check=True)

def run_transcription(work, model_tier="large-v3-turbo"):
    """Transcribes audio with word-level Arabic timestamps & cleans stutters."""
    print(f"🎙️  Running word-level Arabic transcription (Whisper: {model_tier})...")
    transcribe_script = SCRIPTS_DIR / "01b_transcribe.py"
    cmd = [sys.executable, str(transcribe_script), str(work), "--model", model_tier]
    subprocess.run(cmd, check=True)

def generate_captions(work):
    """Builds animated caption cards on the active timeline."""
    print("💬 Generating animated captions...")
    caps_script = SCRIPTS_DIR / "02_captions.py"
    cmd = [sys.executable, str(caps_script), str(work)]
    subprocess.run(cmd, check=True)

def apply_zooms_and_cuts(work):
    """Applies dynamic camera cuts and visual pacing zooms."""
    print("🔍 Applying smart cuts & camera zooms...")
    zoom_script = SCRIPTS_DIR / "03_cut_zoom.py"
    if zoom_script.exists():
        cmd = [sys.executable, str(zoom_script), str(work)]
        subprocess.run(cmd, check=True)

def render_motion_frames(work):
    """Renders motion graphics and captions into video overlay frames."""
    print("🎨 Rendering kinetic captions & motion graphics frames...")
    render_script = SCRIPTS_DIR / "04_render_frames.js"
    if render_script.exists():
        cmd = ["node", str(render_script), str(work)]
        subprocess.run(cmd, check=True)

def master_final_video(work):
    """Encodes final video and masters broadcast audio to -14.0 LUFS."""
    print("🎛️  Mastering video & audio (-14.0 LUFS Broadcast Standard)...")
    master_script = SCRIPTS_DIR / "06_encode_master.py"
    cmd = [sys.executable, str(master_script), str(work)]
    subprocess.run(cmd, check=True)

def export_capcut(work):
    """Generates an editable CapCut desktop project."""
    print("🎞️  Exporting editable CapCut project...")
    capcut_script = SCRIPTS_DIR / "40_capcut.py"
    if capcut_script.exists():
        cmd = [sys.executable, str(capcut_script), str(work)]
        try:
            subprocess.run(cmd, check=False)
        except Exception as e:
            print(f"Note: CapCut export skipped: {e}")

def main():
    banner()
    parser = argparse.ArgumentParser(
        description="ReelForge AI — Zero-Click AI Video & Reels Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("video", help="Path to raw talking-head video (MP4/MOV)")
    parser.add_argument("--work", default="workspace_reel", help="Workspace folder name (default: workspace_reel)")
    parser.add_argument("--model", choices=["large-v3", "large-v3-turbo", "medium", "small", "base"], default="large-v3-turbo", help="Whisper model tier (default: large-v3-turbo)")
    parser.add_argument("--denoise", choices=["auto", "dfn", "ffmpeg", "off"], default="auto", help="Smart AI/FFT noise reduction engine (default: auto)")
    parser.add_argument("--denoise-strength", type=float, default=0.85, help="Denoising strength 0.0 to 1.0 (default: 0.85)")
    parser.add_argument("--capcut", action="store_true", help="Also export as an editable CapCut project")
    parser.add_argument("--cover", help="Generate first-frame cover with headline: 'Line 1|*Colored Line 2*'")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video):
        print(f"❌ Input video not found: {args.video}")
        sys.exit(1)
        
    if not check_dependencies():
        print("Please resolve missing tools to proceed.")
        sys.exit(1)
        
    print(f"🚀 Processing: {args.video}")
    work, src_video = setup_workdir(args.video, args.work)
    
    # Pipeline execution
    extract_audio(src_video, work)
    if args.denoise != "off":
        denoise_audio(work, strength=args.denoise_strength, engine=args.denoise)
    run_silence_cut(work)
    run_transcription(work, model_tier=args.model)
    generate_captions(work)
    apply_zooms_and_cuts(work)
    render_motion_frames(work)
    master_final_video(work)
    
    if args.capcut:
        export_capcut(work)
        
    final_master = work / "ad-master.mp4"
    print("\n" + "="*70)
    print(f"🎉 Reel creation completed successfully!")
    print(f"📍 Master Video Ready: {final_master}")
    if args.capcut:
        print(f"📍 CapCut Draft Ready: {work / 'draft_content.json'}")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
