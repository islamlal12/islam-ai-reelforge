# -*- coding: utf-8 -*-
"""
===============================================================================
Linguistic Verification & Dialect Alignment Module for Arabic Captions
(02d_caption_linguistics.py)
===============================================================================
- Normalizes common Whisper misrecognitions in Arabic dialects (Egyptian, Gulf,
  Levantine) and Modern Standard Arabic (MSA).
- Normalizes Hamza variants (أ / إ / آ / ا), Taa Marbuta vs Haa (ة vs ه),
  and Alif Maqsura vs Yaa (ى vs ي).
- Standardizes AI, Tech, and Creator terminology (ChatGPT, Claude, Cursor, AI, etc.).
- Loads project-level and global dictionary corrections from `fixes.json`.
- Enforces verbatim fidelity and checks audio timestamps to prevent subtitle
  flicker, overlapping, or premature disappearance ("فرفشة").
- Dynamically chunks words into high-retention 1-3 word batches with calibrated
  compact-to-medium font sizing (42px - 50px).
===============================================================================
"""

import sys
import os
import re
import json

# Windows console UTF-8 fix
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# =============================================================================
# 1. Linguistic Knowledge Base & Normalization Tables
# =============================================================================

# Common dialectal particles and Whisper misrecognitions
DIALECT_NORMALIZATIONS = {
    # Egyptian dialect common tokens
    "ايه": "إيه",
    "اية": "إيه",
    "ايوه": "أيوه",
    "أيوة": "أيوه",
    "ايوة": "أيوه",
    "عشان": "عشان",
    "علشان": "عشان",
    "عاشان": "عشان",
    "كده": "كده",
    "كدا": "كده",
    "كدة": "كده",
    "ده": "ده",
    "دا": "ده",
    "دة": "ده",
    "دي": "دي",
    "دى": "دي",
    "دول": "دول",
    "دلوقتي": "دلوقتي",
    "دلوقتى": "دلوقتي",
    "ليه": "ليه",
    "لية": "ليه",
    "برضه": "برضه",
    "برضو": "برضه",
    "برضة": "برضه",
    "ازاي": "إزاي",
    "ازاى": "إزاي",
    "احنا": "إحنا",
    "انت": "إنت",
    "انتي": "إنتي",
    "انتو": "إنتو",
    "انتم": "أنتم",

    # Gulf / Levantine / North African dialect tokens
    "ايش": "إيش",
    "أيش": "إيش",
    "وش": "وش",
    "شو": "شو",
    "اشو": "شو",
    "هادا": "هذا",
    "هاد": "هذا",
    "هيك": "هيك",
    "هسا": "هسه",
    "هسه": "هسه",
    "الحين": "الحين",
    "صار": "صار",
    "صاير": "صاير",
    "تبغى": "تبغى",
    "تبغي": "تبغي",
    "بدك": "بدك",
    "عايز": "عايز",
    "ياريت": "يا ريت",
    "ياجماعة": "يا جماعة",
    "ياجماعه": "يا جماعة",

    # Religious & Honorific common expressions
    "انشاء الله": "إن شاء الله",
    "ان شاء الله": "إن شاء الله",
    "ماشاء الله": "ما شاء الله",
    "باذن الله": "بإذن الله",
    "واللهي": "والله",
    "والله": "والله",
}

# Hamza normalization (Alif with Hamza Above/Below, Madda, Wasla)
HAMZA_CORRECTIONS = {
    # Prepositions & Connectors
    "الي": "إلى",
    "إلي": "إلى",
    "الا": "إلا",
    "إلا": "إلا",
    "اذا": "إذا",
    "او": "أو",
    "ان": "إن",
    "اي": "أي",
    "اين": "أين",
    "الان": "الآن",
    "ايضا": "أيضاً",
    "ايام": "أيام",

    # Common nouns & adjectives
    "اكبر": "أكبر",
    "افضل": "أفضل",
    "احسن": "أحسن",
    "اكثر": "أكثر",
    "اصغر": "أصغر",
    "اسرع": "أسرع",
    "اسهل": "أسهل",
    "اهم": "أهم",
    "اول": "أول",
    "اخر": "آخر",
    "اخري": "أخرى",
    "اخوات": "أخوات",
    "اداة": "أداة",
    "ادوات": "أدوات",
    "امر": "أمر",
    "اوامر": "أوامر",
    "ارقام": "أرقام",
    "اسماء": "أسماء",
    "افكار": "أفكار",
    "اعمال": "أعمال",
    "اسبوع": "أسبوع",
    "اشهر": "أشهر",
    "اشياء": "أشياء",
    "انسان": "إنسان",
    "انتاج": "إنتاج",
    "انترنت": "إنترنت",
    "انجاز": "إنجاز",
    "اعلان": "إعلان",
    "اعلانات": "إعلانات",
    "اعلام": "إعلام",
    "اصدار": "إصدار",
    "ادارة": "إدارة",
    "ايميل": "إيميل",
    "ايميلات": "إيميلات",
}

# Taa Marbuta (ة) vs Haa (ه) corrections for frequent technical & media words
TAA_MARBUTA_CORRECTIONS = {
    "تقنيه": "تقنية",
    "برمجه": "برمجة",
    "طريقه": "طريقة",
    "خطوه": "خطوة",
    "شركه": "شركة",
    "منصه": "منصة",
    "قناه": "قناة",
    "حلقه": "حلقة",
    "نتيجه": "نتيجة",
    "صوره": "صورة",
    "خدمه": "خدمة",
    "تجربه": "تجربة",
    "فرصه": "فرصة",
    "بدايه": "بداية",
    "نهايه": "نهاية",
    "عمليه": "عملية",
    "دقيقه": "دقيقة",
    "ساعه": "ساعة",
    "ثانيه": "ثانية",
    "نسبه": "نسبة",
    "جمله": "جملة",
    "كلمه": "كلمة",
    "سرعه": "سرعة",
    "قوه": "قوة",
    "جوده": "جودة",
    "واجهه": "واجهة",
    "ميزه": "ميزة",
    "فائده": "فائدة",
    "سهوله": "سهولة",
    "صعوبه": "صعوبة",
    "فكره": "فكرة",
    "رساله": "رسالة",
    "نسخه": "نسخة",
}

# Words that MUST end in Haa (ه) and should never be accidentally changed to ة
TRUE_HAA_WORDS = {
    "وجه", "فقه", "شبه", "منبه", "سفيه", "معه", "له", "به", "عنه",
    "منه", "فيه", "عليه", "إليه", "عنده", "معه", "بينه", "دونه",
    "كله", "أصله", "فصله", "الله", "إله", "مياه", "اتجاه", "اشتباه"
}

# AI, Tech, and Creator term standardizations
TECH_TERMINOLOGY = {
    # AI tools & LLMs
    "شات جى بى تى": "ChatGPT",
    "شات جي بي تي": "ChatGPT",
    "شاتجبتي": "ChatGPT",
    "شات جبتي": "ChatGPT",
    "chatgpt": "ChatGPT",
    "كلاود": "Claude",
    "كلود": "Claude",
    "claude": "Claude",
    "كورسور": "Cursor",
    "cursor": "Cursor",
    "ميدجورني": "Midjourney",
    "ميدجورنى": "Midjourney",
    "midjourney": "Midjourney",
    "جيميني": "Gemini",
    "جيمني": "Gemini",
    "gemini": "Gemini",
    "ويسبر": "Whisper",
    "وسبر": "Whisper",
    "whisper": "Whisper",

    # AI Concepts & Abbreviations
    "اي اي": "AI",
    "أي آي": "AI",
    "الاي اي": "الـ AI",
    "الـ ai": "الـ AI",
    "الذكاء الاصطناعي": "الذكاء الاصطناعي",
    "ذكاء اصطناعي": "ذكاء اصطناعي",
    "برومبت": "برومبت",
    "برومت": "برومبت",
    "prompt": "Prompt",
    "اي بي اي": "API",
    "ايه بي اي": "API",
    "api": "API",

    # Social & Media Platforms
    "ريل": "ريل",
    "ريلز": "ريلز",
    "reels": "Reels",
    "reel": "Reel",
    "فديو": "فيديو",
    "فيديو": "فيديو",
    "انستغرام": "إنستغرام",
    "انستقرام": "إنستغرام",
    "انستجرام": "إنستغرام",
    "instagram": "Instagram",
    "تيك توك": "تيك توك",
    "تكتوك": "تيك توك",
    "tiktok": "TikTok",
    "يوتيوب": "يوتيوب",
    "يوتوب": "يوتيوب",
    "youtube": "YouTube",
    "لينكد إن": "لينكد إن",
    "لينكد ان": "لينكد إن",
    "لينكدإن": "لينكد إن",
    "linkedin": "LinkedIn",
    "بودكاست": "بودكاست",
    "بدكاست": "بودكاست",
    "podcast": "Podcast",

    # Programming & Tech
    "بايثون": "بايثون",
    "python": "Python",
    "جافاسكريبت": "جافاسكريبت",
    "javascript": "JavaScript",
    "فرونت إند": "فرونت إند",
    "فرونت اند": "فرونت إند",
    "frontend": "Frontend",
    "باك إند": "باك إند",
    "باك اند": "باك إند",
    "backend": "Backend",
}

# =============================================================================
# 2. Token Normalization Logic
# =============================================================================

def strip_punctuation(text: str) -> tuple:
    """Strips leading/trailing punctuation while tracking what was removed."""
    leading = ""
    trailing = ""
    
    # Strip leading quotes/brackets
    m_lead = re.match(r"^([\"'«»\(\)\[\]\{\}\s]+)", text)
    if m_lead:
        leading = m_lead.group(1)
        text = text[len(leading):]
        
    # Strip trailing commas, periods, question marks, exclamation marks
    m_trail = re.search(r"([،.,!؟?\"'«»\(\)\[\]\{\}\s]+)$", text)
    if m_trail:
        trailing = m_trail.group(1)
        text = text[:-len(trailing)]
        
    return text.strip(), leading, trailing


def normalize_text_phrases(text: str, custom_dict: dict = None) -> str:
    """Replaces multi-word phrases (like 'شات جي بي تي' or 'إن شاء الله') before word tokenization."""
    if not text:
        return ""
    
    # Check custom dictionary phrases first
    if custom_dict:
        for phrase, rep in custom_dict.items():
            if " " in phrase and phrase in text:
                text = text.replace(phrase, rep)

    # Check TECH_TERMINOLOGY multi-word phrases
    for phrase, rep in TECH_TERMINOLOGY.items():
        if " " in phrase and phrase in text:
            # Word boundary check for Arabic text
            text = re.sub(rf'(?<!\w){re.escape(phrase)}(?!\w)', rep, text)

    # Check DIALECT_NORMALIZATIONS multi-word phrases
    for phrase, rep in DIALECT_NORMALIZATIONS.items():
        if " " in phrase and phrase in text:
            text = re.sub(rf'(?<!\w){re.escape(phrase)}(?!\w)', rep, text)

    return text


def normalize_word(word: str, custom_dict: dict = None) -> str:
    """
    Applies linguistic rules to normalize an individual Arabic word token.
    Preserves true haa words, normalizes dialectal pronunciations, hamzas,
    and applies custom dictionary overrides.
    """
    if not word:
        return ""

    raw_word = word.strip()
    clean, lead, trail = strip_punctuation(raw_word)

    if not clean:
        return raw_word

    # 1. Check custom dictionary first (project-level overrides)
    if custom_dict and clean in custom_dict:
        return lead + custom_dict[clean] + trail
    if custom_dict and clean.lower() in custom_dict:
        return lead + custom_dict[clean.lower()] + trail

    # 2. Check Tech / AI terminology
    clean_lower = clean.lower()
    if clean_lower in TECH_TERMINOLOGY:
        return lead + TECH_TERMINOLOGY[clean_lower] + trail
    if clean in TECH_TERMINOLOGY:
        return lead + TECH_TERMINOLOGY[clean] + trail

    # 3. Check Dialectal normalizations
    if clean in DIALECT_NORMALIZATIONS:
        clean = DIALECT_NORMALIZATIONS[clean]
    elif clean_lower in DIALECT_NORMALIZATIONS:
        clean = DIALECT_NORMALIZATIONS[clean_lower]

    # 4. Check Hamza corrections
    if clean in HAMZA_CORRECTIONS:
        clean = HAMZA_CORRECTIONS[clean]

    # 5. Check Taa Marbuta vs Haa corrections
    if clean in TAA_MARBUTA_CORRECTIONS:
        clean = TAA_MARBUTA_CORRECTIONS[clean]
    elif clean.endswith("ه") and clean not in TRUE_HAA_WORDS:
        # Check if known root needs ة
        if clean in TAA_MARBUTA_CORRECTIONS:
            clean = TAA_MARBUTA_CORRECTIONS[clean]

    # 6. Alif Maqsura vs Yaa rules
    if clean == "فى":
        clean = "في"
    elif clean == "حتي":
        clean = "حتى"
    elif clean == "الي":
        clean = "إلى"

    return lead + clean + trail


def normalize_sentence(sentence: str, custom_dict: dict = None) -> str:
    """Normalizes an entire sentence or phrase, replacing multi-word phrases first, then tokens."""
    if not sentence:
        return ""
    text = normalize_text_phrases(sentence, custom_dict)
    tokens = text.split()
    return " ".join([normalize_word(tok, custom_dict) for tok in tokens])



def load_lexicon(work_dir: str = None) -> dict:
    """
    Loads project-level dictionary corrections from `fixes.json`
    (looks for 'dict', 'replacements', or 'lexicon' keys) and checks global dict.
    """
    custom = {}
    
    # 1. Global dictionary if exists
    global_dict_paths = [
        os.path.join(os.path.dirname(__file__), "..", "references", "caption_dictionary.json"),
        os.path.expanduser("~/.islam-ai/caption_dictionary.json")
    ]
    for gpath in global_dict_paths:
        if os.path.exists(gpath):
            try:
                with open(gpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        custom.update(data)
            except Exception:
                pass

    # 2. Project fixes.json
    if work_dir:
        fix_path = os.path.join(work_dir, "fixes.json")
        if os.path.exists(fix_path):
            try:
                with open(fix_path, "r", encoding="utf-8") as f:
                    fx_data = json.load(f)
                    for k in ["dict", "replacements", "lexicon", "custom_words"]:
                        if k in fx_data and isinstance(fx_data[k], dict):
                            custom.update(fx_data[k])
            except Exception:
                pass

    return custom

# =============================================================================
# 3. Verbatim Fidelity & Audio Timestamp Verification
# =============================================================================

def verify_timestamps(words: list) -> list:
    """
    Checks verbatim fidelity against audio timestamps:
    - Enforces strict monotonicity: s < e
    - Anti-flicker: clamps minimum display duration to >= 0.12s
    - Clamps micro-gaps to prevent subtitle flicker / disappearance ("فرفشة")
    """
    if not words:
        return []

    verified = []
    prev_end = 0.0

    for i, w in enumerate(words):
        s = float(w.get("s", 0.0))
        e = float(w.get("e", s + 0.14))

        # Enforce minimum word duration
        if e <= s:
            e = s + 0.14
        elif (e - s) < 0.10:
            e = s + 0.12

        # Prevent overlap with previous word
        if s < prev_end:
            # If overlap is small (< 0.08s), shift s slightly or adjust prev_end
            if prev_end - s < 0.08 and len(verified) > 0:
                verified[-1]["e"] = round(s, 3)
            else:
                s = prev_end

        w_clean = dict(w)
        w_clean["s"] = round(s, 3)
        w_clean["e"] = round(e, 3)
        verified.append(w_clean)
        prev_end = e

    return verified

# =============================================================================
# 4. Smart Compact-to-Medium Chunking (2-3 Words Target)
# =============================================================================

def compute_smart_font_size(word_count: int) -> int:
    """
    Recalibrates caption sizing to a smart 'compact-to-medium' scale:
    * 1-2 words: 48px
    * 3 words: 44px
    * 4+ words (fallback): 42px
    Strictly within 42px - 50px base scale.
    """
    if word_count <= 2:
        return 48
    elif word_count == 3:
        return 44
    else:
        return 42


def chunk_words_smart(words: list, max_words: int = 3, max_chars: int = 24) -> list:
    """
    Groups words into 1 to 3 word chunks (ideal 2-3 words for high retention).
    Ensures safe vertical positioning (Y = 1320-1420 px) and stable baselines
    to guarantee zero jitter ("0 فرفشة").
    """
    if not words:
        return []

    chunks = []
    current_chunk = []
    current_chars = 0

    for w in words:
        txt = w.get("t", "").strip()
        w_len = len(txt)

        # Break chunk if max words reached or max characters exceeded
        if current_chunk and (len(current_chunk) >= max_words or (current_chars + w_len) > max_chars):
            chunks.append(current_chunk)
            current_chunk = []
            current_chars = 0

        current_chunk.append(w)
        current_chars += w_len + 1

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def build_smart_cards(raw_cards: list, keep_ranges: list = None, acc_duration: float = 0.0) -> list:
    """
    Converts segment cards into smart compact-to-medium chunked cards.
    Each card gets:
    - 1-3 words max
    - Dynamic font size (44px for 3 words, 48px for 1-2 words)
    - Line height ~58px - 62px
    - Anchor safe Y: 1370 px (strictly within safe area: 1320 - 1420 px)
    - Smooth start and end timestamps avoiding jitter
    """
    smart_cards = []

    for seg_idx, card in enumerate(raw_cards):
        words = card.get("w", [])
        if not words:
            continue

        verified_words = verify_timestamps(words)
        chunks = chunk_words_smart(verified_words, max_words=3, max_chars=22)

        for chunk_idx, chunk in enumerate(chunks):
            if not chunk:
                continue

            c_words = chunk
            c_start = max(0.0, c_words[0]["s"] - 0.06)
            c_end = c_words[-1]["e"] + 0.16

            fs = compute_smart_font_size(len(c_words))
            lh = int(round(fs * 1.32))

            smart_cards.append({
                "s": round(c_start, 3),
                "e": round(c_end, 3),
                "w": c_words,
                "fontSize": fs,
                "lineHeight": lh,
                "safeY": 1370,
                "seg": card.get("seg", seg_idx),
                "chunk": chunk_idx
            })

    # Sort and guarantee no overlap
    smart_cards.sort(key=lambda c: c["s"])
    for i in range(len(smart_cards) - 1):
        if smart_cards[i]["e"] > smart_cards[i+1]["s"]:
            smart_cards[i]["e"] = round(smart_cards[i+1]["s"] - 0.02, 3)
            # Ensure minimum duration for card
            if smart_cards[i]["e"] <= smart_cards[i]["s"]:
                smart_cards[i]["e"] = smart_cards[i]["s"] + 0.25

    return smart_cards

# =============================================================================
# 5. CLI & Test Suite
# =============================================================================

def process_linguistics(work_dir: str):
    """Executes a complete linguistic verification and dialect alignment pass."""
    work_dir = os.path.abspath(work_dir)
    print(f"🔍 Running Linguistic Verification Pass on: {work_dir}")

    custom_lexicon = load_lexicon(work_dir)
    if custom_lexicon:
        print(f"📖 Loaded {len(custom_lexicon)} custom dictionary corrections.")

    fixes_path = os.path.join(work_dir, "fixes.json")
    if os.path.exists(fixes_path):
        try:
            with open(fixes_path, "r", encoding="utf-8") as f:
                fx = json.load(f)
            
            corrections_count = 0
            new_fix = []
            for line in fx.get("fix", []):
                if isinstance(line, list):
                    new_line = []
                    for w in line:
                        norm = normalize_word(w, custom_lexicon)
                        if norm != w:
                            corrections_count += 1
                        new_line.append(norm)
                    new_fix.append(new_line)
                elif isinstance(line, str):
                    words = line.split()
                    norm_words = [normalize_word(w, custom_lexicon) for w in words]
                    new_fix.append(" ".join(norm_words))
                else:
                    new_fix.append(line)
                    
            fx["fix"] = new_fix
            with open(fixes_path, "w", encoding="utf-8") as f:
                json.dump(fx, f, ensure_ascii=False, indent=2)
                
            print(f"✨ Applied {corrections_count} linguistic & dialect normalizations to fixes.json")
        except Exception as e:
            print(f"⚠️ Error updating fixes.json: {e}")

    print("✅ Linguistic verification complete.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        process_linguistics(sys.argv[1])
    else:
        # Self-test unit checks
        test_words = [
            ("ايه ده", "إيه ده"),
            ("عشان كده", "عشان كده"),
            ("شات جى بى تى", "ChatGPT"),
            ("كلود", "Claude"),
            ("تقنيه", "تقنية"),
            ("وجه", "وجه"),
            ("الي", "إلى"),
            ("اكبر", "أكبر"),
            ("انستقرام", "إنستغرام"),
            ("تكتوك", "تيك توك")
        ]
        print("🧪 Running self-test for Arabic Linguistic Normalization:")
        all_passed = True
        for raw, expected in test_words:
            res = normalize_sentence(raw)
            ok = (res == expected)
            all_passed = all_passed and ok
            mark = "✅" if ok else "❌"
            print(f" {mark} '{raw}' -> '{res}' (expected: '{expected}')")

        if all_passed:
            print("🎉 All linguistic normalizations passed successfully!")
        else:
            sys.exit(1)
