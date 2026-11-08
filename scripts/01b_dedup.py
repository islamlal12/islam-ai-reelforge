# -*- coding: utf-8 -*-
"""كشف وحذف التكرار والتأتأة والبدايات المتعثرة واختيار أفضل محاولة (Master Take)
للفيديو والكلام العفوي (Unscripted Speech Deduplication Engine).

الاستخدام:
    python scripts/01b_dedup.py <work_dir>                 # فحص وعرض التكرارات والوقفات المتعثرة
    python scripts/01b_dedup.py <work_dir> --apply         # تطبيق الحذف وتعديل cut.json و caps.json و sfx.json
    python scripts/01b_dedup.py <work_dir> --dry           # محاكاة التعديل دون لمس الملفات
    python scripts/01b_dedup.py <work_dir> --json          # تقرير مفصّل بصيغة JSON للأدوات والوكلاء
    python scripts/01b_dedup.py <work_dir> --undo          # التراجع عن آخر تعديل واستعادة النسخة الاحتياطية

يحل ثلاث حالات رئيسية للكلام العفوي:
1. التأتأة والتكرار المتتالي (1-gram, 2-gram, 3-gram stutters) مثل: "هذا هذا"، "علشان كذا علشان كذا".
2. البدايات المتعثرة وإعادة الاستئناف (Restart Patterns / False Starts) مثل: "أنا اليوم... [وقفة] أنا اليوم جاي أحكيلكم".
3. إعادة الجُمل والتيكات (Sentence / Take Retakes) مثل إعادة صياغة جملة كاملة بنبرة أفضل أو كلمات أوضح،
   مع تفضيل التيك الأخير الأوضح (Final Take Preference) وحساب لحمات قص ناعمة (5-10ms Micro-margin).
"""
# ── توافق ويندوز وUTF-8 ───────────────────────────────────────────────────
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
# ──────────────────────────────────────────────────────────────────────────

import json, os, sys, shutil, re, difflib, argparse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Set

# هوامش ولحمات القص الناعمة (Acoustic Margins & Micro-crossfade)
MICRO_MARGIN = 0.008       # 8ms ميكرو-كروس فيد لمنع الطقطقة الصوتية (Clicks/Pops)
PAD_ATTACK = 0.035         # 35ms قبل الكلمة المبقاة لحماية طاقة الهجوم الصوتي الأولى (Frame Attack F0)
PAD_RELEASE = 0.040        # 40ms بعد الكلمة السابقة لمنع بتر الحروف الساكنة
MIN_SEG_SRC = 0.150        # أقل مدة مقطع مقبول بـ cut.json لمنع الرمشات الصورية

STOP_WORDS = {
    "في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "هذي", "هذه", "ذلك", "اللي", "الي",
    "و", "او", "أو", "ثم", "بس", "يا", "ان", "أن", "إن", "ما", "لا", "كل", "كان", "صار", "هو", "هي"
}

# ── المعالجة اللغوية للنص العربي العفوي ──────────────────────────────────────
def normalize_arabic(text: str, strip_prefixes: bool = False) -> str:
    """معالجة وتجريد النص العربي العفوي:
    - إزالة التشكيل والتطويل والأقواس وعلامات الترقيم
    - توحيد الألفات (أ، إ، آ، ٱ -> ا)، التاء المربوطة (ة -> ه)، الياء (ى -> ي)
    - تجريد السوابق العفوية واللهجية (و، ف، ال، هال، بال، فال) للمقارنة الدلالية
    """
    if not text:
        return ""
    # 1. إزالة الحركات والتطويل والعلامات
    s = re.sub(r'[\u064B-\u0652\u0640\u0670]', '', text)
    # 2. إزالة علامات الترقيم والأقواس
    s = re.sub(r'[^\w\s]', '', s)
    # 3. توحيد الألفات والهمزات والتاء والياء
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ٱ', 'ا')
    s = s.replace('ة', 'ه').replace('ى', 'ي').replace('ؤ', 'و').replace('ئ', 'ي')
    s = s.strip()

    if strip_prefixes:
        # تجريد السوابق اللهجية والموصولة مع حماية الجذور التي لا تقل عن 3 أحرف
        # سوابق 3 أحرف: "وال"، "فال"، "هال"، "بال"
        if len(s) >= 6 and (s.startswith("وال") or s.startswith("فال") or s.startswith("هال") or s.startswith("بال")):
            s = s[3:]
        # سوابق حرفين: "ال"، "لل"
        elif len(s) >= 5 and (s.startswith("ال") or s.startswith("لل")):
            s = s[2:]
        # سوابق حرف واحد: "و"، "ف"، "ب"، "ل"
        elif len(s) >= 4 and (s.startswith("و") or s.startswith("ف") or s.startswith("ب") or s.startswith("ل")):
            orig_roots = {"وفد", "وقت", "وجه", "وطن", "ولد", "وفاء", "فرع", "فصل", "فكر", "فهم", "باب", "بيت", "بلد", "لون", "لحم"}
            if s not in orig_roots:
                s = s[1:]
                if len(s) >= 5 and s.startswith("ال"):
                    s = s[2:]
    return s


@dataclass
class WordToken:
    idx: int                    # الفهرس التسلسلي العام
    card_idx: int               # رقم الجملة/الكرت
    word_in_card_idx: int       # رقم الكلمة داخل الكرت
    text: str                   # النص الأصلي
    norm: str                   # النص بعد التوحيد البسيط
    stem: str                   # النص بعد تجريد السوابق
    start: float                # وقت البداية بالثواني
    end: float                  # وقت النهاية بالثواني
    prob: float = 1.0           # درجة ثقة وِسبر (Whisper Confidence)


@dataclass
class DropInterval:
    start: float                # بداية فترة الحذف على التايم لاين
    end: float                  # نهاية فترة الحذف على التايم لاين
    token_indices: List[int]    # مؤشرات الكلمات المحذوفة
    card_indices: List[int]     # الكروت المتأثرة
    category: str               # تصنيف التكرار (stutter, restart, retake)
    reason: str                 # سبب الحذف
    discard_text: str           # النص المحذوف
    keep_text: str              # النص المعتمد (Master Take)
    score_diff: str = ""        # فارق النقاط بين المحاولتين


# ── قياس التشابه وتفضيل أفضل محاولة (Scoring Engine) ───────────────────────────
def words_similarity(tokens_a: List[WordToken], tokens_b: List[WordToken]) -> float:
    """حساب التشابه المعجمي والدلالي بين مجموعتين من الكلمات."""
    wa = [t.stem for t in tokens_a if t.stem not in STOP_WORDS]
    wb = [t.stem for t in tokens_b if t.stem not in STOP_WORDS]
    if not wa or not wb:
        wa = [t.stem for t in tokens_a]
        wb = [t.stem for t in tokens_b]
    if not wa or not wb:
        return 0.0
    shared = len(set(wa) & set(wb)) / min(len(wa), len(wb))
    seq = difflib.SequenceMatcher(None, [t.norm for t in tokens_a], [t.norm for t in tokens_b]).ratio()
    return max(shared, seq)


def score_candidate_take(tokens: List[WordToken], is_later: bool) -> Tuple[float, List[str]]:
    """تقييم جودة المحاولة المنطوقة لاختيار المحاولة الأفضل والأكثر طلاقة:
    - طول واكتمال الجملة (+1.5 لكل كلمة)
    - أفضلية الإعادة اللاحقة في التسجيل العفوي (+3.0 لأن المتحدث يعيد الجملة لتصحيح عثرة سابقة)
    - خصم الوقفات والترددات الداخلية (-2.0 لكل وقفة تتجاوز 0.35 ثانية)
    - متوسط ثقة نموذج وِسبر (+2.0 * confidence)
    """
    n = len(tokens)
    score = 0.0
    reasons = []

    # 1. اكتمال الجملة
    comp = n * 1.5
    score += comp
    reasons.append(f"+{comp:.1f} (اكتمال {n} كلمة)")

    # 2. أفضلية الإعادة اللاحقة (Final Take Priority)
    if is_later:
        score += 3.0
        reasons.append("+3.0 (الإعادة الأحدث والأكثر اعتماداً)")

    # 3. فحص الوقفات الداخلية والتردد
    internal_gaps = []
    for k in range(len(tokens) - 1):
        g = tokens[k + 1].start - tokens[k].end
        if g > 0.35:
            internal_gaps.append(g)
    if internal_gaps:
        penalty = len(internal_gaps) * 2.0
        score -= penalty
        reasons.append(f"-{penalty:.1f} ({len(internal_gaps)} وقفة تردد وتعثر داخلية)")

    # 4. ثقة نموذج وِسبر
    avg_prob = sum(t.prob for t in tokens) / max(1, n)
    prob_bonus = avg_prob * 2.0
    score += prob_bonus
    reasons.append(f"+{prob_bonus:.1f} (ثقة وِسبر {avg_prob*100:.0f}٪)")

    return score, reasons


# ── محرك كشف التكرارات الشامل ────────────────────────────────────────────────
def detect_all_speech_repetitions(
    cards_data: List[dict],
    similarity_th: float = 0.60,
    min_restart_gap: float = 0.20,
    max_ngram: int = 3
) -> Tuple[List[DropInterval], Set[int]]:
    """فحص واكتشاف كافة أنواع التكرارات في الكلام العفوي:
    1. إعادة الجمل/التيكات الكاملة بين الكروت المتقاربة.
    2. التأتأة والتكرار المباشر للكلمات والعبارات (1, 2, 3 n-grams).
    3. البدايات المتعثرة وإعادة الاستئناف (False Starts & Restarts).
    """
    tokens: List[WordToken] = []
    cards_words: List[List[WordToken]] = []
    g_idx = 0

    for c_idx, c in enumerate(cards_data):
        c_tokens = []
        for w_idx, w in enumerate(c.get("w", [])):
            raw = str(w.get("t", "")).strip()
            norm = normalize_arabic(raw, False)
            stem = normalize_arabic(raw, True)
            t = WordToken(
                idx=g_idx,
                card_idx=c_idx,
                word_in_card_idx=w_idx,
                text=raw,
                norm=norm,
                stem=stem,
                start=float(w.get("s", 0.0)),
                end=float(w.get("e", 0.0)),
                prob=float(w.get("prob", 1.0))
            )
            tokens.append(t)
            c_tokens.append(t)
            g_idx += 1
        cards_words.append(c_tokens)

    dropped_token_indices: Set[int] = set()
    drop_intervals: List[DropInterval] = []

    # ── 1) فحص تكرار الجمل والتيكات الكاملة (Cross-Card Retakes) ──────────────
    for i in range(len(cards_data) - 1):
        if not cards_words[i] or any(t.idx in dropped_token_indices for t in cards_words[i]):
            continue
        for j in range(i + 1, min(i + 4, len(cards_data))):
            if not cards_words[j] or any(t.idx in dropped_token_indices for t in cards_words[j]):
                continue

            sim = words_similarity(cards_words[i], cards_words[j])
            if sim >= similarity_th:
                s1, r1 = score_candidate_take(cards_words[i], is_later=False)
                s2, r2 = score_candidate_take(cards_words[j], is_later=True)

                if s2 >= s1:
                    drop_c_idx, keep_c_idx = i, j
                    drop_score, keep_score = s1, s2
                else:
                    drop_c_idx, keep_c_idx = j, i
                    drop_score, keep_score = s2, s1

                drop_toks = cards_words[drop_c_idx]
                keep_toks = cards_words[keep_c_idx]

                for dt in drop_toks:
                    dropped_token_indices.add(dt.idx)

                txt_drop = " ".join(t.text for t in drop_toks)
                txt_keep = " ".join(t.text for t in keep_toks)

                # حساب حدود القطع مع مراعاة الحواف
                t_start = max(0.0, drop_toks[0].start - PAD_RELEASE)
                t_end = drop_toks[-1].end + PAD_RELEASE

                drop_intervals.append(DropInterval(
                    start=round(t_start, 3),
                    end=round(t_end, 3),
                    token_indices=[t.idx for t in drop_toks],
                    card_indices=[drop_c_idx],
                    category="sentence_retake",
                    reason=f"إعادة صياغة جملة كاملة (تشابه {sim*100:.0f}٪)",
                    discard_text=txt_drop,
                    keep_text=txt_keep,
                    score_diff=f"سكور: {keep_score:.1f} للمعتمدة مقابل {drop_score:.1f} للمحذوفة"
                ))

    # ── 2) فحص التأتأة والتكرار المباشر (N-gram Stutters) ─────────────────────
    i = 0
    while i < len(tokens):
        if i in dropped_token_indices:
            i += 1
            continue

        found_ngram = False
        for n in range(max_ngram, 0, -1):
            if i + 2 * n <= len(tokens):
                a_toks = tokens[i : i + n]
                b_toks = tokens[i + n : i + 2 * n]

                if any(t.idx in dropped_token_indices for t in a_toks + b_toks):
                    continue

                gap = b_toks[0].start - a_toks[-1].end
                if gap > 1.2:
                    continue

                match_norm = [t.norm for t in a_toks] == [t.norm for t in b_toks]
                match_stem = [t.stem for t in a_toks] == [t.stem for t in b_toks]

                if match_norm or match_stem:
                    # تكرار تأتأة: حذف المحاولة الأولى وإبقاء الثانية
                    drop_slice = a_toks
                    for t in drop_slice:
                        dropped_token_indices.add(t.idx)

                    # حدود القص: حماية هجوم الكلمة التالية (Attack F0)
                    t_start = max(0.0, drop_slice[0].start - PAD_RELEASE)
                    t_end = max(t_start + MICRO_MARGIN, b_toks[0].start - PAD_ATTACK)

                    txt_drop = " ".join(t.text for t in drop_slice)
                    txt_keep = " ".join(t.text for t in b_toks)

                    drop_intervals.append(DropInterval(
                        start=round(t_start, 3),
                        end=round(t_end, 3),
                        token_indices=[t.idx for t in drop_slice],
                        card_indices=sorted(list({t.card_idx for t in drop_slice})),
                        category=f"ngram_stutter_{n}",
                        reason=f"تأتأة وتكرار متتالي ({n} كلمات مكررة)",
                        discard_text=txt_drop,
                        keep_text=txt_keep,
                        score_diff="حذف التأتأة الأولى تلقائياً"
                    ))
                    i += n
                    found_ngram = True
                    break
        if not found_ngram:
            i += 1

    # ── 3) فحص البدايات المتعثرة وإعادة الاستئناف (Restart Patterns) ───────────
    i = 0
    while i < len(tokens):
        if i in dropped_token_indices:
            i += 1
            continue

        found_restart = False
        # البحث في مدى يصل لـ 8 كلمات قادمة أو 5 ثوانٍ
        for j in range(i + 1, min(i + 8, len(tokens))):
            if j in dropped_token_indices:
                continue
            if tokens[j].start - tokens[i].end > 5.0:
                break

            # فحص تطابق الكلمات المبتدئة
            match_len = 0
            while (i + match_len < j and
                   j + match_len < len(tokens) and
                   (tokens[i + match_len].stem == tokens[j + match_len].stem or
                    tokens[i + match_len].norm == tokens[j + match_len].norm)):
                match_len += 1

            if match_len >= 1:
                false_start_toks = tokens[i : j]
                if any(t.idx in dropped_token_indices for t in false_start_toks):
                    continue

                pause_gap = tokens[j].start - false_start_toks[-1].end
                # شرط البداية المتعثرة: وقفة بعد الكلمة أو تطابق كلمتين فأكثر
                if pause_gap >= min_restart_gap or match_len >= 2:
                    for t in false_start_toks:
                        dropped_token_indices.add(t.idx)

                    t_start = max(0.0, false_start_toks[0].start - PAD_RELEASE)
                    t_end = max(t_start + MICRO_MARGIN, tokens[j].start - PAD_ATTACK)

                    txt_drop = " ".join(t.text for t in false_start_toks)
                    txt_keep = " ".join(t.text for t in tokens[j : j + match_len + 3])

                    drop_intervals.append(DropInterval(
                        start=round(t_start, 3),
                        end=round(t_end, 3),
                        token_indices=[t.idx for t in false_start_toks],
                        card_indices=sorted(list({t.card_idx for t in false_start_toks})),
                        category="restart_pattern",
                        reason=f"بداية متعثرة وإعادة استئناف (وقفة {pause_gap:.2f}ث)",
                        discard_text=txt_drop,
                        keep_text=txt_keep,
                        score_diff="حذف البداية الناقصة واستئناف الجملة الكاملة"
                    ))
                    i = j
                    found_restart = True
                    break
        if not found_restart:
            i += 1

    drop_intervals.sort(key=lambda x: x.start)
    return drop_intervals, dropped_token_indices


# ── إزاحة الزمن وتحديث الملفات ───────────────────────────────────────────────
def shift_timeline_time(t: float, merged_intervals: List[Tuple[float, float]]) -> float:
    """إزاحة زمن ت على التايم لاين الجديد بعد حذف الفترات المقصوصة."""
    shift = 0.0
    for a, b in merged_intervals:
        if t <= a:
            break
        elif t >= b:
            shift += (b - a)
        else:
            shift += (t - a)
            break
    return t - shift


def apply_deduplication(
    work_dir: str,
    intervals: List[DropInterval],
    dropped_tokens: Set[int],
    dry_run: bool = False
) -> Dict:
    """تطبيق الحذف المعتمد ومزامنة cut.json, caps.json, sfx.json, script.txt."""
    work_dir = os.path.abspath(work_dir)
    P = lambda n: os.path.join(work_dir, n)

    if not os.path.exists(P("caps.json")):
        raise FileNotFoundError(f"لم يتم العثور على {P('caps.json')}")

    caps = json.load(open(P("caps.json"), encoding="utf-8"))
    cut = json.load(open(P("cut.json"), encoding="utf-8")) if os.path.exists(P("cut.json")) else None

    # دمج الفترات المتداخلة أو المتلاصقة (أقل من 50ms)
    sorted_raw = sorted([(iv.start, iv.end) for iv in intervals], key=lambda x: x[0])
    merged: List[Tuple[float, float]] = []
    for a, b in sorted_raw:
        if merged and a - merged[-1][1] < 0.05:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))

    gone = sum(b - a for a, b in merged)

    # 1. تحديث caps.json
    new_cards = []
    g_idx = 0
    words_dropped_count = 0
    cards_dropped_count = 0

    for c_idx, card in enumerate(caps.get("cards", [])):
        kept_words = []
        for w_idx, w in enumerate(card.get("w", [])):
            w_mid = (float(w["s"]) + float(w["e"])) / 2.0
            in_cut = any(a <= w_mid <= b for a, b in merged) or (g_idx in dropped_tokens)
            if in_cut:
                words_dropped_count += 1
            else:
                ns = round(shift_timeline_time(float(w["s"]), merged), 3)
                ne = round(shift_timeline_time(float(w["e"]), merged), 3)
                if ne <= ns:
                    ne = round(ns + 0.10, 3)
                kept_words.append({**w, "s": ns, "e": ne})
            g_idx += 1

        if kept_words:
            cs = max(0.0, round(kept_words[0]["s"] - 0.08, 3))
            ce = round(kept_words[-1]["e"] + 0.20, 3)
            new_cards.append({"s": cs, "e": ce, "w": kept_words})
        else:
            cards_dropped_count += 1

    # منع تداخل الكروت بعد الإزاحة
    for i in range(len(new_cards) - 1):
        if new_cards[i]["e"] > new_cards[i + 1]["s"]:
            new_cards[i]["e"] = round(new_cards[i + 1]["s"] - 0.02, 3)

    # 2. تحديث cut.json (نقل فترات الحذف لأزمنة الفيديو الأصلي src.mov)
    new_cut_total = 0.0
    if cut:
        keep = [list(x) for x in cut.get("keep", [])]
        off, acc = [], 0.0
        for a, b in keep:
            off.append(acc)
            acc += (b - a)

        src_del = []
        for ds, de in merged:
            for i, (a, b) in enumerate(keep):
                s0, s1 = off[i], off[i] + (b - a)
                lo, hi = max(ds, s0), min(de, s1)
                if hi > lo:
                    src_del.append([a + (lo - s0), a + (hi - s0)])

        new_keep = []
        for a, b in keep:
            parts = [[a, b]]
            for ds, de in src_del:
                out = []
                for x, y in parts:
                    if de <= x or ds >= y:
                        out.append([x, y])
                        continue
                    if ds > x:
                        out.append([x, ds])
                    if de < y:
                        out.append([de, y])
                parts = out
            new_keep += [p for p in parts if (p[1] - p[0]) >= MIN_SEG_SRC]

        new_cut_total = round(sum(b - a for a, b in new_keep), 3)
        cut["keep"] = new_keep
        cut["total"] = new_cut_total

    new_caps_total = round(max(0.0, caps["total"] - gone), 3)
    if cut:
        tail = float(cut.get("tail", 0) or 0)
        new_caps_total = round(min(new_caps_total, new_cut_total + tail), 3)

    new_caps = {"total": new_caps_total, "cards": new_cards}

    # 3. تحديث sfx.json
    sfx_res = {"moved": 0, "killed": 0}
    sfx_path = P("sfx.json")
    new_sfx = None
    if os.path.exists(sfx_path):
        sfx = json.load(open(sfx_path, encoding="utf-8"))
        for k, v in list(sfx.items()):
            if not isinstance(v, list):
                continue
            out_times = []
            for t in v:
                if any(a - 1e-5 <= t <= b + 1e-5 for a, b in merged):
                    sfx_res["killed"] += 1
                else:
                    out_times.append(round(shift_timeline_time(t, merged), 3))
                    sfx_res["moved"] += 1
            sfx[k] = out_times
        new_sfx = sfx

    # 4. الحفظ وإنشاء النسخ الاحتياطية
    if not dry_run:
        for fname, data in [("caps.json", new_caps), ("cut.json", cut), ("sfx.json", new_sfx)]:
            if data is None or not os.path.exists(P(fname)):
                continue
            orig_p = P(fname + ".orig")
            bak_p = P(fname + ".bak")
            if not os.path.exists(orig_p):
                shutil.copy(P(fname), orig_p)
            shutil.copy(P(fname), bak_p)
            json.dump(data, open(P(fname), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

        # تحديث script.txt إن وجد
        body_lines = [
            "# السكربت المنقح بعد إزالة التكرار والتأتأة تلقائياً",
            "# للتعديل اليدوي: احذف أي سطر ثم شغّل: python scripts/10_script_edit.py <work> apply\n"
        ]
        for i, c in enumerate(new_cards):
            txt = " ".join(w["t"] for w in c["w"])
            body_lines.append(f"{i+1:>3}  [{int(c['s']//60):02d}:{c['s']%60:05.2f}]  {txt}")
        open(P("script.txt"), "w", encoding="utf-8").write("\n".join(body_lines) + "\n")

    return {
        "original_total": caps["total"],
        "new_total": new_caps_total,
        "seconds_removed": round(gone, 3),
        "percentage_removed": round((gone / max(0.1, caps["total"])) * 100, 1),
        "words_dropped": words_dropped_count,
        "cards_dropped": cards_dropped_count,
        "cut_intervals_count": len(merged),
        "sfx_moved": sfx_res["moved"],
        "sfx_killed": sfx_res["killed"]
    }


def undo_deduplication(work_dir: str) -> bool:
    """استرجاع آخر نسخة احتياطية سابقة من ملفات التقطيع."""
    work_dir = os.path.abspath(work_dir)
    P = lambda n: os.path.join(work_dir, n)
    reverted = 0
    for f in ("cut.json", "caps.json", "sfx.json", "script.txt"):
        if os.path.exists(P(f + ".bak")):
            shutil.copy(P(f + ".bak"), P(f))
            reverted += 1
    return reverted > 0


# ── واجهة سطر الأوامر (CLI Runner) ───────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Speech Deduplication Specialist - محو التكرارات والبدايات المتعثرة واختيار أفضل تيك"
    )
    parser.add_argument("work_dir", nargs="?", default=".", help="مسار مجلد العمل (Workspace directory)")
    parser.add_argument("--apply", action="store_true", help="تطبيق التعديلات وحفظها مباشرة في cut.json و caps.json")
    parser.add_argument("--dry", action="store_true", help="محاكاة الفحص وعرض التعديلات دون حفظها")
    parser.add_argument("--json", action="store_true", help="إخراج تقرير JSON تقني مفصل")
    parser.add_argument("--undo", action="store_true", help="التراجع عن آخر حذف واستعادة النسخة الاحتياطية .bak")
    parser.add_argument("--threshold", type=float, default=0.60, help="نسبة التشابه لكشف إعادة الجمل (افتراضي 0.60)")
    parser.add_argument("--min-gap", type=float, default=0.20, help="أقل وقفة لاعتبار الاستئناف بداية متعثرة (افتراضي 0.20ث)")
    parser.add_argument("--max-ngram", type=int, default=3, help="أقصى حجم تكرار n-gram مباشر (افتراضي 3 كلمات)")

    # دعم كتابة: python 01b_dedup.py dedup <work> أو python 01b_dedup.py <work>
    argv = sys.argv[1:]
    if argv and argv[0].lower() == "dedup":
        argv = argv[1:]
    args = parser.parse_args(argv)

    work_dir = os.path.abspath(args.work_dir)
    P = lambda n: os.path.join(work_dir, n)

    if args.undo:
        ok = undo_deduplication(work_dir)
        if ok:
            print(f"↩️ تم التراجع بنجاح واستعادة الملفات السابقة في: {work_dir}")
        else:
            print(f"⚠️ ما فيه نسخ احتياطية سابقة (.bak) للتراجع عنها في: {work_dir}")
        return

    caps_path = P("caps.json")
    if not os.path.exists(caps_path):
        print(f"❌ لم يتم العثور على caps.json في {work_dir}")
        print("💡 تأكد من تشغيل 01_cut_plan.py ثم 01b_transcribe.py ثم 02_captions.py أولاً.")
        sys.exit(1)

    caps_data = json.load(open(caps_path, encoding="utf-8"))
    cards = caps_data.get("cards", [])

    intervals, dropped_tokens = detect_all_speech_repetitions(
        cards,
        similarity_th=args.threshold,
        min_restart_gap=args.min_gap,
        max_ngram=args.max_ngram
    )

    if args.json:
        report = {
            "work_dir": work_dir,
            "total_intervals": len(intervals),
            "dropped_tokens_count": len(dropped_tokens),
            "intervals": [asdict(iv) for iv in intervals]
        }
        if args.apply:
            stats = apply_deduplication(work_dir, intervals, dropped_tokens, dry_run=False)
            report["applied_stats"] = stats
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("=" * 72)
    print("🎙️ فاحص ومزيل التكرارات والبدايات المتعثرة (Speech Deduplication Specialist)")
    print(f"📁 المجلد: {work_dir}")
    print(f"⏱️ المدة الإجمالية الحالية: {caps_data.get('total', 0.0):.2f} ثانية · {len(cards)} كرت")
    print("=" * 72)

    if not intervals:
        print("\n✅ رائع! لم يتم رصد أي تكرارات أو تأتأة أو بدايات متعثرة في هذا المقطع.")
        return

    print(f"\n🔍 تم رصد {len(intervals)} عثرة/تكرار تحتاج للتنقيح:")
    tot_time_est = sum(iv.end - iv.start for iv in intervals)

    for idx, iv in enumerate(intervals, 1):
        cat_icon = {
            "sentence_retake": "🔁 [إعادة تيك كامل]",
            "restart_pattern": "🛑 [بداية متعثرة واستئناف]",
            "ngram_stutter_1": "⚡ [تأتأة كلمة واحدة]",
            "ngram_stutter_2": "⚡ [تأتأة كلمتين]",
            "ngram_stutter_3": "⚡ [تأتأة 3 كلمات]"
        }.get(iv.category, "✂️ [تكرار]")

        print(f"\n{idx}. {cat_icon}  [{iv.start:05.2f}ث ──> {iv.end:05.2f}ث]  (المدة: {iv.end - iv.start:.2f}ث)")
        print(f"   السبب   : {iv.reason}")
        print(f"   ❌ يُحذف : \"{iv.discard_text}\"")
        print(f"   ✅ يُعتمد: \"{iv.keep_text}\"")
        if iv.score_diff:
            print(f"   📊 الميزان: {iv.score_diff}")

    print("\n" + "-" * 72)
    print(f"📉 إجمالي الوقت المتوقع توفيره: {tot_time_est:.2f} ثانية ({(tot_time_est / max(0.1, caps_data.get('total', 1.0)))*100:.1f}٪ اختصار)")

    if args.apply:
        stats = apply_deduplication(work_dir, intervals, dropped_tokens, dry_run=False)
        print("\n🚀 تم تطبيق الحذف وتنقيح التايم لاين بنجاح:")
        print(f"   - المدة الجديدة: {stats['new_total']:.2f} ثانية (انحذف {stats['seconds_removed']:.2f} ثانية)")
        print(f"   - الكلمات المحذوفة: {stats['words_dropped']} كلمة")
        print(f"   - الكروت المزالة كلياً: {stats['cards_dropped']} كرت")
        if stats.get("sfx_moved", 0) or stats.get("sfx_killed", 0):
            print(f"   - المؤثرات الصوتية: {stats['sfx_moved']} انزاحت لمكانها · {stats['sfx_killed']} انحذفت")
        print("\n🎬 الخطوة التالية لإعادة الرندر:")
        print(f"   python scripts/03_cut_zoom.py \"{work_dir}\"")
        print(f"   mkdir -p \"{work_dir}/vfr\" && ffmpeg -v error -i \"{work_dir}/cutz.mp4\" -vf fps=30 -q:v 3 -y \"{work_dir}/vfr/%05d.jpg\"")
        print(f"   node scripts/04_render_frames.js \"{work_dir}\" all --force")
        print(f"↩️ للتراجع عن هذا التعديل: python scripts/01b_dedup.py \"{work_dir}\" --undo")
    else:
        print("\n💡 للتطبيق التلقائي وقص هذه التكرارات من الفيديو والصوت والكابشن:")
        print(f"   python scripts/01b_dedup.py \"{work_dir}\" --apply")
        print(f"   أو: python scripts/10_script_edit.py \"{work_dir}\" dedup --apply")


if __name__ == "__main__":
    main()
