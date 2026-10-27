# -*- coding: utf-8 -*-
"""Automated Word-Level Arabic Transcription & Stutter Filter for AI Video Editor.
Defaults to high-tier large model (large-v3-turbo) and allows dynamic agent/user model selection.
"""
import os, sys, json, subprocess, re, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def get_whisper_model(requested_model=None):
    if requested_model:
        if os.path.exists(requested_model):
            return requested_model
        return requested_model

    custom_env = os.environ.get("WHISPER_MODEL") or os.environ.get("WHISPER_MODEL_PATH")
    if custom_env:
        return custom_env

    # Check local cache for high-tier large models if already present
    local_cache_turbo = os.path.expanduser(r"~/.cache/whisper/large-v3-turbo.pt")
    local_pc_turbo = r"C:\Users\PC\.cache\whisper\large-v3-turbo.pt"
    local_cache_large = os.path.expanduser(r"~/.cache/whisper/large-v3.pt")

    for path in [local_pc_turbo, local_cache_turbo, local_cache_large]:
        if os.path.exists(path):
            return path

    # Default to high-tier large model (Whisper downloads it dynamically on first run)
    return "large-v3-turbo"

def remove_arabic_stutters(segments):
    """Detects immediate word duplicates and common false starts."""
    clean_segments = []
    total_stutters_removed = 0
    
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            clean_segments.append(seg)
            continue
            
        new_words = []
        i = 0
        while i < len(words):
            curr_w = words[i]
            curr_text = re.sub(r'[^\w\s]', '', curr_w.get("word", "").strip())
            
            # Check duplicate next word
            if i + 1 < len(words):
                next_w = words[i+1]
                next_text = re.sub(r'[^\w\s]', '', next_w.get("word", "").strip())
                if curr_text and curr_text == next_text:
                    # Duplicate stutter detected! Keep the second occurrence
                    total_stutters_removed += 1
                    i += 1
                    continue
            new_words.append(curr_w)
            i += 1
            
        seg["words"] = new_words
        seg["text"] = " ".join([w.get("word", "").strip() for w in new_words])
        clean_segments.append(seg)
        
    if total_stutters_removed > 0:
        print(f"✨ Auto-cleaned {total_stutters_removed} duplicate words/stutters from transcription.")
    return clean_segments

def transcribe(work_dir, audio_file=None, model_choice=None):
    work_dir = os.path.abspath(work_dir)
    if not audio_file:
        audio_file = os.path.join(work_dir, "a.wav")
        if not os.path.exists(audio_file):
            audio_file = os.path.join(work_dir, "audio", "mic.wav")
            
    if not os.path.exists(audio_file):
        print(f"❌ Error: Audio file {audio_file} not found.")
        sys.exit(1)
        
    model = get_whisper_model(model_choice)
    print(f"🎙️ Transcribing with Whisper model [{model}]...", flush=True)
    
    out_json = os.path.join(work_dir, "a.json")
    whisper_log = os.path.join(work_dir, "whisper.log")
    
    cmd = [
        sys.executable, "-m", "whisper",
        audio_file,
        "--language", "ar",
        "--model", model,
        "--word_timestamps", "True",
        "--output_format", "json",
        "--output_dir", work_dir,
        "--fp16", "False",
        "--verbose", "False"
    ]
    
    with open(whisper_log, "w", encoding="utf-8") as log_f:
        res = subprocess.run(cmd, stdout=log_f, stderr=subprocess.STREQUAL if hasattr(subprocess, 'STREQUAL') else log_f)
        
    # Whisper outputs <audio_basename>.json in work_dir
    raw_json_name = os.path.splitext(os.path.basename(audio_file))[0] + ".json"
    raw_json_path = os.path.join(work_dir, raw_json_name)
    
    if os.path.exists(raw_json_path):
        data = json.load(open(raw_json_path, encoding="utf-8"))
        data["segments"] = remove_arabic_stutters(data.get("segments", []))
        json.dump(data, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"✅ Transcription saved to: {out_json}")
    else:
        print(f"❌ Whisper failed. Check log: {whisper_log}")
        sys.exit(1)
        
    # Generate default fixes.json if not existing
    fixes_path = os.path.join(work_dir, "fixes.json")
    if not os.path.exists(fixes_path):
        fixes = {
            "fix": [[w.get("word", "").strip() for w in seg.get("words", [])] for seg in data.get("segments", [])],
            "hot": [],
            "fx": {}
        }
        json.dump(fixes, open(fixes_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"✅ Generated baseline fixes.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio with Whisper")
    parser.add_argument("work_dir", nargs="?", default=".", help="Workspace directory")
    parser.add_argument("--model", choices=["large-v3", "large-v3-turbo", "medium", "small", "base"], default=None, help="Whisper model tier")
    args = parser.parse_args()
    transcribe(args.work_dir, model_choice=args.model)
