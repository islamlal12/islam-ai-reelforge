# -*- coding: utf-8 -*-
"""تسمية الفيديو النهائي باسم دلالي مرتبط بموضوع الفيديو (Semantic Video Naming).
يستخرج عنواناً دلالياً معبراً من موضوع الفيديو (theme.json / a.json / script.txt)
ويسمي به ملف الإخراج النهائي بدلاً من الأسماء العامة (ad-final.mp4 / ad-master.mp4).

الاستخدام:
    python 28c_semantic_namer.py <workdir> [--apply <target_file.mp4>] [--json]
"""
import sys, os, json, re

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    name = re.sub(r'_+', '_', name)
    return name.strip('_')

def get_semantic_title(work_dir):
    work_dir = os.path.abspath(work_dir)
    
    # 1. Check theme.json for explicit title / topic
    theme_file = os.path.join(work_dir, "theme.json")
    if os.path.exists(theme_file):
        try:
            th = json.load(open(theme_file, encoding="utf-8"))
            if th.get("title"):
                return sanitize_filename(th["title"])
            if th.get("topic"):
                return sanitize_filename(th["topic"])
            if th.get("hook"):
                return sanitize_filename(th["hook"])
        except Exception:
            pass

    # 2. Check folder name if meaningful (not temp / root)
    folder_name = os.path.basename(work_dir)
    if folder_name and folder_name not in ("work", "tmp", "output", "dist", "video", "reel"):
        clean_folder = sanitize_filename(folder_name)
        if len(clean_folder) >= 4:
            return clean_folder

    # 3. Check a.json / caps.json for first strong sentence or topic
    for fn in ("caps.json", "a.json"):
        p = os.path.join(work_dir, fn)
        if os.path.exists(p):
            try:
                data = json.load(open(p, encoding="utf-8"))
                text = ""
                if "cards" in data and data["cards"]:
                    words = [w["t"] for c in data["cards"][:3] for w in c.get("w", [])]
                    text = " ".join(words[:6])
                elif "segments" in data and data["segments"]:
                    text = data["segments"][0].get("text", "")
                
                if text:
                    clean = re.sub(r'[^\w\s\u0600-\u06FF]', '', text).strip()
                    tokens = [w for w in clean.split() if w not in ("السلام", "عليكم", "اليوم", "هذا", "فيديو", "مرحبا")]
                    if tokens:
                        return sanitize_filename("_".join(tokens[:5]))
            except Exception:
                pass

    return "ريل_محتوى_إسلام_آي"

def main():
    if len(sys.argv) < 2:
        print("Usage: python 28c_semantic_namer.py <workdir> [--apply <target.mp4>]")
        sys.exit(1)

    work_dir = os.path.abspath(sys.argv[1])
    target_mp4 = None
    if "--apply" in sys.argv:
        idx = sys.argv.index("--apply")
        if idx + 1 < len(sys.argv):
            target_mp4 = os.path.abspath(sys.argv[idx + 1])

    title = get_semantic_title(work_dir)
    semantic_name = f"{title}.mp4"
    dest_path = os.path.join(work_dir, semantic_name)

    print(f"📌 Semantic Title: {title}")
    print(f"📁 Target Output: {semantic_name}")

    if target_mp4 and os.path.exists(target_mp4):
        import shutil
        if os.path.abspath(target_mp4) != os.path.abspath(dest_path):
            shutil.copy2(target_mp4, dest_path)
            print(f"✅ Created semantic named file: {dest_path}")

    if "--json" in sys.argv:
        print(json.dumps({"title": title, "filename": semantic_name, "path": dest_path}, ensure_ascii=False))

if __name__ == "__main__":
    main()
