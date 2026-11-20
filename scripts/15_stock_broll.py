# -*- coding: utf-8 -*-
"""
===================================================================================
Islam AI ReelForge — Smart B-Roll Stock Sourcing & Normalization Engine
===================================================================================
Automates fetching, downloading, and 9:16 normalization of royalty-free HD stock
footage from Pexels and Pixabay APIs (or local folders).

Integrated seamlessly into the Storyboard-First Protocol:
- Fullscreen Cutaway: Replaces talking-head for 2-4 seconds during strong narrative beats.
- Card / PIP (Picture-in-Picture): 24px rounded floating cards above captions.
- Faceless Primary Track: Generates the entire visual storyline sequentially.

Features:
- Free Pexels Video API & Pixabay Video API integration.
- Automatic Arabic -> English semantic visual query translation.
- High-efficiency ffmpeg conversion to exact 1080x1920 @ 30fps (H.264).
- Generates <work>/broll_manifest.json for downstream DaVinci Resolve & render engines.

Usage:
  python scripts/15_stock_broll.py <work_dir> search "ذكاء اصطناعي"
  python scripts/15_stock_broll.py <work_dir> fetch --query "developer coding" --dur 3.5 --out broll_01.mp4
  python scripts/15_stock_broll.py <work_dir> plan --file storyboard_broll.json
===================================================================================
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import subprocess
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Built-in Arabic -> English Semantic Keyword Dictionary
AR_TO_EN_KEYWORDS = {
    "ذكاء اصطناعي": "artificial intelligence technology neural network robot futuristic",
    "تطبيق": "mobile phone app smartphone scrolling user screen",
    "تطبيقات": "mobile apps smartphone user technology",
    "برمجة": "software developer coding laptop keyboard programmer screen",
    "كود": "coding programming computer screen source code dark",
    "موقع": "website computer screen internet browsing laptop",
    "ارباح": "stock market trading money finance crypto growth chart",
    "فلوس": "money counting cash business finance success",
    "استثمار": "investment finance graph business growth chart",
    "تجارة": "ecommerce online store shopping warehouse package delivery",
    "تسويق": "digital marketing social media analytics dashboard advertising",
    "محتوى": "video production camera creator youtube recording studio",
    "انتاج": "video editing filmmaker camera lens creative work",
    "روبوت": "robot robotics cyborg humanoid future automation",
    "بيانات": "big data server room data center networking cloud",
    "سرعة": "fast motion lights highway traffic night speed",
    "مستقبل": "futuristic city cyber technology abstract neon lights",
    "عمل": "modern office business meeting teamwork professional working",
    "نجاح": "celebration success winning achievement happy entrepreneur",
    "فكرة": "light bulb creative idea inspiration thinking brainstorm",
    "طبيعة": "nature landscape cinematic drone mountains forest ocean",
    "قهوة": "coffee pouring espresso cafe morning cozy work",
    "سفر": "travel airplane airport flying scenic destination luggage",
    "ساعة": "clock watch time passing timelapse ticking deadline",
    "قفل": "cyber security digital lock padlock shield cybersecurity",
}

def resolve_api_keys(work_dir=None):
    """Retrieves Pexels and Pixabay keys from environment or .env files."""
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
    
    # Check potential .env files
    cand_env_files = []
    if work_dir:
        cand_env_files.append(Path(work_dir) / ".env")
        cand_env_files.append(Path(work_dir).parent / ".env")
    cand_env_files.append(Path.cwd() / ".env")
    cand_env_files.append(Path.home() / ".env")

    for env_path in cand_env_files:
        if env_path.exists() and env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("PEXELS_API_KEY=") and not pexels_key:
                            pexels_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("PIXABAY_API_KEY=") and not pixabay_key:
                            pixabay_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass

    return {
        "pexels": pexels_key,
        "pixabay": pixabay_key
    }

def translate_query(query):
    """Maps Arabic terms to visual English search terms for stock engines."""
    clean_q = query.strip()
    for ar_term, en_term in AR_TO_EN_KEYWORDS.items():
        if ar_term in clean_q:
            return en_term
    return clean_q

def search_pexels_videos(query, api_key, per_page=10):
    """Queries Pexels Video Search API for vertical / portrait HD videos."""
    if not api_key:
        return []
    
    en_query = translate_query(query)
    encoded_q = urllib.parse.quote(en_query)
    url = f"https://api.pexels.com/videos/search?query={encoded_q}&orientation=portrait&per_page={per_page}"
    
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "User-Agent": "IslamAI-ReelForge/2.0"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            videos = data.get("videos", [])
            results = []
            for v in videos:
                v_files = v.get("video_files", [])
                # Prioritize vertical HD files (1080x1920 or 720x1280)
                best_file = None
                for vf in v_files:
                    w = vf.get("width", 0)
                    h = vf.get("height", 0)
                    if h > w and h >= 1280:
                        best_file = vf
                        if h == 1920:
                            break
                if not best_file and v_files:
                    best_file = v_files[0]

                if best_file:
                    results.append({
                        "id": f"pexels_{v.get('id')}",
                        "provider": "pexels",
                        "title": en_query,
                        "duration": v.get("duration", 0),
                        "width": best_file.get("width", 1080),
                        "height": best_file.get("height", 1920),
                        "url": best_file.get("link"),
                        "preview": v.get("image")
                    })
            return results
    except Exception as ex:
        print(f"⚠️ Pexels search error for '{query}': {ex}")
        return []

def search_pixabay_videos(query, api_key, per_page=10):
    """Queries Pixabay Video Search API for vertical HD videos."""
    if not api_key:
        return []

    en_query = translate_query(query)
    encoded_q = urllib.parse.quote(en_query)
    url = f"https://pixabay.com/api/videos/?key={api_key}&q={encoded_q}&video_type=film&orientation=vertical&per_page={per_page}"
    
    req = urllib.request.Request(url, headers={
        "User-Agent": "IslamAI-ReelForge/2.0"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            hits = data.get("hits", [])
            results = []
            for h in hits:
                vids = h.get("videos", {})
                cand = vids.get("large") or vids.get("medium") or vids.get("small")
                if cand:
                    results.append({
                        "id": f"pixabay_{h.get('id')}",
                        "provider": "pixabay",
                        "title": en_query,
                        "duration": h.get("duration", 0),
                        "width": cand.get("width", 1080),
                        "height": cand.get("height", 1920),
                        "url": cand.get("url"),
                        "preview": h.get("picture_id")
                    })
            return results
    except Exception as ex:
        print(f"⚠️ Pixabay search error for '{query}': {ex}")
        return []

def normalize_broll_clip(input_source, out_mp4, target_dur=3.5, start_offset=0.0):
    """
    Downloads / crops / scales video to exact 1080x1920 (9:16) @ 30fps H.264 without audio.
    """
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    
    # High-quality 9:16 vertical crop and scale filter
    vf_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "fps=30,"
        "format=yuv420p"
    )
    
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-ss", str(start_offset),
        "-i", str(input_source),
        "-t", str(target_dur),
        "-vf", vf_filter,
        "-an",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True)
    return str(out_mp4)

def fetch_smart_broll(work_dir, query, out_filename, dur=3.5, mode="cutaway", start_t=0.0):
    """
    Finds and downloads the best matching B-roll video clip into <work>/broll/.
    """
    work_dir = Path(work_dir).resolve()
    broll_dir = work_dir / "broll"
    broll_dir.mkdir(parents=True, exist_ok=True)
    out_path = broll_dir / out_filename

    keys = resolve_api_keys(work_dir)
    results = []

    # 1. Search Pexels
    if keys["pexels"]:
        print(f"🔍 Searching Pexels for '{query}'...")
        results = search_pexels_videos(query, keys["pexels"])

    # 2. Search Pixabay if Pexels empty
    if not results and keys["pixabay"]:
        print(f"🔍 Searching Pixabay for '{query}'...")
        results = search_pixabay_videos(query, keys["pixabay"])

    # 3. Check local stock_source/ folder
    if not results:
        local_stock_dir = work_dir / "stock_source"
        if local_stock_dir.exists():
            for f in local_stock_dir.glob("*.mp4"):
                results.append({
                    "id": f.stem,
                    "provider": "local",
                    "title": f.stem,
                    "duration": 10.0,
                    "url": str(f)
                })

    if not results:
        # If no API keys or offline, generate an aesthetic cinematic placeholder video
        print(f"⚠️ No API keys found or search yielded no results. Creating procedural cinematic B-Roll placeholder for '{query}'...")
        font_arg = ":fontfile='C\\:/Windows/Fonts/arial.ttf'" if os.name == "nt" else ""
        synth_cmd = [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x0B1528:s=1080x1920:d={dur}",
            "-vf", f"drawbox=x=100:y=200:w=880:h=1520:color=0x0C68E9@0.5:t=8,drawtext=text='B-ROLL SCENE'{font_arg}:fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(out_path)
        ]
        try:
            subprocess.run(synth_cmd, check=True)
        except Exception:
            # Fallback without drawtext if font issues occur
            synth_cmd_simple = [
                "ffmpeg", "-v", "error", "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x0B1528:s=1080x1920:d={dur}",
                "-vf", "drawbox=x=100:y=200:w=880:h=1520:color=0x0C68E9@0.5:t=8",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(out_path)
            ]
            subprocess.run(synth_cmd_simple, check=True)
        provider = "synthetic"
    else:
        chosen = results[0]
        print(f"📥 Downloading matching B-Roll from {chosen['provider']} -> {out_filename} ({dur}s)...")
        normalize_broll_clip(chosen["url"], out_path, target_dur=dur)
        provider = chosen["provider"]

    return {
        "file": f"broll/{out_path.name}",
        "full_path": str(out_path),
        "query": query,
        "provider": provider,
        "dur": dur,
        "start_t": start_t,
        "end_t": start_t + dur,
        "display_mode": mode
    }

def process_broll_manifest(work_dir, plan_file=None):
    """
    Parses a B-Roll plan or creates default manifest <work>/broll_manifest.json.
    """
    work_dir = Path(work_dir).resolve()
    manifest_path = work_dir / "broll_manifest.json"
    
    plan_data = []
    if plan_file and os.path.exists(plan_file):
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
            
    manifest = {
        "work_dir": str(work_dir),
        "clips": []
    }
    
    for idx, item in enumerate(plan_data):
        q = item.get("query", "technology")
        dur = float(item.get("dur", 3.0))
        mode = item.get("mode", "cutaway")
        start_t = float(item.get("start_t", 0.0))
        fname = f"broll_{idx+1:02d}.mp4"
        
        clip_info = fetch_smart_broll(
            work_dir=work_dir,
            query=q,
            out_filename=fname,
            dur=dur,
            mode=mode,
            start_t=start_t
        )
        manifest["clips"].append(clip_info)
        
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        
    print(f"✅ B-Roll manifest written to: {manifest_path}")
    return manifest

def main():
    parser = argparse.ArgumentParser(description="Islam AI ReelForge Smart B-Roll Sourcing")
    subparsers = parser.add_subparsers(dest="command")
    
    # search subcommand
    p_search = subparsers.add_parser("search", help="Search stock footage")
    p_search.add_argument("query", help="Keywords (Arabic or English)")
    p_search.add_argument("--work", default=".", help="Workspace folder")
    
    # fetch subcommand
    p_fetch = subparsers.add_parser("fetch", help="Fetch single B-roll video")
    p_fetch.add_argument("work_dir", help="Workspace folder")
    p_fetch.add_argument("--query", required=True, help="Keywords")
    p_fetch.add_argument("--dur", type=float, default=3.5, help="Duration in seconds")
    p_fetch.add_argument("--out", default="broll_01.mp4", help="Output file name")
    p_fetch.add_argument("--mode", default="cutaway", choices=["cutaway", "pip", "card", "split"], help="Display mode")
    p_fetch.add_argument("--start", type=float, default=0.0, help="Timeline start seconds")

    # plan subcommand
    p_plan = subparsers.add_parser("plan", help="Execute B-Roll plan from JSON")
    p_plan.add_argument("work_dir", help="Workspace folder")
    p_plan.add_argument("--file", required=True, help="Path to storyboard_broll.json")

    args = parser.parse_args()
    
    if args.command == "search":
        keys = resolve_api_keys(args.work)
        res = []
        if keys["pexels"]:
            res += search_pexels_videos(args.query, keys["pexels"])
        if keys["pixabay"]:
            res += search_pixabay_videos(args.query, keys["pixabay"])
        print(f"Found {len(res)} results for query '{args.query}':")
        for r in res[:5]:
            print(f" - [{r['provider']}] {r['title']} ({r['width']}x{r['height']} - {r['duration']}s): {r['url']}")
    elif args.command == "fetch":
        fetch_smart_broll(
            work_dir=args.work_dir,
            query=args.query,
            out_filename=args.out,
            dur=args.dur,
            mode=args.mode,
            start_t=args.start
        )
    elif args.command == "plan":
        process_broll_manifest(args.work_dir, args.file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
