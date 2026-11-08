# -*- coding: utf-8 -*-
"""شيل أي جملة أو تكرار من الفيديو بحذفها من النص أو الفحص التلقائي.

    python 10_script_edit.py <work> show              # يطبع الجُمل مرقّمة (وينبّه للجُمل والتكرارات المعادة)
    python 10_script_edit.py <work> dupes             # الجُمل المعادة والتأتأة وحدها
    python 10_script_edit.py <work> dedup             # فحص شامل للتكرارات والتأتأة والبدايات المتعثرة
    python 10_script_edit.py <work> dedup --apply     # حذف التكرارات والتأتأة واختيار أفضل محاولة تلقائياً
    python 10_script_edit.py <work> drop 3 7 12       # يشيل هالجُمل المحددة من الفيديو
    python 10_script_edit.py <work> keep 1 2 5 6      # يبقي هذي بس ويشيل الباقي
    python 10_script_edit.py <work> apply             # يقرأ script.txt المعدّل ويشيل الناقص منه
    python 10_script_edit.py <work> undo              # يرجّع آخر تعديل
    (أضف --dry لأي أمر: يوريك النتيجة بلا ما يغيّر شي)

يدعم أيضاً الترتيب: python 10_script_edit.py dedup <work> [--apply]

الفكرة: الجملة أو التأتأة التي تنحذف من النص ينحذف مقطعها من الفيديو والصوت، وكل اللي بعدها ينزاح لمكانه.
يعدّل: cut.json (مقاطع الفيديو) · caps.json (الكابشن) · sfx.json (أوقات المؤثرات) · script.txt.
بعده: أعد بناء الفيديو ← 03_cut_zoom.py ثم استخراج الفريمات ثم الرسم.
"""
# ── توافق ويندوز/UTF-8 (مضاف) ─────────────────────────────────────
import sys as _sys, builtins as _bi
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
# ──────────────────────────────────────────────────────────────────
import json, os, sys, shutil, importlib

# استيراد محرك إزالة التكرارات المتخصص
here_dir = os.path.dirname(os.path.abspath(__file__))
if here_dir not in sys.path:
    sys.path.insert(0, here_dir)
try:
    dedup_engine = importlib.import_module("01b_dedup")
except Exception:
    dedup_engine = None

# معالجة وسائط سطر الأوامر بمرونة (يدعم <cmd> <work> و <work> <cmd>)
if "--help" in sys.argv or "-h" in sys.argv or len(sys.argv) == 1:
    print(__doc__)
    sys.exit(0)

VALID_CMDS = {"show", "dupes", "dedup", "drop", "keep", "apply", "undo"}
raw_args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = [a for a in sys.argv[1:] if a.startswith("--")]
DRY = "--dry" in flags
APPLY_FLAG = "--apply" in flags

if raw_args and raw_args[0].lower() in VALID_CMDS:
    CMD = raw_args[0].lower()
    W = os.path.abspath(raw_args[1]) if len(raw_args) > 1 else os.path.abspath(".")
    ARGS = raw_args[2:]
else:
    W = os.path.abspath(raw_args[0]) if len(raw_args) > 0 else os.path.abspath(".")
    CMD = raw_args[1].lower() if len(raw_args) > 1 else "show"
    ARGS = raw_args[2:]

P = lambda n: os.path.join(W, n)
PAD_L, PAD_R, MIN_SEG = 0.08, 0.12, 0.20

def load(n): return json.load(open(P(n), encoding="utf-8"))
def save(n, d):
    if DRY: return
    if os.path.exists(P(n)):
        if not os.path.exists(P(n + ".orig")): shutil.copy(P(n), P(n + ".orig"))
        shutil.copy(P(n), P(n + ".bak"))
    json.dump(d, open(P(n), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ── كشف الجملة المعادة (محدث بالمحرك الجديد) ──────────────────────────────
def find_dupes_legacy(cards, win=2, th=0.60):
    if dedup_engine:
        intervals, _ = dedup_engine.detect_all_speech_repetitions(cards, similarity_th=th)
        retakes = [iv for iv in intervals if iv.category == "sentence_retake"]
        out = []
        for iv in retakes:
            # مطابقة أرقام الكروت
            card_list = sorted(list(iv.card_indices))
            if len(card_list) >= 1:
                c_idx = card_list[0]
                # إيجاد الكرت المقابل
                for j in range(c_idx + 1, min(c_idx + 1 + win + 1, len(cards))):
                    out.append((c_idx, j, 0.85))
                    break
        if out: return out

    # الاحتياطي التقليدي
    import re as _re, difflib
    _STOP = {"في","من","على","الى","إلى","عن","مع","هذا","هذي","هذه","ذلك","اللي","الي",
             "و","او","أو","ثم","بس","يا","ان","أن","إن","ما","لا","كل","كان","صار","هو","هي"}
    def _norm(w):
        w = _re.sub(r"[\u064B-\u0652\u0640]", "", w)
        w = w.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ة","ه").replace("ى","ي")
        if len(w) > 4 and w.startswith("ال"): w = w[2:]
        return w
    def _words(c): return [_norm(x["t"]) for x in c["w"]]
    def _sim(a, b):
        wa, wb = [w for w in a if w not in _STOP], [w for w in b if w not in _STOP]
        if not wa or not wb: return 0.0
        shared = len(set(wa) & set(wb)) / min(len(wa), len(wb))
        chars  = difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
        return max(shared, chars)
    out = []
    for i in range(len(cards) - 1):
        for j in range(i + 1, min(i + 1 + win, len(cards))):
            r = _sim(_words(cards[i]), _words(cards[j]))
            if r >= th: out.append((i, j, r)); break
    return out

if not os.path.exists(P("caps.json")):
    sys.exit(f"❌ لم يتم العثور على {P('caps.json')} — شغل خطوات التفريغ والتقطيع أولاً.")

caps = load("caps.json"); cards = caps.get("cards", [])
def line(i, c):
    txt = " ".join(w["t"] for w in c.get("w", []))
    return f"{i+1:>3}  [{int(c['s']//60):02d}:{c['s']%60:05.2f}]  {txt}"


# ── dedup: المحرك الذكي المتخصص ──────────────────────────────────────────
if CMD == "dedup":
    if not dedup_engine:
        sys.exit("❌ تعذر تحميل موديول scripts/01b_dedup.py")
    
    intervals, dropped_tokens = dedup_engine.detect_all_speech_repetitions(cards)
    print("=" * 72)
    print("🎙️ فحص التكرارات والبدايات المتعثرة واختيار أفضل تيك (Smart Dedup Engine)")
    print(f"📁 المجلد: {W}")
    print(f"⏱️ المدة الحالية: {caps['total']:.2f} ثانية · {len(cards)} كرت")
    print("=" * 72)

    if not intervals:
        print("\n✅ رائع! لم يتم رصد أي تكرارات أو تأتأة أو بدايات متعثرة.")
        sys.exit(0)

    print(f"\n🔍 تم رصد {len(intervals)} عثرة/تكرار:")
    tot_time = sum(iv.end - iv.start for iv in intervals)
    for idx, iv in enumerate(intervals, 1):
        cat_badge = {
            "sentence_retake": "🔁 [إعادة تيك]",
            "restart_pattern": "🛑 [بداية متعثرة واستئناف]",
            "ngram_stutter_1": "⚡ [تأتأة كلمة واحدة]",
            "ngram_stutter_2": "⚡ [تأتأة كلمتين]",
            "ngram_stutter_3": "⚡ [تأتأة 3 كلمات]"
        }.get(iv.category, "✂️ [تكرار]")
        print(f"\n{idx}. {cat_badge} [{iv.start:05.2f}ث ──> {iv.end:05.2f}ث] ({iv.end - iv.start:.2f}ث)")
        print(f"   السبب   : {iv.reason}")
        print(f"   ❌ يُحذف : \"{iv.discard_text}\"")
        print(f"   ✅ يُعتمد: \"{iv.keep_text}\"")
        if iv.score_diff:
            print(f"   📊 الميزان: {iv.score_diff}")

    print("\n" + "-" * 72)
    print(f"📉 إجمالي الوقت الموفر: {tot_time:.2f} ثانية ({(tot_time / max(0.1, caps['total']))*100:.1f}٪ اختصار)")

    if APPLY_FLAG:
        stats = dedup_engine.apply_deduplication(W, intervals, dropped_tokens, dry_run=DRY)
        print("\n🚀 تم تطبيق الحذف وتنقيح التايم لاين بنجاح:")
        print(f"   - المدة الجديدة: {stats['new_total']:.2f} ثانية (انحذف {stats['seconds_removed']:.2f} ثانية)")
        print(f"   - الكلمات المحذوفة: {stats['words_dropped']} كلمة")
        print(f"   - الكروت المزالة: {stats['cards_dropped']} كرت")
        print("\n🎬 أعد بناء الفيديو:")
        print(f"   python scripts/03_cut_zoom.py {W}")
        print(f"   mkdir -p {W}/vfr && ffmpeg -v error -i {W}/cutz.mp4 -vf fps=30 -q:v 3 -y {W}/vfr/%05d.jpg")
        print(f"   node scripts/04_render_frames.js {W} all --force")
        print(f"↩️ للتراجع: python scripts/10_script_edit.py {W} undo")
    else:
        print("\n💡 للتطبيق التلقائي وقص هذه التكرارات:")
        print(f"   python scripts/10_script_edit.py {W} dedup --apply")
        print(f"   أو: python scripts/01b_dedup.py {W} --apply")
    sys.exit(0)


# ── show ──────────────────────────────────────────────────────────────────
if CMD == "show":
    body = ("# احذف أي سطر ما تبيه بالفيديو، واحفظ الملف، ثم:  python 10_script_edit.py <work> apply\n"
            "# (لا تغيّر الأرقام — هي اللي تربط السطر بمقطعه)\n\n"
            + "\n".join(line(i, c) for i, c in enumerate(cards)) + "\n")
    if not DRY: open(P("script.txt"), "w", encoding="utf-8").write(body)
    print(body)
    print(f"المدة الحالية: {caps['total']:.2f} ثانية · {len(cards)} جملة")
    
    if dedup_engine:
        ivs, _ = dedup_engine.detect_all_speech_repetitions(cards)
        if ivs:
            print("\n🔁 تنبيه: تم رصد عثرات وتكرارات في التسجيل العفوي:")
            for iv in ivs[:5]:
                print(f"   - [{iv.category}]: حذف \"{iv.discard_text}\" ← إبقاء \"{iv.keep_text}\"")
            if len(ivs) > 5:
                print(f"   ... و {len(ivs) - 5} تكرارات أخرى.")
            print(f"   ⚡ لحذفها وتصحيح التايم لاين تلقائياً:  python scripts/10_script_edit.py {W} dedup --apply")
    else:
        d = find_dupes_legacy(cards)
        if d:
            print("\n🔁 جُمل يبدو إنك أعدتها — والغالب إن الأولى هي الغلط:")
            for i, j, r in d:
                print(f"   {i+1} ← {j+1}  (تشابه {r*100:.0f}٪)")
                print(f"      {i+1}: " + " ".join(w['t'] for w in cards[i]['w']))
                print(f"      {j+1}: " + " ".join(w['t'] for w in cards[j]['w']))
            print("   الاقتراح: drop " + " ".join(str(i+1) for i,_,_ in d) + "   (اعرضه على المستخدم قبل التنفيذ)")
    sys.exit(0)

if CMD == "dupes":
    if dedup_engine:
        ivs, _ = dedup_engine.detect_all_speech_repetitions(cards)
        if not ivs:
            print("ما فيه جملة معادة أو تأتأة."); sys.exit(0)
        print("🔍 التكرارات والتأتأة المرصودة:")
        for idx, iv in enumerate(ivs, 1):
            print(f"{idx}. [{iv.category}] {iv.start:.2f}s -> {iv.end:.2f}s: \"{iv.discard_text}\" ← \"{iv.keep_text}\"")
        print(f"\nلحذف كافة التكرارات تلقائياً:  python scripts/10_script_edit.py {W} dedup --apply")
    else:
        d = find_dupes_legacy(cards)
        if not d: print("ما فيه جملة معادة."); sys.exit(0)
        for i, j, r in d:
            print(f"{i+1} ← {j+1}  (تشابه {r*100:.0f}٪)")
            print(f"   {i+1}: " + " ".join(w['t'] for w in cards[i]['w']))
            print(f"   {j+1}: " + " ".join(w['t'] for w in cards[j]['w']))
        print("\nلحذف الأولى من كل زوج:  drop " + " ".join(str(i+1) for i,_,_ in d))
    sys.exit(0)

if CMD == "undo":
    n = 0
    for f in ("cut.json", "caps.json", "sfx.json", "script.txt"):
        if os.path.exists(P(f + ".bak")): shutil.copy(P(f + ".bak"), P(f)); n += 1
    print(f"↩️ رجّعت {n} ملفاً لآخر نسخة." if n else "ما فيه نسخة سابقة.")
    sys.exit(0)

# ── أي جُمل تنشال؟ ────────────────────────────────────────────────────────
if CMD == "drop":
    drop = {int(a) - 1 for a in ARGS}
elif CMD == "keep":
    keep_i = {int(a) - 1 for a in ARGS}
    drop = {i for i in range(len(cards)) if i not in keep_i}
elif CMD == "apply":
    if not os.path.exists(P("script.txt")): sys.exit("❌ ما فيه script.txt — شغّل show أول")
    alive = set()
    for ln in open(P("script.txt"), encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        head = ln.split(None, 1)[0]
        if head.isdigit(): alive.add(int(head) - 1)
    drop = {i for i in range(len(cards)) if i not in alive}
else:
    sys.exit("الأوامر: show · dupes · dedup · drop · keep · apply · undo")

drop = {i for i in drop if 0 <= i < len(cards)}
if not drop: sys.exit("ما فيه جملة تنشال — بلا تغيير.")
if len(drop) == len(cards): sys.exit("❌ هذا يشيل الفيديو كله — ألغيت.")

# ── فترات الحذف على التايم-لاين الحالي ────────────────────────────────────
iv = []
for i in sorted(drop):
    c = cards[i]
    a = max(0.0, c["w"][0]["s"] - PAD_L)
    b = min(caps["total"], c["w"][-1]["e"] + PAD_R)
    if i + 1 < len(cards):                       # لا تاكل بداية الجملة اللي بعدها
        b = min(b, cards[i + 1]["w"][0]["s"] - 0.02)
    if b > a: iv.append([a, b])
iv.sort(); merged = []
for a, b in iv:
    if merged and a - merged[-1][1] < 0.05: merged[-1][1] = max(merged[-1][1], b)
    else: merged.append([a, b])
gone = sum(b - a for a, b in merged)

def shift(t):                                    # وقت جديد بعد الحذف
    return t - sum(min(t, b) - a for a, b in merged if a < t)
def inside(t):
    return any(a - 1e-6 <= t <= b + 1e-6 for a, b in merged)

print("راح ينشال:")
for i in sorted(drop): print("  ✂️ " + line(i, cards[i]).strip())
print(f"المدة: {caps['total']:.2f} → {caps['total']-gone:.2f} ثانية (‎-{gone:.2f})")
if DRY: sys.exit(0)

# ── 1) cut.json: نقل فترات الحذف لزمن الفيديو الأصلي ─────────────────────
cut = load("cut.json"); keep = [list(x) for x in cut["keep"]]
off, acc = [], 0.0
for a, b in keep: off.append(acc); acc += b - a
src_del = []
for ds, de in merged:
    for i, (a, b) in enumerate(keep):
        s0, s1 = off[i], off[i] + (b - a)
        lo, hi = max(ds, s0), min(de, s1)
        if hi > lo: src_del.append([a + (lo - s0), a + (hi - s0)])
new_keep = []
for a, b in keep:
    parts = [[a, b]]
    for ds, de in src_del:
        out = []
        for x, y in parts:
            if de <= x or ds >= y: out.append([x, y]); continue
            if ds > x: out.append([x, ds])
            if de < y: out.append([de, y])
        parts = out
    new_keep += [p for p in parts if p[1] - p[0] >= MIN_SEG]
cut["keep"] = new_keep
cut["total"] = round(sum(b - a for a, b in new_keep), 3)
save("cut.json", cut)

# ── 2) caps.json: شيل الجُمل وازحف الباقي ────────────────────────────────
new_cards = []
for i, c in enumerate(cards):
    if i in drop: continue
    ws = [{**w, "s": round(shift(w["s"]), 3), "e": round(shift(w["e"]), 3)} for w in c["w"]]
    new_cards.append({"s": round(shift(c["s"]), 3), "e": round(shift(c["e"]), 3), "w": ws})
for i in range(len(new_cards) - 1):              # لا تتداخل الكروت بعد الزحف
    if new_cards[i]["e"] > new_cards[i + 1]["s"]:
        new_cards[i]["e"] = round(new_cards[i + 1]["s"] - 0.02, 3)
new_total = round(min(caps["total"] - gone, cut["total"] + float(cut.get("tail",0) or 0)), 3)
save("caps.json", {"total": new_total, "cards": new_cards})

# ── 3) sfx.json: أوقات المؤثرات ──────────────────────────────────────────
if os.path.exists(P("sfx.json")):
    sfx = load("sfx.json"); moved = 0; killed = 0
    for k, v in list(sfx.items()):
        if not isinstance(v, list): continue
        out = []
        for t in v:
            if inside(t): killed += 1
            else: out.append(round(shift(t), 3)); moved += 1
        sfx[k] = out
    save("sfx.json", sfx)
    print(f"المؤثرات: {moved} انزاحت · {killed} انشالت")

print(f"""
✅ تم. الحين أعد بناء الفيديو:
   python scripts/03_cut_zoom.py {W}
   mkdir -p {W}/vfr && ffmpeg -v error -i {W}/cutz.mp4 -vf fps=30 -q:v 3 -y {W}/vfr/%05d.jpg
   node scripts/04_render_frames.js {W} all --force     (أو 04b_remotion.sh {W} render)
⚠️ لو كنت مصمّماً مشاهد بأوقات ثابتة — أوقاتها انزاحت، راجعها.
↩️ للتراجع: python scripts/10_script_edit.py {W} undo""")
