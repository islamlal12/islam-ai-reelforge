# -*- coding: utf-8 -*-
"""يبني توقيتات الكابشن الذكية والمتوسطة الحجم على التايم-لاين الجديد.
python3 02_captions.py <workdir> [--no-chunk]
- يتأكد تلقائياً من وجود a_clean.wav واستخدامه حصراً لتفريغ وِسبر بدلاً من الصوت الخام المشوش.
- يقرأ: cut.json · a.json (وِسبر) · fixes.json
- يمرر التدقيق اللغوي ومطابقة اللهجات (02d_caption_linguistics.py): تصحيح أخطاء وِسبر، الهمزات، والتاء المربوطة والمصطلحات التقنية.
- يُقسّم الكابشن إلى دفعات ذكية سريعة (1-3 كلمات فقط) بحجم خط متوسط-مضغوط (42px - 50px) داخل المنطقة الآمنة Y=1320-1420px وبلا أي فرفشة.
"""
# ── توافق ويندوز/UTF-8 مع دعم BOM التلقائي ─────────────────────────
import sys as _sys, builtins as _bi
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
_real_open = _bi.open
def _utf8_open(f, mode="r", *a, **k):
    if "b" not in mode:
        if "w" in mode or "a" in mode:
            k.setdefault("encoding", "utf-8")
        else:
            k.setdefault("encoding", "utf-8-sig")
    return _real_open(f, mode, *a, **k)
_bi.open = _utf8_open
# ──────────────────────────────────────────────────────────────────
import json, sys, os, subprocess, importlib.util

if len(sys.argv) < 2:
    print("Usage: python 02_captions.py <workdir> [--no-chunk]")
    sys.exit(1)

W = os.path.abspath(sys.argv[1])
NO_CHUNK = "--no-chunk" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))

# استيراد وحدة التدقيق اللغوي وضبط التوقيتات
ling_path = os.path.join(HERE, "02d_caption_linguistics.py")
if os.path.isfile(ling_path):
    spec = importlib.util.spec_from_file_location("caption_linguistics", ling_path)
    ling = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ling)
else:
    ling = None

# ── كشف الصوت النظيف المحسّن (Mandatory Clean Audio Detection) ──────
clean_cands = [os.path.join(W, "a_clean.wav"), os.path.join(W, "audio_clean.wav")]
clean_audio = next((p for p in clean_cands if os.path.isfile(p)), None)

if clean_audio:
    print(f"🎙️ [02_captions] Clean audio verified: {os.path.basename(clean_audio)} (Default for Whisper transcription & captions).")
else:
    print("⚠️ [02_captions] a_clean.wav not found. Checking if pre-whisper speech enhancement is needed...")

# ── التأكد من وجود التفريغ وخطة القص (Auto-resolve Prerequisites) ───
cut_path = os.path.join(W, "cut.json")
a_json_path = os.path.join(W, "a.json")
fixes_path = os.path.join(W, "fixes.json")

# 1. لو التفريغ مو موجود: نشغل التفريغ بالصوت النظيف a_clean.wav حصراً
if not os.path.isfile(a_json_path):
    print("🎙️ [02_captions] a.json not found. Initiating Whisper transcription with clean audio...")
    if not clean_audio:
        denoise_script = os.path.join(HERE, "02c_denoise.py")
        if os.path.isfile(denoise_script):
            print("🧹 Generating mandatory a_clean.wav via DeepFilterNet 3...")
            try:
                spec_d = importlib.util.spec_from_file_location("denoise_mod", denoise_script)
                mod_d = importlib.util.module_from_spec(spec_d)
                spec_d.loader.exec_module(mod_d)
                clean_audio = mod_d.prepare_clean_audio_for_whisper(W)
            except Exception as ex:
                print(f"⚠️ Denoise function call failed ({ex}). Running CLI...")
                subprocess.run([sys.executable, denoise_script, W], check=False)
                clean_audio = os.path.join(W, "a_clean.wav")
                
    transcribe_script = os.path.join(HERE, "01b_transcribe.py")
    if os.path.isfile(transcribe_script):
        cmd = [sys.executable, transcribe_script, W]
        if clean_audio and os.path.isfile(clean_audio):
            cmd.extend(["--audio", clean_audio])
        subprocess.run(cmd, check=True)
    else:
        sys.exit(f"❌ ما لقيت سكربت التفريغ {transcribe_script}")

# 2. لو cut.json مو موجود: نشغل 01_cut_plan.py
if not os.path.isfile(cut_path):
    cut_script = os.path.join(HERE, "01_cut_plan.py")
    if os.path.isfile(cut_script):
        print("✂️ [02_captions] cut.json not found. Running 01_cut_plan.py...")
        subprocess.run([sys.executable, cut_script, W], check=True)
    else:
        sys.exit(f"❌ ما لقيت cut.json ولا سكربت القص {cut_script}")

# 3. لو fixes.json مو موجود: نبني واحد أولي من a.json
if not os.path.isfile(fixes_path) and os.path.isfile(a_json_path):
    tr_temp = json.load(open(a_json_path))
    fx_temp = {
        "fix": [[w.get("word", "").strip() for w in seg.get("words", [])] for seg in tr_temp.get("segments", [])],
        "hot": [],
        "fx": {}
    }
    json.dump(fx_temp, open(fixes_path, "w"), ensure_ascii=False, indent=2)
    print("✨ [02_captions] Auto-generated baseline fixes.json")

# ── بناء الكروت والتوقيتات ──────────────────────────────────────────
keep = json.load(open(cut_path))["keep"]
tr = json.load(open(a_json_path))
fx = json.load(open(fixes_path))
FIX, HOT = fx["fix"], set(fx.get("hot", []))
FXMAP = fx.get("fx", {})   # 🎬 حركات الكلمة العربية

# تحميل القاموس المخصص من fixes.json والمراجع
custom_lexicon = ling.load_lexicon(W) if ling else {}

def seg_of(t):
    best, bd = 0, 1e9
    for i, (a, b) in enumerate(keep):
        if a <= t <= b: return i
        d = min(abs(t - a), abs(t - b))
        if d < bd: bd, best = d, i
    return best

off = []; acc = 0.0
for a, b in keep: off.append(acc); acc += b - a
def newt(t, si):
    a, b = keep[si]; return off[si] + (max(a, min(b, t)) - a)

# التدقيق اللغوي وبناء بطاقات الكابشن
raw_cards = []
normalized_count = 0

for i, seg in enumerate(tr["segments"]):
    ws = seg.get("words", [])
    if i >= len(FIX):
        f = [w.get("word", "").strip() for w in ws]
    else:
        f = FIX[i]
    if not ws: continue

    pin = isinstance(seg.get("seg"), int)
    si = seg["seg"] if pin else seg_of((ws[0]["start"] + ws[-1]["end"]) / 2)

    if isinstance(f, str):
        # نص بديل للجملة مع تطبيع الكلمات لغوياً
        if ling:
            f = ling.normalize_sentence(f, custom_lexicon)
        toks = f.split()
        s0, e0 = ws[0]["start"], ws[-1]["end"]
        tot = sum(len(t) for t in toks) or 1
        c = 0; pairs = []
        for t in toks:
            a0 = s0 + (e0 - s0) * c / tot
            c += len(t)
            pairs.append((t, a0, s0 + (e0 - s0) * c / tot))
    else:
        if len(ws) != len(f):
            sys.exit(f"❌ الجملة {i}: وِسبر {len(ws)} كلمة، fixes.json {len(f)} — لازم يتساوون (أو اكتبها نص وحدة إذا وِسبر هلوس)")
        # فحص وتطبيع الكلمات لغوياً
        norm_f = []
        for raw_w in f:
            if not raw_w:
                norm_f.append("")
                continue
            norm_w = ling.normalize_word(raw_w, custom_lexicon) if ling else raw_w
            if norm_w != raw_w:
                normalized_count += 1
            norm_f.append(norm_w)
        pairs = [(txt, w["start"], w["end"]) for w, txt in zip(ws, norm_f) if txt]

    if not pairs: continue
    o = []
    for txt, ws0, we0 in pairs:
        if pin: s1, e1 = newt(ws0, si), newt(we0, si)
        else:
            sw = seg_of(ws0); s1, e1 = newt(ws0, sw), newt(we0, max(sw, seg_of(we0)))
        if e1 <= s1: e1 = s1 + 0.12
        _w = {"t": txt, "s": round(s1, 3), "e": round(e1, 3), "hot": txt in HOT or txt in FXMAP}
        if txt in FXMAP: _w["fx"] = FXMAP[txt]
        o.append(_w)

    # فحص سلامة التوقيتات ومنع الفرفشة والتداخل
    if ling:
        o = ling.verify_timestamps(o)

    a, b = keep[si]; lo, hi = (off[si], off[si] + (b - a)) if pin else (0.0, acc)
    cs = max(o[0]["s"] - 0.08, lo)
    ce = min(max(x["e"] for x in o) + 0.22, hi)
    raw_cards.append({"s": round(cs, 3), "e": round(ce, 3), "w": o, "seg": i})

# تحويل البطاقات إلى دفعات ذكية سريعة (1-3 كلمات) مع تحديد الحجم الذكي (42-50px)
cards = []
if NO_CHUNK or not ling:
    cards = raw_cards
    for c in cards:
        fs = ling.compute_smart_font_size(len(c["w"])) if ling else 44
        c["fontSize"] = fs
        c["lineHeight"] = int(round(fs * 1.32))
        c["safeY"] = 1370
else:
    cards = ling.build_smart_cards(raw_cards, keep_ranges=keep, acc_duration=acc)

cards.sort(key=lambda c: c["s"])
for i in range(len(cards) - 1):
    if cards[i]["e"] > cards[i+1]["s"]:
        cards[i]["e"] = round(cards[i+1]["s"] - 0.02, 3)

_tail = float(json.load(open(cut_path)).get("tail", 0) or 0)
output_payload = {
    "total": round(acc + _tail, 3),
    "style": {
        "fontSizeRange": [42, 50],
        "fontDefault": "Readex Pro",
        "accentColor": "#F97316",
        "safeAreaY": [1320, 1420],
        "activeBoxRadius": 8,
        "zeroJitter": True
    },
    "cards": cards
}

json.dump(output_payload, open(os.path.join(W, "caps.json"), "w"), ensure_ascii=False, indent=1)

print(f"✨ تم التدقيق اللغوي: {normalized_count} كلمة مصححة ومطابقة للهجة.")
print(f"💬 تم بناء كروت الكابشن الذكية: {len(cards)} كرت (الحجم: 42-50px، داخل المنطقة الآمنة Y=1320-1420) — المدة: {round(acc, 2)} ثانية")
for c in cards[:8]:
    w_txt = " ".join(x['t'] for x in c['w'])
    fs = c.get('fontSize', 44)
    print(f"  [{c['s']:6.2f}-{c['e']:6.2f}] ({fs}px) {w_txt}")
if len(cards) > 8:
    print(f"  ... و {len(cards) - 8} كرت إضافي.")
