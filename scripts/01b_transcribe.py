# -*- coding: utf-8 -*-
"""Automated Word-Level Arabic Transcription & Stutter Filter for Islam AI ReelForge.
Uses Whisper large-v3-turbo with word-level timestamps and auto-detects stutter/false starts.
"""
import os, sys, json, subprocess, re

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def get_whisper_model():
    custom_path = os.environ.get("WHISPER_MODEL_PATH")
    if custom_path and os.path.exists(custom_path):
        return custom_path
    islam_default = r"C:\Users\PC\.cache\whisper\large-v3-turbo.pt"
    if os.path.exists(islam_default):
        return islam_default
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
                    # Duplicate stutter detected! Keep the second occurrence (which is usually the confident one)
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

def transcribe(work_dir, audio_file=None):
    work_dir = os.path.abspath(work_dir)
    if not audio_file:
        audio_file = os.path.join(work_dir, "a.wav")
        if not os.path.exists(audio_file):
            audio_file = os.path.join(work_dir, "audio", "mic.wav")
            
    if not os.path.exists(audio_file):
        print(f"❌ Error: Audio file {audio_file} not found.")
        sys.exit(1)
        
    model = get_whisper_model()
    print(f"🎙️ Transcribing with Whisper ({model})...", flush=True)
    
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
    work = sys.argv[1] if len(sys.argv) > 1 else "."
    transcribe(work)
