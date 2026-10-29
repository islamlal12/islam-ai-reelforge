# -*- coding: utf-8 -*-
"""🎙️ Smart AI & FFT Audio Denoising (DeepFilterNet3 & FFmpeg Adaptive FFT).

Cleans background noise (air conditioning, fan, traffic, mic hiss, room reverb)
without distorting voice quality.
Does NOT bloat the git repository:
- Checks user cache (~/.cache/reelforge/bin/) or system PATH for DeepFilterNet
- Automatically downloads binary to user cache on demand if requested
- Seamlessly falls back to FFmpeg's built-in intelligent FFT denoiser (afftdn)

Usage:
  python3 scripts/02c_denoise.py <workspace> [--strength 0.85] [--engine auto|dfn|ffmpeg]
"""
import os
import sys
import shutil
import platform
import subprocess
import tempfile
import urllib.request
from pathlib import Path

SR = 48000  # DeepFilterNet operates at 48kHz
HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = "highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=8:release=120,loudnorm=I=-16:TP=-1.5:LRA=9"

def die(msg):
    print("❌ " + msg, file=sys.stderr)
    sys.exit(2)

def flag(args, name, default, cast=str):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            try:
                return cast(args[i + 1])
            except Exception:
                pass
    return default

def get_cache_bin_dir():
    """Returns ~/.cache/reelforge/bin directory for local tool caching."""
    d = Path.home() / ".cache" / "reelforge" / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d

def find_dfn():
    """Locates DeepFilterNet binary in environment, cache, local bin, or PATH."""
    custom_env = os.environ.get("DEEPFILTER_BIN")
    if custom_env and os.path.isfile(custom_env) and os.access(custom_env, os.X_OK):
        return os.path.abspath(custom_env)

    cache_dir = get_cache_bin_dir()
    is_win = sys.platform == "win32"
    bin_name = "deep-filter.exe" if is_win else "deep-filter"
    
    # 1. User cache directory (~/.cache/reelforge/bin)
    cached = cache_dir / bin_name
    if cached.is_file() and os.access(str(cached), os.X_OK):
        return str(cached.resolve())

    # 2. Alternative cache (~/.cache/deepfilternet)
    alt_cache = Path.home() / ".cache" / "deepfilternet" / bin_name
    if alt_cache.is_file() and os.access(str(alt_cache), os.X_OK):
        return str(alt_cache.resolve())

    # 3. System PATH
    in_path = shutil.which("deep-filter") or (shutil.which("deep-filter.exe") if is_win else None)
    if in_path:
        return os.path.abspath(in_path)

    # 4. Local legacy bin folder if present
    local_bin = os.path.join(HERE, "..", "bin", bin_name)
    if os.path.isfile(local_bin) and os.access(local_bin, os.X_OK):
        return os.path.abspath(local_bin)

    return None

def download_dfn_binary():
    """Downloads pre-compiled DeepFilterNet binary directly into user cache."""
    cache_dir = get_cache_bin_dir()
    sys_plat = platform.system().lower()
    mach = platform.machine().lower()
    is_win = sys_plat == "windows"
    target_name = "deep-filter.exe" if is_win else "deep-filter"
    dest = cache_dir / target_name

    url = None
    if is_win and "64" in mach:
        url = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-pc-windows-msvc.exe"
    elif sys_plat == "linux" and ("x86_64" in mach or "amd64" in mach):
        url = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-unknown-linux-musl"
    elif sys_plat == "darwin":
        if "arm" in mach or "aarch64" in mach:
            url = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-aarch64-apple-darwin"
        else:
            url = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-apple-darwin"

    if not url:
        return None

    print(f"📥 Downloading DeepFilterNet AI Denoise Model to cache ({dest.name})...", flush=True)
    try:
        urllib.request.urlretrieve(url, str(dest))
        if not is_win:
            os.chmod(str(dest), 0o755)
        print(f"✅ Downloaded and cached DeepFilterNet to: {dest}")
        return str(dest.resolve())
    except Exception as e:
        print(f"⚠️ Could not download DeepFilterNet binary ({e}). Falling back to FFmpeg.", flush=True)
        if dest.exists():
            try: dest.unlink()
            except Exception: pass
        return None

def ff(*a):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *a], capture_output=True, text=True)
    if r.returncode:
        die("ffmpeg error: " + (r.stderr or "")[-300:])

def read_wav(p):
    import numpy as np, wave
    with wave.open(p) as w:
        n, ch, sw = w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    dt = {2: np.int16, 4: np.int32}.get(sw)
    if dt is None:
        q = p + ".s16.wav"
        ff("-i", p, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", q)
        return read_wav(q)
    x = np.frombuffer(raw, dt).astype(np.float32) / float(np.iinfo(dt).max)
    return x.reshape(-1, ch).mean(1) if ch > 1 else x

def lag_of(dry, wet, max_ms=200):
    """Calculates internal latency offset of DeepFilterNet."""
    import numpy as np
    L = min(len(dry), len(wet), SR * 30)
    if L < SR:
        return 0
    a, b = dry[:L], wet[:L]
    n = 1 << (2 * L - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    m = int(SR * max_ms / 1000)
    cand = np.concatenate([c[:m + 1], c[-m:]])
    k = int(np.argmax(cand))
    return k if k <= m else k - len(cand)

def atten_db(s):
    return 100 if s >= 0.99 else round(12 + 36 * s)

def dfn_clean(binp, wav, tmp, s):
    od = os.path.join(tmp, "out")
    os.makedirs(od, exist_ok=True)
    r = subprocess.run([binp, "-D", "-a", str(atten_db(s)), "-o", od, wav], capture_output=True, text=True)
    out = os.path.join(od, os.path.basename(wav))
    if r.returncode or not os.path.exists(out):
        print("⚠️ deep-filter returned non-zero:", (r.stderr or r.stdout)[-200:].strip())
        return None
    return out

def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    W = os.path.abspath(a[0])
    src_mp4 = os.path.join(W, "src.mp4")
    src_mov = os.path.join(W, "src.mov")
    
    if os.path.exists(src_mp4):
        src = src_mp4
        raw = os.path.join(W, "src_rawaudio.mp4")
    elif os.path.exists(src_mov):
        src = src_mov
        raw = os.path.join(W, "src_rawaudio.mov")
    else:
        die("Could not find src.mp4 or src.mov in " + W)

    if not os.path.exists(raw):
        shutil.copy2(src, raw)

    s = max(0.0, min(1.0, flag(a, "--strength", 0.85, float)))
    eng = flag(a, "--engine", "auto")

    binp = find_dfn()
    if not binp and eng in ("auto", "dfn"):
        binp = download_dfn_binary()

    if eng == "dfn" and not binp:
        die("DeepFilterNet binary could not be found or downloaded. Please check internet connection or use --engine ffmpeg.")

    tmp = tempfile.mkdtemp(prefix="dfn_")
    try:
        cleaned_successfully = False
        if binp:
            try:
                import numpy as np, wave
                dry_p = os.path.join(tmp, "a.wav")
                ff("-i", raw, "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", dry_p)
                print(f"🎙️ Denoising audio with DeepFilterNet AI (Strength: {s:.2f} · Limit: {atten_db(s)}dB)...", flush=True)
                wet_p = dfn_clean(binp, dry_p, tmp, s)
                if wet_p:
                    dry, wet = read_wav(dry_p), read_wav(wet_p)
                    lag = lag_of(dry, wet)
                    if lag > 0:
                        wet = wet[lag:]
                    elif lag < 0:
                        wet = np.concatenate([np.zeros(-lag, np.float32), wet])
                    n = len(dry)
                    wet = np.pad(wet, (0, max(0, n - len(wet))))[:n]
                    mix = np.clip(wet, -1, 1)
                    mix_p = os.path.join(tmp, "mix.wav")
                    with wave.open(mix_p, "wb") as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                        w.writeframes((mix * 32767).astype(np.int16).tobytes())
                    ff("-i", raw, "-i", mix_p, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                       "-af", CHAIN, "-ac", "2", "-ar", str(SR), "-c:a", "aac", "-b:a", "192k", "-shortest",
                       "-movflags", "+faststart", src)
                    print(f"✨ Audio enhanced with DeepFilterNet3 (latency compensated {lag / SR * 1000:.0f}ms).")
                    cleaned_successfully = True
            except Exception as ex:
                print(f"⚠️ DeepFilterNet execution failed ({ex}). Falling back to FFmpeg FFT.")

        if not cleaned_successfully:
            print("ℹ️ Denoising with FFmpeg Adaptive FFT Spectral Subtraction (afftdn)...", flush=True)
            ff("-i", raw, "-c:v", "copy",
               "-af", "highpass=f=80,afftdn=nf=-28:nt=w," + CHAIN.split(",", 1)[1],
               "-ar", str(SR), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", src)
            print("✨ Audio enhanced with FFmpeg adaptive FFT filter.")

        # Also refresh workspace a.wav so whisper and silence cut pick up clean audio
        a_wav = os.path.join(W, "a.wav")
        ff("-i", src, "-vn", "-ar", "16000", "-ac", "1", a_wav)
        print("✅ Cleaned audio synchronized -> a.wav (Original audio preserved at " + os.path.basename(raw) + ")")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main(sys.argv[1:])
