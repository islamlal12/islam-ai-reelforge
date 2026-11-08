# -*- coding: utf-8 -*-
"""
===================================================================================
DaVinci Resolve Universal Timeline & Project Exporter for Islam AI ReelForge
===================================================================================
Exports a production-ready, vertical 9:16 timeline (1080x1920) for DaVinci Resolve:
1. Video Track (V1): Exact sequence of cut segments from src.mov (from cut.json).
2. Audio Track 1 (A1): Synchronized clean dialogue track (a_clean.wav / audio.wav).
3. Audio Track 2 (A2): Individual SFX events (whooshes, pops, hero hits, risers) from sfx.json.
4. Subtitle Track / Markers: Colored duration markers and .srt subtitles from caps.json.
5. FCPXML v1.8 / v1.9 + FCP7 XML (xmeml) for 100% universal compatibility across DaVinci 17, 18, 19, and 20.
6. Standalone Python Script (import_to_davinci.py) for 1-click DaVinci Resolve Studio automation!

Usage:
    python scripts/42_davinci_export.py <work_dir> [--fps 30] [--import]
===================================================================================
"""

import sys as _sys
import builtins as _bi

# ── Universal Windows UTF-8 Console & File Handling ──────────────────────────
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_real_open = _bi.open
def _utf8_open(f, mode="r", *a, **k):
    if "b" not in mode:
        k.setdefault("encoding", "utf-8")
    return _real_open(f, mode, *a, **k)
_bi.open = _utf8_open
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
import json
import wave
import shutil
import argparse
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np

# ═════════════════════════════════════════════════════════════════════════════
# 1) SFX Audio Synthesizer (Broadcast 48kHz Stereo PCM)
# ═════════════════════════════════════════════════════════════════════════════

def _lp(x, a0, a1):
    """Linear time-varying single-pole lowpass filter."""
    y = np.empty_like(x)
    z = 0.0
    n = len(x)
    for i in range(n):
        a = a0 + (a1 - a0) * (i / n)
        z += a * (x[i] - z)
        y[i] = z
    return y

def synthesize_sfx_library(out_dir, sr=48000):
    """
    Generates high-fidelity sound effect WAV files into out_dir.
    Matches Islam AI ReelForge sound design guidelines:
    - 3-Layer Hero hits (Transient Click + Resonant Body + 45Hz Deep Sub)
    - Clamped Risers with sharp end cutoff
    - Whooshes, Pops, Clicks, Thuds, Taps, Shimmers, Sub-sweeps, and Glitches.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(42)

    def write_wav(filename, sig, gain=0.85):
        filepath = out_dir / filename
        if filepath.exists() and filepath.stat().st_size > 1000:
            return str(filepath)
        sig = np.asarray(sig, dtype=np.float32)
        peak = np.max(np.abs(sig))
        if peak > 1e-6:
            sig = (sig / peak) * gain
        sig = np.clip(sig, -0.98, 0.98)
        pcm16 = (sig * 32767).astype('<i2')
        stereo = np.repeat(pcm16[:, None], 2, axis=1).ravel()
        with wave.open(str(filepath), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(stereo.tobytes())
        return str(filepath)

    # 1. Whoosh Up & Whoosh Down
    dur_w = 0.34
    L_w = int(dur_w * sr)
    t_w = np.arange(L_w) / sr
    env_w = np.sin(np.pi * t_w / dur_w) ** 2
    w_up = _lp(rng.randn(L_w), 2 * np.pi * 180 / sr, 2 * np.pi * 2400 / sr) * env_w
    write_wav("whoosh_up.wav", w_up, gain=0.8)

    dur_wd = 0.30
    L_wd = int(dur_wd * sr)
    t_wd = np.arange(L_wd) / sr
    env_wd = np.sin(np.pi * t_wd / dur_wd) ** 2
    w_down = _lp(rng.randn(L_wd), 2 * np.pi * 2400 / sr, 2 * np.pi * 180 / sr) * env_wd
    write_wav("whoosh_down.wav", w_down, gain=0.75)

    # 2. Pop
    dur_p = 0.09
    L_p = int(dur_p * sr)
    t_p = np.arange(L_p) / sr
    f_p = 380 * np.exp(-t_p / 0.015) + 90
    pop_sig = np.sin(2 * np.pi * np.cumsum(f_p) / sr) * np.exp(-t_p / 0.025)
    write_wav("pop.wav", pop_sig, gain=0.85)

    # 3. Click
    dur_c = 0.04
    L_c = int(dur_c * sr)
    t_c = np.arange(L_c) / sr
    f_c = 2200 * np.exp(-t_c / 0.005) + 300
    click_sig = np.sin(2 * np.pi * np.cumsum(f_c) / sr) * np.exp(-t_c / 0.006)
    write_wav("click.wav", click_sig, gain=0.75)

    # 4. Thud
    dur_th = 0.22
    L_th = int(dur_th * sr)
    t_th = np.arange(L_th) / sr
    f_th = 110 * np.exp(-t_th / 0.04) + 40
    thud_sig = np.sin(2 * np.pi * np.cumsum(f_th) / sr) * np.exp(-t_th / 0.07)
    write_wav("thud.wav", thud_sig, gain=0.90)

    # 5. Tap
    dur_tp = 0.05
    L_tp = int(dur_tp * sr)
    t_tp = np.arange(L_tp) / sr
    f_tp = 900 * np.exp(-t_tp / 0.008) + 120
    tap_sig = np.sin(2 * np.pi * np.cumsum(f_tp) / sr) * np.exp(-t_tp / 0.012)
    write_wav("tap.wav", tap_sig, gain=0.75)

    # 6. Typing
    dur_ty = 0.80
    L_ty = int(dur_ty * sr)
    ty_sig = np.zeros(L_ty)
    cps = 14
    for i in range(int(dur_ty * cps)):
        j = int((i / cps + rng.uniform(-0.01, 0.01)) * sr)
        j = max(0, min(L_ty - len(click_sig), j))
        ty_sig[j:j + len(click_sig)] += click_sig * rng.uniform(0.5, 1.0)
    write_wav("typing.wav", ty_sig, gain=0.70)

    # 7. Shimmer
    dur_sh = 0.90
    L_sh = int(dur_sh * sr)
    t_sh = np.arange(L_sh) / sr
    shimmer_sig = sum(np.sin(2 * np.pi * f * t_sh) * np.exp(-t_sh / (0.25 + 0.1 * idx))
                      for idx, f in enumerate([1760, 2217, 2637, 3520]))
    write_wav("shimmer.wav", shimmer_sig, gain=0.70)

    # 8. Sub Bass Drop
    dur_sub = 0.70
    L_sub = int(dur_sub * sr)
    t_sub = np.arange(L_sub) / sr
    f_sub = 60 * np.exp(np.log(34 / 60) * t_sub / dur_sub)
    sub_sig = np.sin(2 * np.pi * np.cumsum(f_sub) / sr) * np.exp(-t_sub / 0.22)
    write_wav("sub.wav", sub_sig, gain=0.92)

    # 9. Glitch
    dur_g = 0.28
    L_g = int(dur_g * sr)
    g_sig = np.zeros(L_g)
    for _ in range(7):
        a = rng.randint(0, max(1, L_g - 800))
        b = min(L_g, a + rng.randint(300, 1600))
        g_sig[a:b] += np.round(rng.randn(b - a) * 3) / 3 * rng.uniform(0.4, 1.0)
    write_wav("glitch.wav", g_sig, gain=0.75)

    # 10. Clamped Riser (0.55s)
    dur_r = 0.55
    L_r = int(dur_r * sr)
    t_r = np.arange(L_r) / sr
    f_r = 80 + 1200 * (t_r / dur_r) ** 2
    r_sig = np.sin(2 * np.pi * np.cumsum(f_r) / sr) * (t_r / dur_r) ** 1.5
    # Guillotine cut: zero-pad last 3ms to avoid click
    cut_tail = int(0.003 * sr)
    r_sig[-cut_tail:] *= np.linspace(1.0, 0.0, cut_tail)
    write_wav("riser.wav", r_sig, gain=0.80)

    # 11. Hero 3-Layer Stack (Tech Material)
    L_att = int(0.040 * sr)
    t_att = np.arange(L_att) / sr
    f_att = 5800.0 * np.exp(-t_att / 0.006) + 400.0
    click_tr = np.sin(2 * np.pi * np.cumsum(f_att) / sr) * np.exp(-t_att / 0.005)
    noise_tr = _lp(rng.randn(L_att), 0.45, 0.10) * np.exp(-t_att / 0.004)
    attack = (click_tr * 0.65 + noise_tr * 0.35)

    dur_mid = 0.24
    L_mid = int(dur_mid * sr)
    t_mid = np.arange(L_mid) / sr
    f_mid = 440.0 * np.exp(-t_mid / 0.04) + 160.0
    fm_mod = np.sin(2 * np.pi * 320.0 * t_mid) * np.exp(-t_mid / 0.03) * 1.2
    body_tech = np.sin(2 * np.pi * np.cumsum(f_mid) / sr + fm_mod) * np.exp(-t_mid / 0.055)
    sheen = (np.sin(2 * np.pi * 1750.0 * t_mid) + np.sin(2 * np.pi * 2620.0 * t_mid)) * np.exp(-t_mid / 0.025) * 0.25
    mid_tech = body_tech + sheen

    dur_sub_h = 0.75
    L_sub_h = int(dur_sub_h * sr)
    t_sub_h = np.arange(L_sub_h) / sr
    env_sub_h = np.exp(-t_sub_h / 0.35)
    sub_w = (np.sin(2 * np.pi * 45.0 * t_sub_h) + 0.22 * np.sin(2 * np.pi * 90.0 * t_sub_h) * np.exp(-t_sub_h / 0.22)) * env_sub_h

    tot_len = max(L_att, L_mid, L_sub_h)
    hero_tech = np.zeros(tot_len)
    hero_tech[:L_att] += attack * 0.45
    hero_tech[:L_mid] += mid_tech * 0.50
    hero_tech[:L_sub_h] += sub_w * 0.70
    write_wav("hero.wav", hero_tech, gain=0.90)
    write_wav("hero_tech.wav", hero_tech, gain=0.90)

    # 12. Hero Stone/Impact
    f_stone = 240.0 * np.exp(-t_mid / 0.035) + 95.0
    body_stone = np.sin(2 * np.pi * np.cumsum(f_stone) / sr) * np.exp(-t_mid / 0.08)
    mid_stone = body_stone + _lp(rng.randn(L_mid), 0.30, 0.08) * np.exp(-t_mid / 0.012) * 0.45
    hero_impact = np.zeros(tot_len)
    hero_impact[:L_att] += attack * 0.40
    hero_impact[:L_mid] += mid_stone * 0.55
    hero_impact[:L_sub_h] += sub_w * 0.75
    write_wav("hero_impact.wav", hero_impact, gain=0.92)

    return out_dir


# ═════════════════════════════════════════════════════════════════════════════
# 2) Media Discovery & Metadata Probing
# ═════════════════════════════════════════════════════════════════════════════

def probe_video_stream(video_path):
    """Probes video width, height, rotation, and fps using ffprobe."""
    meta = {
        "width": 1080,
        "height": 1920,
        "fps": 30.0,
        "duration": 0.0
    }
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration:stream_tags=rotate:stream_side_data=rotation",
            "-of", "json",
            str(video_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if streams:
            s = streams[0]
            w = int(s.get("width", 1080))
            h = int(s.get("height", 1920))
            
            # Check rotation
            rot = 0
            if "tags" in s and "rotate" in s["tags"]:
                try: rot = int(s["tags"]["rotate"])
                except Exception: pass
            if "side_data_list" in s:
                for sd in s["side_data_list"]:
                    if "rotation" in sd:
                        try: rot = int(sd["rotation"])
                        except Exception: pass
            if abs(rot) in (90, 270):
                w, h = h, w
                
            meta["width"] = w
            meta["height"] = h

            # Parse frame rate
            r_fps = s.get("r_frame_rate", "30/1")
            if "/" in r_fps:
                num, den = r_fps.split("/")
                fps_val = float(num) / float(den) if float(den) > 0 else 30.0
            else:
                fps_val = float(r_fps)
            if 23.9 <= fps_val <= 61.0:
                meta["fps"] = round(fps_val, 2)

            if "duration" in s and s["duration"]:
                meta["duration"] = float(s["duration"])
    except Exception:
        pass
        
    return meta

def find_project_media(work_dir):
    """
    Scans the workspace folder to find:
    - cut.json
    - caps.json
    - sfx.json
    - Source Video (src.mov, src.mp4, etc.)
    - Dialogue Audio (a_clean.wav, audio.wav, a.wav, etc.)
    """
    work = Path(work_dir).resolve()
    
    # 1. Source Video
    video_candidates = [
        work / "src.mov",
        work / "src.mp4",
        work / "src_sdr.mov",
        work / "src_raw_rotated.mov",
        work / "src_raw.mov"
    ]
    src_video = None
    for cand in video_candidates:
        if cand.exists() and cand.stat().st_size > 0:
            src_video = cand
            break
    if not src_video:
        # Search for any mov or mp4
        for f in work.glob("*.mov"):
            if not f.name.startswith("cutz") and not f.name.startswith("ad-"):
                src_video = f
                break
        if not src_video:
            for f in work.glob("*.mp4"):
                if not f.name.startswith("cutz") and not f.name.startswith("ad-"):
                    src_video = f
                    break

    # 2. Dialogue Audio Track
    audio_candidates = [
        work / "a_clean.wav",
        work / "audio.wav",
        work / "voice48k.wav",
        work / "a.wav",
        work / "a_mono.wav"
    ]
    src_audio = None
    for cand in audio_candidates:
        if cand.exists() and cand.stat().st_size > 0:
            src_audio = cand
            break
            
    # 3. JSON files
    cut_file = work / "cut.json"
    caps_file = work / "caps.json"
    sfx_file = work / "sfx.json"

    return {
        "work_dir": work,
        "src_video": src_video,
        "src_audio": src_audio,
        "cut_file": cut_file if cut_file.exists() else None,
        "caps_file": caps_file if caps_file.exists() else None,
        "sfx_file": sfx_file if sfx_file.exists() else None,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3) Utilities: URLs, Timecodes & Colors
# ═════════════════════════════════════════════════════════════════════════════

def to_file_url(path):
    """Generates standard RFC 8089 file URL: file:///C:/path/to/file."""
    abs_path = os.path.abspath(path).replace("\\", "/")
    if abs_path.startswith("/"):
        return f"file://{urllib.parse.quote(abs_path)}"
    else:
        # Windows drive letter C:/ -> file:///C:/
        return f"file:///{urllib.parse.quote(abs_path, safe='/:')}"

def seconds_to_timecode(seconds, fps=30.0, start_offset_hours=0):
    """Converts seconds to HH:MM:SS:FF timecode format."""
    total_frames = int(round(seconds * fps))
    ff = total_frames % int(round(fps))
    tot_sec = total_frames // int(round(fps))
    ss = tot_sec % 60
    tot_min = tot_sec // 60
    mm = tot_min % 60
    hh = (tot_min // 60) + start_offset_hours
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

def seconds_to_srt_timestamp(seconds):
    """Converts seconds to SRT format: HH:MM:SS,mmm."""
    ms = int(round((seconds % 1.0) * 1000))
    tot_sec = int(seconds)
    ss = tot_sec % 60
    tot_min = tot_sec // 60
    mm = tot_min % 60
    hh = tot_min // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"

def time_rational_str(seconds, fps=30.0):
    """Formats exact FCPXML rational time string: e.g. '150/30s'."""
    fps_int = int(round(fps))
    frames = int(round(seconds * fps))
    return f"{frames}/{fps_int}s"


# ═════════════════════════════════════════════════════════════════════════════
# 4) SFX Event Planner & Audio Placement
# ═════════════════════════════════════════════════════════════════════════════

def parse_sfx_events(sfx_data, sfx_dir):
    """
    Parses sfx.json into a structured list of sound effect instances:
    Each event: {
        'name': 'whoosh_up',
        'file': Path to wav,
        'at': float (timeline start seconds),
        'dur': float (seconds)
    }
    """
    sfx_dir = Path(sfx_dir)
    events = []

    sfx_mapping = {
        "whoosh_up": ("whoosh_up.wav", 0.34),
        "whoosh_down": ("whoosh_down.wav", 0.30),
        "pop": ("pop.wav", 0.12),
        "click": ("click.wav", 0.06),
        "thud": ("thud.wav", 0.25),
        "tap": ("tap.wav", 0.08),
        "type": ("typing.wav", 0.80),
        "shimmer": ("shimmer.wav", 0.90),
        "sub": ("sub.wav", 0.70),
        "glitch": ("glitch.wav", 0.28),
        "riser": ("riser.wav", 0.55),
        "hero": ("hero_tech.wav", 0.75),
        "hero_hits": ("hero_tech.wav", 0.75),
        "soft": ("whoosh_up.wav", 0.30),
        "counter": ("click.wav", 0.50),
    }

    if not sfx_data:
        return events

    for key, (wav_name, default_dur) in sfx_mapping.items():
        items = sfx_data.get(key, [])
        if not items:
            continue
        wav_file = sfx_dir / wav_name
        
        for item in items:
            t0 = 0.0
            dur = default_dur
            
            if key == "riser":
                if isinstance(item, (list, tuple)):
                    te = float(item[0])
                    d0 = float(item[1]) if len(item) > 1 else 0.55
                else:
                    te = float(item)
                    d0 = 0.55
                cd = float(np.clip(d0, 0.4, 0.7))
                t0 = max(0.0, te - cd)
                dur = cd
            elif key in ("hero", "hero_hits"):
                if isinstance(item, (int, float)):
                    t0 = float(item)
                elif isinstance(item, (list, tuple)):
                    t0 = float(item[0])
                    mat = str(item[1]).lower() if len(item) > 1 else "tech"
                    if mat in ("heavy", "stone", "impact"):
                        wav_file = sfx_dir / "hero_impact.wav"
                    else:
                        wav_file = sfx_dir / "hero_tech.wav"
                elif isinstance(item, dict):
                    t0 = float(item.get("t", item.get("t0", 0.0)))
                    mat = str(item.get("material", "tech")).lower()
                    if mat in ("heavy", "stone", "impact"):
                        wav_file = sfx_dir / "hero_impact.wav"
                    else:
                        wav_file = sfx_dir / "hero_tech.wav"
                dur = 0.75
            elif key in ("type", "counter"):
                if isinstance(item, (list, tuple)):
                    t0 = float(item[0])
                    dur = float(item[1]) if len(item) > 1 else default_dur
                else:
                    t0 = float(item)
                    dur = default_dur
            else:
                if isinstance(item, (list, tuple)):
                    t0 = float(item[0])
                else:
                    t0 = float(item)

            events.append({
                "name": key,
                "file": str(wav_file),
                "filename": wav_file.name,
                "at": round(t0, 3),
                "dur": round(dur, 3)
            })

    events.sort(key=lambda x: x["at"])
    return events


# ═════════════════════════════════════════════════════════════════════════════
# 5) FCPXML v1.8 / v1.9 Universal Timeline Generator
# ═════════════════════════════════════════════════════════════════════════════

def export_fcpxml(work_dir, cuts, caps, sfx_events, video_path, audio_path, meta, fps=30.0):
    """
    Generates standard FCPXML v1.8 / v1.9 (timeline.fcpxml) compatible with
    DaVinci Resolve 17, 18, 19, and 20:
    - 9:16 Vertical Resolution (1080x1920)
    - Primary Spine: V1 Cut blocks from src.mov
    - Lane -1: A1 Dialogue audio blocks from a_clean.wav / audio.wav
    - Lane -2: A2 SFX audio blocks placed at exact timestamps
    - Markers: Embedded caption cards with duration, text and color notes
    """
    fps_int = int(round(fps))
    format_frame_dur = f"1/{fps_int}s"
    
    # Calculate timeline total duration
    total_frames = sum(max(1, int(round((e - s) * fps))) for s, e in cuts)
    total_sec = total_frames / fps
    total_dur_str = time_rational_str(total_sec, fps)

    # Prepare root
    root = ET.Element("fcpxml", version="1.8")
    
    # Resources
    resources = ET.SubElement(root, "resources")
    ET.SubElement(resources, "format", {
        "id": "r1",
        "name": f"FFVideoFormat1080x1920p{fps_int}",
        "frameDuration": format_frame_dur,
        "width": "1080",
        "height": "1920"
    })

    # Asset: Source Video
    src_dur_sec = meta.get("duration", 0.0) or (cuts[-1][1] + 10.0 if cuts else 60.0)
    src_dur_str = time_rational_str(src_dur_sec, fps)
    video_url = to_file_url(video_path)
    ET.SubElement(resources, "asset", {
        "id": "r2",
        "name": os.path.basename(video_path),
        "uid": f"asset_video_{Path(video_path).stem}",
        "src": video_url,
        "start": "0s",
        "duration": src_dur_str,
        "hasVideo": "1",
        "format": "r1",
        "hasAudio": "1",
        "audioSources": "1",
        "audioChannels": "2",
        "audioRate": "48000"
    })

    # Asset: Clean Dialogue Audio
    audio_dur_str = src_dur_str
    audio_url = to_file_url(audio_path)
    ET.SubElement(resources, "asset", {
        "id": "r3",
        "name": os.path.basename(audio_path),
        "uid": f"asset_dialogue_{Path(audio_path).stem}",
        "src": audio_url,
        "start": "0s",
        "duration": audio_dur_str,
        "hasAudio": "1",
        "audioSources": "1",
        "audioChannels": "2",
        "audioRate": "48000"
    })

    # SFX Assets
    sfx_assets = {}
    next_asset_id = 4
    for ev in sfx_events:
        fname = ev["filename"]
        if fname not in sfx_assets:
            r_id = f"r{next_asset_id}"
            next_asset_id += 1
            sfx_assets[fname] = r_id
            ET.SubElement(resources, "asset", {
                "id": r_id,
                "name": fname,
                "uid": f"asset_sfx_{Path(fname).stem}",
                "src": to_file_url(ev["file"]),
                "start": "0s",
                "duration": time_rational_str(max(0.5, ev["dur"] + 0.2), fps),
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": "2",
                "audioRate": "48000"
            })

    # Library -> Event -> Project -> Sequence -> Spine
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="Islam AI ReelForge")
    project = ET.SubElement(event, "project", name="ReelForge Timeline")
    sequence = ET.SubElement(project, "sequence", {
        "format": "r1",
        "duration": total_dur_str,
        "tcStart": "0s",
        "tcFormat": "NDF"
    })
    spine = ET.SubElement(sequence, "spine")

    # Group SFX and Captions by Cut Intervals
    # Build list of cuts with their timeline bounds
    cut_intervals = []
    accum_frames = 0
    for idx, (s, e) in enumerate(cuts):
        dur_f = max(1, int(round((e - s) * fps)))
        tl_start_f = accum_frames
        tl_end_f = accum_frames + dur_f
        cut_intervals.append({
            "idx": idx,
            "src_s": s,
            "src_e": e,
            "dur_f": dur_f,
            "dur_s": dur_f / fps,
            "tl_start_f": tl_start_f,
            "tl_end_f": tl_end_f,
            "tl_start_s": tl_start_f / fps,
            "tl_end_s": tl_end_f / fps,
            "sfx": [],
            "caps": []
        })
        accum_frames += dur_f

    # Distribute SFX events to cuts
    for ev in sfx_events:
        t = ev["at"]
        assigned = False
        for c in cut_intervals:
            if c["tl_start_s"] <= t < c["tl_end_s"]:
                c["sfx"].append(ev)
                assigned = True
                break
        if not assigned and cut_intervals:
            # Place in last cut
            cut_intervals[-1]["sfx"].append(ev)

    # Distribute Caption cards to cuts for marker placement
    cards = caps.get("cards", []) if caps else []
    for c_card in cards:
        cs = c_card.get("s", 0.0)
        ce = c_card.get("e", cs + 1.0)
        assigned = False
        for c in cut_intervals:
            if c["tl_start_s"] <= cs < c["tl_end_s"]:
                c["caps"].append(c_card)
                assigned = True
                break
        if not assigned and cut_intervals:
            cut_intervals[-1]["caps"].append(c_card)

    # Assemble Spine Clips
    for c in cut_intervals:
        idx = c["idx"]
        cut_num = f"{idx + 1:02d}"
        cut_offset_str = time_rational_str(c["tl_start_s"], fps)
        cut_dur_str = time_rational_str(c["dur_s"], fps)
        src_start_str = time_rational_str(c["src_s"], fps)

        # 1. Primary Video Clip (V1)
        v_clip = ET.SubElement(spine, "asset-clip", {
            "ref": "r2",
            "offset": cut_offset_str,
            "name": f"Cut {cut_num}",
            "start": src_start_str,
            "duration": cut_dur_str,
            "format": "r1",
            "tcFormat": "NDF"
        })

        # 2. Synchronized Clean Dialogue Audio (A1)
        ET.SubElement(v_clip, "asset-clip", {
            "ref": "r3",
            "lane": "-1",
            "offset": cut_offset_str,
            "name": f"Dialogue {cut_num}",
            "start": src_start_str,
            "duration": cut_dur_str,
            "role": "dialogue"
        })

        # 3. Sound Effects (A2)
        for ev in c["sfx"]:
            r_sfx = sfx_assets.get(ev["filename"])
            if r_sfx:
                sfx_offset_str = time_rational_str(ev["at"], fps)
                sfx_dur_str = time_rational_str(ev["dur"], fps)
                ET.SubElement(v_clip, "asset-clip", {
                    "ref": r_sfx,
                    "lane": "-2",
                    "offset": sfx_offset_str,
                    "name": ev["name"],
                    "start": "0s",
                    "duration": sfx_dur_str,
                    "role": "effects"
                })

        # 4. Markers for Captions (on the clip)
        for card in c["caps"]:
            cs = card.get("s", 0.0)
            ce = card.get("e", cs + 1.0)
            # Time inside the source asset
            offset_in_cut = cs - c["tl_start_s"]
            marker_start_in_asset = c["src_s"] + offset_in_cut
            marker_dur = max(0.2, ce - cs)
            
            words = card.get("w", [])
            caption_text = " ".join(w.get("t", "") for w in words)
            hot_words = [w.get("t", "") for w in words if w.get("hot") or w.get("fx")]
            
            note = f"🔥 Emphasized: {', '.join(hot_words)}" if hot_words else "Dialogue Caption"
            
            ET.SubElement(v_clip, "marker", {
                "start": time_rational_str(marker_start_in_asset, fps),
                "duration": time_rational_str(marker_dur, fps),
                "value": caption_text or "Caption",
                "note": note
            })

    # Write formatted XML
    xml_str = ET.tostring(root, encoding="utf-8")
    # Pretty format
    try:
        from xml.dom import minidom
        reparsed = minidom.parseString(xml_str)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
        # Ensure standard doctype
        if "<!DOCTYPE fcpxml>" not in pretty_xml:
            lines = pretty_xml.splitlines()
            if lines[0].startswith("<?xml"):
                lines.insert(1, "<!DOCTYPE fcpxml>")
            else:
                lines.insert(0, "<!DOCTYPE fcpxml>")
            pretty_xml = "\n".join(lines)
    except Exception:
        pretty_xml = xml_str.decode("utf-8")

    out_file = Path(work_dir) / "timeline.fcpxml"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    return out_file


# ═════════════════════════════════════════════════════════════════════════════
# 6) FCP7 XML (xmeml v5) Companion Exporter
# ═════════════════════════════════════════════════════════════════════════════

def export_fcp7_xml(work_dir, cuts, sfx_events, video_path, audio_path, meta, fps=30.0):
    """
    Generates standard Final Cut Pro 7 XML (timeline.xml - xmeml v5)
    with explicit video track (V1), dialogue track (A1), and SFX track (A2).
    """
    fps_int = int(round(fps))
    total_frames = sum(max(1, int(round((e - s) * fps))) for s, e in cuts)
    src_dur_frames = int(round((meta.get("duration", 0.0) or (cuts[-1][1] + 10.0)) * fps))

    root = ET.Element("xmeml", version="5")
    sequence = ET.SubElement(root, "sequence", id="sequence-1")
    ET.SubElement(sequence, "name").text = "ReelForge Timeline"
    ET.SubElement(sequence, "duration").text = str(total_frames)
    
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = str(fps_int)
    ET.SubElement(rate, "ntsc").text = "FALSE"

    timecode = ET.SubElement(sequence, "timecode")
    tc_rate = ET.SubElement(timecode, "rate")
    ET.SubElement(tc_rate, "timebase").text = str(fps_int)
    ET.SubElement(tc_rate, "ntsc").text = "FALSE"
    ET.SubElement(timecode, "string").text = "00:00:00:00"
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF"

    media = ET.SubElement(sequence, "media")

    # 1. Video Section
    video = ET.SubElement(media, "video")
    v_format = ET.SubElement(video, "format")
    v_sample = ET.SubElement(v_format, "samplecharacteristics")
    ET.SubElement(v_sample, "width").text = "1080"
    ET.SubElement(v_sample, "height").text = "1920"
    ET.SubElement(v_sample, "pixelaspectratio").text = "square"
    v_s_rate = ET.SubElement(v_sample, "rate")
    ET.SubElement(v_s_rate, "timebase").text = str(fps_int)
    ET.SubElement(v_s_rate, "ntsc").text = "FALSE"

    v_track = ET.SubElement(video, "track")

    # 2. Audio Section
    audio = ET.SubElement(media, "audio")
    a_track_dialogue = ET.SubElement(audio, "track")
    a_track_sfx = ET.SubElement(audio, "track")

    video_url = to_file_url(video_path)
    audio_url = to_file_url(audio_path)

    accum_frame = 0
    for idx, (s, e) in enumerate(cuts):
        dur_f = max(1, int(round((e - s) * fps)))
        start_f = accum_frame
        end_f = accum_frame + dur_f
        in_f = int(round(s * fps))
        out_f = in_f + dur_f

        # V1 ClipItem
        ci_v = ET.SubElement(v_track, "clipitem", id=f"clipitem-v{idx + 1}")
        ET.SubElement(ci_v, "name").text = f"Cut {idx + 1:02d}"
        ET.SubElement(ci_v, "duration").text = str(src_dur_frames)
        ci_r = ET.SubElement(ci_v, "rate")
        ET.SubElement(ci_r, "timebase").text = str(fps_int)
        ET.SubElement(ci_r, "ntsc").text = "FALSE"
        ET.SubElement(ci_v, "start").text = str(start_f)
        ET.SubElement(ci_v, "end").text = str(end_f)
        ET.SubElement(ci_v, "in").text = str(in_f)
        ET.SubElement(ci_v, "out").text = str(out_f)

        file_v = ET.SubElement(ci_v, "file", id="file-video-src")
        ET.SubElement(file_v, "name").text = os.path.basename(video_path)
        ET.SubElement(file_v, "pathurl").text = video_url
        f_r = ET.SubElement(file_v, "rate")
        ET.SubElement(f_r, "timebase").text = str(fps_int)
        ET.SubElement(f_r, "ntsc").text = "FALSE"
        ET.SubElement(file_v, "duration").text = str(src_dur_frames)
        f_m = ET.SubElement(file_v, "media")
        f_mv = ET.SubElement(f_m, "video")
        f_mvs = ET.SubElement(f_mv, "samplecharacteristics")
        ET.SubElement(f_mvs, "width").text = "1080"
        ET.SubElement(f_mvs, "height").text = "1920"

        # A1 Dialogue ClipItem
        ci_a = ET.SubElement(a_track_dialogue, "clipitem", id=f"clipitem-a1-{idx + 1}")
        ET.SubElement(ci_a, "name").text = f"Dialogue {idx + 1:02d}"
        ET.SubElement(ci_a, "duration").text = str(src_dur_frames)
        ci_ar = ET.SubElement(ci_a, "rate")
        ET.SubElement(ci_ar, "timebase").text = str(fps_int)
        ET.SubElement(ci_ar, "ntsc").text = "FALSE"
        ET.SubElement(ci_a, "start").text = str(start_f)
        ET.SubElement(ci_a, "end").text = str(end_f)
        ET.SubElement(ci_a, "in").text = str(in_f)
        ET.SubElement(ci_a, "out").text = str(out_f)

        file_a = ET.SubElement(ci_a, "file", id="file-audio-dialogue")
        ET.SubElement(file_a, "name").text = os.path.basename(audio_path)
        ET.SubElement(file_a, "pathurl").text = audio_url
        fa_r = ET.SubElement(file_a, "rate")
        ET.SubElement(fa_r, "timebase").text = str(fps_int)
        ET.SubElement(fa_r, "ntsc").text = "FALSE"
        ET.SubElement(file_a, "duration").text = str(src_dur_frames)
        fa_m = ET.SubElement(file_a, "media")
        fa_ma = ET.SubElement(fa_m, "audio")
        fa_mas = ET.SubElement(fa_ma, "samplecharacteristics")
        ET.SubElement(fa_mas, "depth").text = "16"
        ET.SubElement(fa_mas, "samplerate").text = "48000"

        accum_frame += dur_f

    # A2 SFX ClipItems
    for s_idx, ev in enumerate(sfx_events):
        sfx_start_f = int(round(ev["at"] * fps))
        sfx_dur_f = max(1, int(round(ev["dur"] * fps)))
        sfx_end_f = sfx_start_f + sfx_dur_f
        sfx_url = to_file_url(ev["file"])

        ci_sfx = ET.SubElement(a_track_sfx, "clipitem", id=f"clipitem-sfx-{s_idx + 1}")
        ET.SubElement(ci_sfx, "name").text = ev["name"]
        ET.SubElement(ci_sfx, "duration").text = str(sfx_dur_f)
        cs_r = ET.SubElement(ci_sfx, "rate")
        ET.SubElement(cs_r, "timebase").text = str(fps_int)
        ET.SubElement(cs_r, "ntsc").text = "FALSE"
        ET.SubElement(ci_sfx, "start").text = str(sfx_start_f)
        ET.SubElement(ci_sfx, "end").text = str(sfx_end_f)
        ET.SubElement(ci_sfx, "in").text = "0"
        ET.SubElement(ci_sfx, "out").text = str(sfx_dur_f)

        file_sfx = ET.SubElement(ci_sfx, "file", id=f"file-sfx-{Path(ev['filename']).stem}")
        ET.SubElement(file_sfx, "name").text = ev["filename"]
        ET.SubElement(file_sfx, "pathurl").text = sfx_url
        fs_r = ET.SubElement(file_sfx, "rate")
        ET.SubElement(fs_r, "timebase").text = str(fps_int)
        ET.SubElement(fs_r, "ntsc").text = "FALSE"
        ET.SubElement(file_sfx, "duration").text = str(sfx_dur_f)
        fs_m = ET.SubElement(file_sfx, "media")
        fs_ma = ET.SubElement(fs_m, "audio")
        fs_mas = ET.SubElement(fs_ma, "samplecharacteristics")
        ET.SubElement(fs_mas, "depth").text = "16"
        ET.SubElement(fs_mas, "samplerate").text = "48000"

    xml_str = ET.tostring(root, encoding="utf-8")
    try:
        from xml.dom import minidom
        reparsed = minidom.parseString(xml_str)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
        if "<!DOCTYPE xmeml>" not in pretty_xml:
            lines = pretty_xml.splitlines()
            if lines[0].startswith("<?xml"):
                lines.insert(1, "<!DOCTYPE xmeml>")
            else:
                lines.insert(0, "<!DOCTYPE xmeml>")
            pretty_xml = "\n".join(lines)
    except Exception:
        pretty_xml = xml_str.decode("utf-8")

    out_file = Path(work_dir) / "timeline.xml"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    return out_file


# ═════════════════════════════════════════════════════════════════════════════
# 7) Subtitles & Markers Exporters (.srt, .edl, .csv)
# ═════════════════════════════════════════════════════════════════════════════

def export_srt(work_dir, caps):
    """Exports clean SubRip (.srt) subtitle track for DaVinci Resolve."""
    cards = caps.get("cards", []) if caps else []
    srt_lines = []
    
    for idx, card in enumerate(cards, start=1):
        s = card.get("s", 0.0)
        e = card.get("e", s + 1.0)
        words = card.get("w", [])
        text = " ".join(w.get("t", "") for w in words).strip()
        if not text:
            continue
        t0_str = seconds_to_srt_timestamp(s)
        t1_str = seconds_to_srt_timestamp(e)
        srt_lines.append(f"{idx}\n{t0_str} --> {t1_str}\n{text}\n")

    out_file = Path(work_dir) / "timeline.srt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    return out_file

def export_markers_edl(work_dir, caps, total_dur, fps=30.0):
    """
    Exports CMX3600 EDL with DaVinci Resolve marker color and note extensions.
    Import in DaVinci: Timelines > Import > Timeline Markers from EDL...
    """
    cards = caps.get("cards", []) if caps else []
    lines = [
        "TITLE: ReelForge Markers",
        "FCM: NON-DROP FRAME",
        ""
    ]

    for idx, card in enumerate(cards, start=1):
        s = card.get("s", 0.0)
        e = card.get("e", s + 1.0)
        words = card.get("w", [])
        text = " ".join(w.get("t", "") for w in words).strip()
        hot_words = [w.get("t", "") for w in words if w.get("hot") or w.get("fx")]
        
        # Color coding:
        # Yellow: Emphasized words
        # Rose: Hook (first 5 seconds)
        # Mint: Outro / CTA (last 5 seconds)
        # Cyan: Normal speech
        if hot_words:
            color = "ResolveColorYellow"
        elif s < 5.0:
            color = "ResolveColorRose"
        elif e >= (total_dur - 5.5):
            color = "ResolveColorMint"
        else:
            color = "ResolveColorCyan"

        dur_frames = max(1, int(round((e - s) * fps)))
        tc_in = seconds_to_timecode(s, fps)
        tc_out = seconds_to_timecode(s + (1.0 / fps), fps)

        entry_num = f"{idx:03d}"
        lines.append(f"{entry_num}  001      V     C        {tc_in} {tc_out} {tc_in} {tc_out}")
        lines.append(f" |C:{color} |M:{text} |D:{dur_frames}")
        lines.append("")

    out_file = Path(work_dir) / "markers.edl"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_file

def export_markers_csv(work_dir, caps, total_dur, fps=30.0):
    """
    Exports standard DaVinci Resolve Marker CSV file:
    Import in DaVinci: Timelines > Import > Timeline Markers from CSV...
    """
    cards = caps.get("cards", []) if caps else []
    lines = ["Timecode In,Timecode Out,Name,Comment,Color"]

    for card in cards:
        s = card.get("s", 0.0)
        e = card.get("e", s + 1.0)
        words = card.get("w", [])
        text = " ".join(w.get("t", "") for w in words).strip().replace(",", " ")
        hot_words = [w.get("t", "") for w in words if w.get("hot") or w.get("fx")]
        
        if hot_words:
            color = "Yellow"
            comment = f"🔥 Emphasized: {' '.join(hot_words)}"
        elif s < 5.0:
            color = "Rose"
            comment = "🎣 Hook Sentence"
        elif e >= (total_dur - 5.5):
            color = "Mint"
            comment = "📢 Outro / Call To Action"
        else:
            color = "Cyan"
            comment = "Dialogue Caption"

        tc_in = seconds_to_timecode(s, fps)
        tc_out = seconds_to_timecode(e, fps)
        lines.append(f"{tc_in},{tc_out},{text},{comment},{color}")

    out_file = Path(work_dir) / "markers.csv"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_file


# ═════════════════════════════════════════════════════════════════════════════
# 8) Standalone DaVinci Resolve Studio Automation Script
# ═════════════════════════════════════════════════════════════════════════════

def generate_import_script(work_dir, proj_name, fps=30.0):
    """
    Writes a standalone Python automation script into <work_dir>/import_to_davinci.py.
    When executed while DaVinci Resolve Studio is open, it connects to the Resolve API,
    creates the project, sets 1080x1920 vertical resolution, imports media into Media Pool,
    imports timeline.fcpxml, and adds timeline duration markers directly!
    """
    script_content = f'''# -*- coding: utf-8 -*-
"""
DaVinci Resolve Studio 1-Click Project & Timeline Importer
Generated automatically by Islam AI ReelForge
"""
import os
import sys
import json
import platform

# Universal UTF-8 Console
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJECT_NAME = "{proj_name}"
FPS = {fps}
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
FCPXML_FILE = os.path.join(WORK_DIR, "timeline.fcpxml")
FCP7_FILE = os.path.join(WORK_DIR, "timeline.xml")
SRT_FILE = os.path.join(WORK_DIR, "timeline.srt")
CAPS_FILE = os.path.join(WORK_DIR, "caps.json")

def find_davinci_script_module():
    """Detects DaVinciResolveScript module path across Windows, macOS, and Linux."""
    sys_plat = platform.system().lower()
    script_paths = []
    
    if sys_plat == "windows":
        prog_data = os.environ.get("PROGRAMDATA", r"C:\\ProgramData")
        prog_files = os.environ.get("PROGRAMFILES", r"C:\\Program Files")
        script_paths.append(os.path.join(prog_data, r"Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules"))
        if "RESOLVE_SCRIPT_API" not in os.environ:
            os.environ["RESOLVE_SCRIPT_API"] = os.path.join(prog_data, r"Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting")
        if "RESOLVE_SCRIPT_LIB" not in os.environ:
            os.environ["RESOLVE_SCRIPT_LIB"] = os.path.join(prog_files, r"Blackmagic Design\\DaVinci Resolve\\fusionscript.dll")
    elif sys_plat == "darwin":
        script_paths.append("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
        if "RESOLVE_SCRIPT_API" not in os.environ:
            os.environ["RESOLVE_SCRIPT_API"] = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
        if "RESOLVE_SCRIPT_LIB" not in os.environ:
            os.environ["RESOLVE_SCRIPT_LIB"] = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
    elif sys_plat == "linux":
        script_paths.append("/opt/resolve/Developer/Scripting/Modules")
        if "RESOLVE_SCRIPT_API" not in os.environ:
            os.environ["RESOLVE_SCRIPT_API"] = "/opt/resolve/Developer/Scripting"
        if "RESOLVE_SCRIPT_LIB" not in os.environ:
            os.environ["RESOLVE_SCRIPT_LIB"] = "/opt/resolve/libs/Fusion/fusionscript.so"

    for p in script_paths:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)

def main():
    print("=" * 70)
    print("🎬 DaVinci Resolve 1-Click Project & Timeline Importer")
    print("=" * 70)

    find_davinci_script_module()

    try:
        import DaVinciResolveScript as dvr
    except ImportError:
        print("❌ Could not import 'DaVinciResolveScript'.")
        print("Please verify that DaVinci Resolve Studio is installed on this computer.")
        print("\\nManual Import Guide:")
        print("  1. Open DaVinci Resolve.")
        print("  2. File > Import > Timeline > Import AAF, EDL, XML...")
        print(f"  3. Select: {{FCPXML_FILE}}")
        sys.exit(1)

    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        print("⚠️  DaVinci Resolve is NOT currently open.")
        print("Please start DaVinci Resolve, then re-run this script!")
        print("\\nOr import manually right now:")
        print("  In DaVinci Resolve: File > Import > Timeline > Import AAF, EDL, XML...")
        print(f"  Select: {{FCPXML_FILE}}")
        sys.exit(0)

    print("✅ Connected to DaVinci Resolve Application!")
    pm = resolve.GetProjectManager()
    if not pm:
        print("❌ Failed to get Project Manager.")
        sys.exit(1)

    # 1. Create or Open Project
    proj = pm.GetCurrentProject()
    if not proj or proj.GetName() != PROJECT_NAME:
        proj = pm.LoadProject(PROJECT_NAME)
        if not proj:
            print(f"📁 Creating new project: {{PROJECT_NAME}}...")
            proj = pm.CreateProject(PROJECT_NAME)
            if not proj:
                print(f"⚠️ Could not create {{PROJECT_NAME}}, using current project.")
                proj = pm.GetCurrentProject()

    print(f"🎯 Active Project: {{proj.GetName()}}")

    # 2. Configure Vertical 9:16 Settings (1080x1920)
    proj.SetSetting("timelineResolutionWidth", "1080")
    proj.SetSetting("timelineResolutionHeight", "1920")
    proj.SetSetting("timelineOutputResolutionWidth", "1080")
    proj.SetSetting("timelineOutputResolutionHeight", "1920")
    proj.SetSetting("timelineFrameRate", str(FPS))
    proj.SetSetting("useCustomSettings", "1")
    print(f"📐 Resolution configured: 1080x1920 (Vertical 9:16) @ {{FPS}} fps")

    # 3. Import Source Media into Media Pool
    mp = proj.GetMediaPool()
    root_folder = mp.GetRootFolder()

    media_to_import = []
    for fname in ["src.mov", "src.mp4", "src_sdr.mov", "a_clean.wav", "audio.wav", "sfx.wav"]:
        fp = os.path.join(WORK_DIR, fname)
        if os.path.exists(fp):
            media_to_import.append(fp)
            
    sfx_clips_dir = os.path.join(WORK_DIR, "sfx_clips")
    if os.path.exists(sfx_clips_dir):
        for f in os.listdir(sfx_clips_dir):
            if f.endswith(".wav"):
                media_to_import.append(os.path.join(sfx_clips_dir, f))

    if media_to_import:
        print(f"📦 Importing {{len(media_to_import)}} media assets into Media Pool...")
        mp.ImportMedia(media_to_import)

    # 4. Import Timeline from FCPXML
    tl = None
    target_xml = FCPXML_FILE if os.path.exists(FCPXML_FILE) else FCP7_FILE
    if os.path.exists(target_xml):
        print(f"🎞️  Importing timeline from: {{os.path.basename(target_xml)}}...")
        try:
            tl = mp.ImportTimelineFromFile(target_xml)
        except Exception as e:
            print(f"ImportTimelineFromFile note: {{e}}")

    if tl:
        print(f"🎉 Timeline imported: {{tl.GetName()}}")
        proj.SetCurrentTimeline(tl)
        tl.SetSetting("useCustomSettings", "1")
        tl.SetSetting("timelineResolutionWidth", "1080")
        tl.SetSetting("timelineResolutionHeight", "1920")
    else:
        print("ℹ️  Note: Direct API timeline import not available in this Resolve edition.")
        print("    Simply use File > Import > Timeline > Import AAF, EDL, XML... to import.")

    # 5. Add Timeline Markers from caps.json
    if tl and os.path.exists(CAPS_FILE):
        try:
            caps_data = json.load(open(CAPS_FILE, encoding="utf-8"))
            cards = caps_data.get("cards", [])
            start_frame = tl.GetStartFrame()
            marker_count = 0
            
            for card in cards:
                cs = card.get("s", 0.0)
                ce = card.get("e", cs + 1.0)
                frame = start_frame + int(round(cs * FPS))
                dur = max(1, int(round((ce - cs) * FPS)))
                words = card.get("w", [])
                text = " ".join(w.get("t", "") for w in words).strip()
                hot_words = [w.get("t", "") for w in words if w.get("hot") or w.get("fx")]

                if hot_words:
                    color = "Yellow"
                    note = f"🔥 Emphasized: {{', '.join(hot_words)}}"
                elif cs < 5.0:
                    color = "Rose"
                    note = "🎣 Hook"
                else:
                    color = "Cyan"
                    note = "Caption"

                if tl.AddMarker(frame, color, text, note, dur):
                    marker_count += 1

            print(f"🏷️  Added {{marker_count}} colored caption markers to timeline!")
        except Exception as e:
            print(f"Marker import note: {{e}}")

    # 6. Switch to Edit Page
    resolve.OpenPage("edit")
    print("\\n" + "=" * 70)
    print("🚀 DaVinci Resolve Timeline is Ready!")
    print("=" * 70 + "\\n")

if __name__ == "__main__":
    main()
'''
    out_file = Path(work_dir) / "import_to_davinci.py"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(script_content)
    return out_file


# ═════════════════════════════════════════════════════════════════════════════
# 9) Main CLI Execution Routine
# ═════════════════════════════════════════════════════════════════════════════

def export_davinci_project(work_dir, fps_override=None, auto_import=False):
    """Orchestrates complete DaVinci Resolve timeline and project export."""
    work_dir = Path(work_dir).resolve()
    print("=" * 75)
    print("🎞️  Islam AI ReelForge — Universal DaVinci Resolve Timeline Exporter")
    print("=" * 75)

    media = find_project_media(work_dir)

    if not media["cut_file"]:
        print(f"❌ Error: 'cut.json' not found in {work_dir}")
        print("Please run 01_cut_plan.py or reelforge.py first.")
        sys.exit(1)

    if not media["src_video"]:
        print(f"❌ Error: Source video (src.mov / src.mp4) not found in {work_dir}")
        sys.exit(1)

    # Load cut plan
    cut_data = json.load(open(media["cut_file"], encoding="utf-8"))
    cuts = cut_data.get("keep", [])
    if not cuts:
        print("❌ Error: 'cut.json' contains no keep segments.")
        sys.exit(1)

    # Load captions
    caps_data = None
    if media["caps_file"]:
        caps_data = json.load(open(media["caps_file"], encoding="utf-8"))

    # Load SFX
    sfx_data = None
    if media["sfx_file"]:
        sfx_data = json.load(open(media["sfx_file"], encoding="utf-8"))

    # Video & Audio Probing
    meta = probe_video_stream(media["src_video"])
    fps = float(fps_override) if fps_override else meta.get("fps", 30.0)
    
    # Audio Track determination
    audio_path = media["src_audio"]
    if not audio_path:
        # Extract audio from src_video if no wav found
        extracted_audio = work_dir / "audio.wav"
        if not extracted_audio.exists():
            print(f"🔊 Extracting 48kHz audio track from video -> {extracted_audio.name}...")
            cmd = [
                "ffmpeg", "-v", "error", "-y",
                "-i", str(media["src_video"]),
                "-vn", "-ar", "48000", "-ac", "2",
                str(extracted_audio)
            ]
            subprocess.run(cmd, check=True)
        audio_path = extracted_audio

    print(f"📁 Workspace:        {work_dir.name}")
    print(f"📹 Source Video:     {media['src_video'].name} ({meta['width']}x{meta['height']} @ {fps:.2f} fps)")
    print(f"🎙️ Dialogue Audio:    {audio_path.name}")
    print(f"✂️ Video Cut Blocks:  {len(cuts)} cuts from cut.json")
    if caps_data:
        print(f"💬 Caption Cards:    {len(caps_data.get('cards', []))} cards from caps.json")

    # 1. Synthesize SFX library into sfx_clips/
    sfx_dir = work_dir / "sfx_clips"
    print(f"🔊 Generating broadcast SFX sound library -> {sfx_dir.name}/...")
    synthesize_sfx_library(sfx_dir)
    sfx_events = parse_sfx_events(sfx_data, sfx_dir)
    print(f"⚡ Sound Effects:    {len(sfx_events)} SFX events placed on Audio Track 2 (A2)")

    # 2. Export FCPXML v1.8 / v1.9 (Primary timeline)
    print("📝 Generating standard FCPXML v1.8/v1.9 timeline...")
    fcpxml_path = export_fcpxml(work_dir, cuts, caps_data, sfx_events, media["src_video"], audio_path, meta, fps=fps)

    # 3. Export FCP7 XML (xmeml v5 Companion)
    print("📝 Generating FCP7 XML (xmeml v5) companion...")
    fcp7_path = export_fcp7_xml(work_dir, cuts, sfx_events, media["src_video"], audio_path, meta, fps=fps)

    # 4. Export Subtitles & Markers (.srt, .edl, .csv)
    total_dur = cut_data.get("total", sum(e - s for s, e in cuts))
    srt_path = export_srt(work_dir, caps_data)
    edl_path = export_markers_edl(work_dir, caps_data, total_dur, fps=fps)
    csv_path = export_markers_csv(work_dir, caps_data, total_dur, fps=fps)

    # 5. Generate Standalone Python Script for DaVinci Resolve Studio
    proj_name = f"ReelForge_{work_dir.name.replace(' ', '_')}"
    script_path = generate_import_script(work_dir, proj_name, fps=fps)

    print("\n" + "=" * 75)
    print("✅ DaVinci Resolve Timeline Package Generated Successfully!")
    print("=" * 75)
    print(f"📍 FCPXML Timeline (Primary):   {fcpxml_path}")
    print(f"📍 FCP7 XML (Companion):        {fcp7_path}")
    print(f"📍 Subtitle Track (.srt):       {srt_path}")
    print(f"📍 Markers (EDL):               {edl_path}")
    print(f"📍 Markers (CSV):               {csv_path}")
    print(f"📍 1-Click Import Script:       {script_path}")
    print("\n🎯 How to use in DaVinci Resolve:")
    print("  METHOD 1 (Automatic via Python Scripting API):")
    print(f"    Open DaVinci Resolve, then run: python \"{script_path}\"")
    print("  METHOD 2 (Direct GUI Import):")
    print("    In DaVinci Resolve: File > Import > Timeline > Import AAF, EDL, XML...")
    print(f"    Select: {fcpxml_path.name}")
    print("  METHOD 3 (Subtitles & Markers):")
    print(f"    Drag '{srt_path.name}' onto Subtitle Track, or import '{csv_path.name}' for markers.")
    print("=" * 75 + "\n")

    if auto_import:
        print("🚀 Invoking DaVinci Resolve Studio API Importer...")
        subprocess.run([sys.executable, str(script_path)])

def main():
    parser = argparse.ArgumentParser(
        description="Islam AI ReelForge — Universal DaVinci Resolve Timeline Exporter"
    )
    parser.add_argument("work_dir", help="Path to project workspace folder containing cut.json")
    parser.add_argument("--fps", type=float, default=None, help="Force specific timeline frame rate (default: auto-detected or 30.0)")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Automatically connect to DaVinci Resolve API if running")

    args = parser.parse_args()
    export_davinci_project(args.work_dir, fps_override=args.fps, auto_import=args.do_import)

if __name__ == "__main__":
    main()
