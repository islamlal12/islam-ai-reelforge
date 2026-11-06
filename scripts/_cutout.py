# -*- coding: utf-8 -*-
"""صورة الشخص من الفيديو نفسه — يختار أحسن فريم (وجه كبير + واضح) ويقصّه بخلفية شفافة.
   يستخدمه 28_cover.py (--cut) و33_thumb.py (--video). القص بـpersonmask.swift (Vision المدمج بالماك) أو تلقائياً عبر rembg (u2net_human_seg) على ويندوز ولينكس.
   python3 _cutout.py <video> <out.png> [--t 3.2] [--n 12]"""
import os, sys, json, shutil, subprocess, tempfile
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = ["src_sdr.mov", "src_fixed.mov", "src.mov", "src.mp4", "ad-master.mp4", "ad-final.mp4"]   # المصدر أول: النهائي فيه كابشن محروق


def find_video(W):
    for c in SOURCES:
        if os.path.exists(os.path.join(W, c)): return os.path.join(W, c)
    return ""


def _dur(f):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f],
                         capture_output=True, text=True).stdout
    try:
        return float((out or "").strip() or 0)
    except Exception:
        return 0.0


def _bin(cache):
    if sys.platform != "darwin":
        return None
    b = os.path.join(cache, "personmask")
    if not os.path.exists(b):
        if not shutil.which("swiftc"):
            return None
        os.makedirs(cache, exist_ok=True)
        try:
            subprocess.run(["swiftc", "-O", "-o", b, os.path.join(HERE, "personmask.swift")], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return None
    return b


def _run_rembg(in_dir, out_dir):
    """بديل عبر rembg لنظام ويندوز ولينكس كبديل تلقائي لـ Apple Vision (personmask.swift)."""
    try:
        from rembg import remove, new_session
    except ImportError:
        sys.exit("❌ قص الشخص من الفيديو على ويندوز/لينكس يتطلب مكتبة rembg: شغّل 'pip install rembg' أولاً، أو زوّدني بـ --photo (صورة مقصوصة مسبقاً بخلفية شفافة).")

    os.makedirs(out_dir, exist_ok=True)
    try:
        session = new_session("u2net_human_seg")
    except Exception:
        session = new_session()

    files = sorted([f for f in os.listdir(in_dir) if f.endswith(".jpg")])
    meta = []
    for f in files:
        in_path = os.path.join(in_dir, f)
        img = Image.open(in_path).convert("RGB")
        W, H = img.size
        mask = remove(img, session=session, only_mask=True)
        if not isinstance(mask, Image.Image):
            mask = Image.fromarray(mask)
        mask = mask.convert("L")
        out_png = os.path.join(out_dir, f.replace(".jpg", ".png"))
        mask.save(out_png)

        face_box = None
        # 1) محاولة كشف الوجه بدقة عبر OpenCV Haar Cascade
        try:
            import cv2
            gray = cv2.imread(in_path, cv2.IMREAD_GRAYSCALE)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(cascade_path)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))
            if len(faces) > 0:
                faces = sorted(faces, key=lambda b: b[2] * b[3], reverse=True)
                fx, fy, fw, fh = faces[0]
                face_box = {"x": float(fx), "y": float(fy), "w": float(fw), "h": float(fh)}
        except Exception:
            pass

        # 2) في حال عدم توفر cv2 أو عدم التقاط وجه، نقدّر مكان الوجه هندسياً من أبعاد قناع العزل
        if not face_box:
            al = np.asarray(mask)
            rows, cols = np.where(al > 40)
            if len(rows) > 0 and len(cols) > 0:
                min_r, max_r = rows.min(), rows.max()
                min_c, max_c = cols.min(), cols.max()
                bw = max_c - min_c
                bh = max_r - min_r
                fw = bw * 0.45
                fh = bh * 0.30
                fx = min_c + (bw - fw) / 2
                fy = min_r + bh * 0.05
                face_box = {"x": float(fx), "y": float(fy), "w": float(fw), "h": float(fh)}
            else:
                face_box = {"x": float(W * 0.3), "y": float(H * 0.15), "w": float(W * 0.4), "h": float(H * 0.3)}

        meta.append({"f": f, "face": face_box})

    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as mf:
        json.dump(meta, mf, ensure_ascii=False, indent=2)


def cutout(video, out, t=-1.0, n=12, cache=None):
    """يطلّع out (PNG شفاف مقصوص على حدود الشخص) ويرجّع الثانية اللي انأخذ منها."""
    tmp = tempfile.mkdtemp(); fr, mk = os.path.join(tmp, "f"), os.path.join(tmp, "m"); os.makedirs(fr)
    d = _dur(video)
    times = [t] if t >= 0 else [1.0 + (d - 2.0) * i / max(1, n - 1) for i in range(n)]
    for i, x in enumerate(times):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, x):.2f}", "-i", video, "-frames:v", "1", "-q:v", "2",
                        os.path.join(fr, f"{i:03d}.jpg")])
    native_bin = _bin(cache or os.path.join(tmp, "bt"))
    if native_bin and os.path.exists(native_bin):
        try:
            subprocess.run([native_bin, fr, mk, "accurate", "1.5"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            _run_rembg(fr, mk)
    else:
        _run_rembg(fr, mk)

    meta_file = os.path.join(mk, "meta.json")
    if not os.path.exists(meta_file):
        sys.exit("❌ فشل استخراج بيانات أقنعة الشخص (meta.json غير موجود)")

    with open(meta_file, "r", encoding="utf-8") as mf:
        meta = json.load(mf)

    best = None
    for r in meta:
        if "face" not in r: continue
        fpath = os.path.join(fr, r["f"])
        if not os.path.exists(fpath): continue
        a = np.asarray(Image.open(fpath).convert("L").resize((270, 480)), dtype=np.float32)
        sharp = np.abs(a[1:-1, 1:-1] * 4 - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]).var()
        score = r["face"]["w"] * np.sqrt(sharp)            # وجه كبير وواضح (مو مهزوز وسط حركة)
        if not best or score > best[0]: best = (score, r["f"])
    if not best: sys.exit("❌ ما لقيت وجه بالفيديو — أعطني --photo أو --t لثانية يبين فيها الوجه")
    f = best[1]; i = int(f.split(".")[0])
    im = Image.open(os.path.join(fr, f)).convert("RGB")
    m_file = os.path.join(mk, f.replace(".jpg", ".png"))
    if not os.path.exists(m_file):
        sys.exit(f"❌ لم يتم العثور على قناع العزل للفريم {f}")
    m = Image.open(m_file).convert("L").resize(im.size)
    rgba = im.convert("RGBA"); rgba.putalpha(m)
    al = np.asarray(m)
    rows_idx = np.where(al.max(1) > 40)[0]
    cols_idx = np.where(al.max(0) > 40)[0]
    if len(rows_idx) == 0 or len(cols_idx) == 0:
        c0, r0, c1, r1 = 0, 0, im.width, im.height
        rgba.save(out)
    else:
        c0, r0, c1, r1 = cols_idx[0], rows_idx[0], cols_idx[-1] + 1, rows_idx[-1] + 1
        rgba.crop((c0, r0, c1, r1)).save(out)
    fc = next(r["face"] for r in meta if r["f"] == f)   # مكان الوجه بالصورة المقصوصة — الثمبنيل يقص الراس والكتوف منه
    with open(out + ".face.json", "w", encoding="utf-8") as ff:
        json.dump({"x": fc["x"] - c0, "y": fc["y"] - r0, "w": fc["w"], "h": fc["h"]}, ff, ensure_ascii=False, indent=2)
    shutil.rmtree(tmp, ignore_errors=True)
    return times[i]


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 3: print(__doc__); sys.exit(1)
    t = float(a[a.index("--t") + 1]) if "--t" in a else -1.0
    n = int(a[a.index("--n") + 1]) if "--n" in a else 12
    print(f"→ {a[2]} (الثانية {cutout(a[1], a[2], t, n):.2f})")
