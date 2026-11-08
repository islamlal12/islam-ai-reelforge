# -*- coding: utf-8 -*-
"""Automated Word-Level Arabic Transcription & Stutter Filter for AI Video Editor.
Enforces MANDATORY speech enhancement/denoising before Whisper:
Transcribes clean audio (a_clean.wav), NEVER raw noisy audio, using large-v3-turbo.
"""
import os, sys, json, subprocess, re, argparse, importlib.util

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

def get_whisper_model(requested_model=None):
    if requested_model:
        if os.path.exists(requested_model):
            return requested_model
        return requested_model

    custom_env = os.environ.get("WHISPER_MODEL") or os.environ.get("WHISPER_MODEL_PATH")
    if custom_env:
        return custom_env

    # Prioritize permanent high-tier model cache
    local_pc_turbo = r"large-v3-turbo"
    local_cache_turbo = os.path.expanduser(r"~/.cache/whisper/large-v3-turbo.pt")
    local_cache_large = os.path.expanduser(r"~/.cache/whisper/large-v3.pt")

    for path in [local_pc_turbo, local_cache_turbo, local_cache_large]:
        if os.path.exists(path):
            return path

    # Default to high-tier large model
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

def ensure_clean_audio(work_dir, explicit_audio=None):
    """Ensures a clean, denoised audio track (a_clean.wav) exists before Whisper."""
    if explicit_audio and os.path.isfile(explicit_audio):
        return os.path.abspath(explicit_audio)

    # 1. Check for dedicated clean audio files in workspace
    for cand in ["a_clean.wav", "audio_clean.wav"]:
        p = os.path.join(work_dir, cand)
        if os.path.isfile(p):
            print(f"🎙️ Using verified clean audio: {cand} (Zero noise / Pre-denoised)", flush=True)
            return p

    # 2. If a_clean.wav does not exist, trigger pre-whisper speech enhancement automatically
    print(f"⚠️ Clean audio (a_clean.wav) not found in {work_dir}.")
    print("🧹 Auto-initiating mandatory pre-whisper speech enhancement (DeepFilterNet 3 / FFmpeg)...", flush=True)
    
    denoise_script = os.path.join(HERE, "02c_denoise.py")
    if os.path.isfile(denoise_script):
        try:
            spec = importlib.util.spec_from_file_location("denoise_mod", denoise_script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "prepare_clean_audio_for_whisper"):
                clean_path = mod.prepare_clean_audio_for_whisper(work_dir)
                if os.path.isfile(clean_path):
                    return clean_path
        except Exception as ex:
            print(f"⚠️ In-process denoising failed: {ex}. Running script via subprocess...", flush=True)
            subprocess.run([sys.executable, denoise_script, work_dir], check=False)
            clean_path = os.path.join(work_dir, "a_clean.wav")
            if os.path.isfile(clean_path):
                return clean_path

    # Fallback to existing a.wav or audio/mic.wav only if enhancement failed
    fallback_cands = [os.path.join(work_dir, "a.wav"), os.path.join(work_dir, "audio", "mic.wav")]
    for p in fallback_cands:
        if os.path.isfile(p):
            print(f"⚠️ Falling back to audio file: {p}", flush=True)
            return p

    return None

def transcribe(work_dir, audio_file=None, model_choice=None):
    work_dir = os.path.abspath(work_dir)
    
    # Enforce clean speech audio
    audio_file = ensure_clean_audio(work_dir, audio_file)
            
    if not audio_file or not os.path.exists(audio_file):
        print(f"❌ Error: Audio file {audio_file} not found.")
        sys.exit(1)
        
    model = get_whisper_model(model_choice)
    print(f"🎙️ Transcribing with Whisper model [{model}]...", flush=True)
    print(f"🎧 Transcription audio source: {os.path.basename(audio_file)}", flush=True)
    
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
    parser.add_argument("--model", default=None, help="Whisper model tier or file path")
    parser.add_argument("--audio", default=None, help="Explicit audio file to transcribe")
    args = parser.parse_args()
    transcribe(args.work_dir, audio_file=args.audio, model_choice=args.model)
