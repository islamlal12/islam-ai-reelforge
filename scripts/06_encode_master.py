# -*- coding: utf-8 -*-
"""Cross-platform video encoder & audio mastering engine for Islam AI ReelForge.
Encodes visual frames with synchronized audio & sound effects, and masters to -14.0 LUFS.
"""
import os, sys, json, subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def encode_and_master(work_dir, add_cover=True):
    work_dir = os.path.abspath(work_dir)
    caps_path = os.path.join(work_dir, "caps.json")
    sfx_path = os.path.join(work_dir, "sfx.json")
    
    if not os.path.exists(caps_path):
        print(f"❌ Error: {caps_path} not found.")
        sys.exit(1)
        
    caps = json.load(open(caps_path, encoding="utf-8"))
    sfx = json.load(open(sfx_path, encoding="utf-8")) if os.path.exists(sfx_path) else {}
    dur = round(caps.get("total", 0) + sfx.get("outro", 0.5), 3)
    fade = round(max(0, dur - 0.6), 3)
    
    out_final = os.path.join(work_dir, "ad-final.mp4")
    out_master = os.path.join(work_dir, "ad-master.mp4")
    
    cutz = os.path.join(work_dir, "cutz.mp4")
    sfx_wav = os.path.join(work_dir, "sfx.wav")
    frames_pattern = os.path.join(work_dir, "out", "%05d.jpg")
    
    has_frames = os.path.exists(os.path.join(work_dir, "out"))
    has_sfx = os.path.exists(sfx_wav)
    
    print(f"🎬 Encoding video (Duration: {dur}s)...", flush=True)
    
    if has_frames and has_sfx:
        fc = (
            f"[0:v]scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p[vo];"
            f"[1:a]apad=pad_dur=8[a0];"
            f"[a0][2:a]amix=inputs=2:duration=first:normalize=0[am];"
            f"[am]atrim=0:{dur},asetpts=PTS-STARTPTS,afade=t=out:st={fade}:d=0.6[ao]"
        )
        cmd_encode = [
            "ffmpeg", "-v", "error", "-nostats", "-framerate", "30",
            "-i", frames_pattern,
            "-i", cutz,
            "-i", sfx_wav,
            "-filter_complex", fc,
            "-map", "[vo]", "-map", "[ao]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
            "-maxrate", "8M", "-bufsize", "16M",
            "-profile:v", "high", "-level", "4.0",
            "-pix_fmt", "yuv420p", "-color_range", "tv",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", "-y", out_final
        ]
    else:
        # Fallback direct encode if cutz already has merged audio
        cmd_encode = [
            "ffmpeg", "-v", "error", "-nostats",
            "-i", cutz,
            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", "-y", out_final
        ]
        
    subprocess.run(cmd_encode, check=True)
    print(f"✅ Generated: {out_final}", flush=True)
    
    # Audio Broadcast Mastering to -14.0 LUFS
    print(f"🔊 Calibrating audio to -14.0 LUFS broadcast standard...", flush=True)
    cmd_master = [
        "ffmpeg", "-v", "error", "-nostats",
        "-i", out_final,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-y", out_master
    ]
    subprocess.run(cmd_master, check=True)
    print(f"✅ Mastered reel created: {out_master}", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 06_encode_master.py <work_dir>")
        sys.exit(1)
    encode_and_master(sys.argv[1])
