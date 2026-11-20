# -*- coding: utf-8 -*-
"""
scripts/36_motion_mapper.py - خريطة الحركة للفريمات المباشرة (Motion-to-Frame Event Mapper)
يقوم بمسح الفيديو، مشاهد الكود، ملفات التقطيع والكابشن، واستخراج كل حركة إلى فريمها الدقيق:
- الفريم الأولي للحركة (Frame 0 of move)
- العنصر المتحرك (Card, Cursor, Title, Window)
- نوع الحركة (Slide, Click, Landing, Cut, Riser, Hero Slam)
- خامة العنصر (Tech, Glass, Paper, Solid Metallic)
- تعيين مؤثر صوتي ثابت لنفس نوع الحركة (Sonic Consistency)
"""

import sys, os, json, re

# إعداد مخرجات UTF-8 لويندوز
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FPS = 30.0

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def analyze_motion(work_dir):
    work_dir = os.path.abspath(work_dir)
    caps = load_json(os.path.join(work_dir, "caps.json"))
    cut = load_json(os.path.join(work_dir, "cut.json"))
    hook = load_json(os.path.join(work_dir, "hook.json"))
    sfx_existing = load_json(os.path.join(work_dir, "sfx.json"))

    total_dur = float(caps.get("total", 0.0))
    if total_dur == 0.0 and "keep" in cut:
        total_dur = sum(seg[1] - seg[0] for seg in cut.get("keep", []))
    if total_dur == 0.0:
        total_dur = 30.0  # قيمة افتراضية

    total_frames = int(round(total_dur * FPS))
    moves = []

    # 1. فحص الهوك في الفريم 0 (First-5-Seconds Text Hook)
    hook_text = hook.get("text", "")
    hook_style = hook.get("style", "card-white")
    mat_hook = "glass" if "glass" in hook_style else ("paper" if "card" in hook_style else "tech")
    
    # Hero Hit في أول فريم
    moves.append({
        "frame": 0,
        "time_s": 0.0,
        "target": "hook_hero",
        "action": "hero_hit",
        "material": mat_hook,
        "level": "hero",
        "sfx": "sub_impact",
        "layers": ["whoosh_fast", "glass_tap" if mat_hook == "glass" else "button_click", "sub_impact"]
    })

    # 2. فحص الهبوط أو شتر الكرت عند استقرار الهوك (t = 0.25s / F7)
    moves.append({
        "frame": 7,
        "time_s": 0.233,
        "target": "hook_card_settle",
        "action": "landing",
        "material": mat_hook,
        "level": "medium",
        "sfx": "camera_shutter" if "card" in hook_style else "metal_latch"
    })

    # 3. فحص قطوع Jump Cuts من cut.json لإضافة Whoosh خفيف متناسق قبل القطعية
    segs = cut.get("keep", [])
    running_t = 0.0
    for i in range(len(segs) - 1):
        seg_dur = segs[i][1] - segs[i][0]
        running_t += seg_dur
        # القطعية تحدث عند running_t
        cut_frame = int(round(running_t * FPS))
        # Whoosh يسبق القطع بفريمين أو ثلاثة (60ms-90ms)
        lead_frame = max(0, cut_frame - 2)
        lead_t = round(lead_frame / FPS, 3)
        moves.append({
            "frame": lead_frame,
            "time_s": lead_t,
            "target": f"jump_cut_{i+1}",
            "action": "cut",
            "material": "air",
            "level": "soft",
            "sfx": "whoosh_fast"
        })

    # 4. فحص كروت الكابشن والكلمات المشددة (Hot Words / Emphasis)
    for card in caps.get("cards", []):
        for w in card.get("w", []):
            if w.get("hot"):
                w_time = float(w.get("s", 0.0))
                w_frame = int(round(w_time * FPS))
                # تجنب وضع صوتين على نفس الفريم بالضبط
                if not any(abs(m["frame"] - w_frame) < 3 for m in moves):
                    moves.append({
                        "frame": w_frame,
                        "time_s": round(w_time, 3),
                        "target": f"hot_word_{w.get('t', '')[:10]}",
                        "action": "pop",
                        "material": "tech",
                        "level": "soft",
                        "sfx": "pop_bubble"
                    })

    # 5. فحص كود المشاهد compose.html وملف motion_extracted.json إن وجد
    extracted_path = os.path.join(work_dir, "motion_extracted.json")
    if os.path.exists(extracted_path):
        ext_moves = load_json(extracted_path)
        if isinstance(ext_moves, list):
            for em in ext_moves:
                ef = int(em.get("frame", 0))
                if not any(abs(m["frame"] - ef) < 3 for m in moves):
                    moves.append({
                        "frame": ef,
                        "time_s": float(em.get("time_s", ef / FPS)),
                        "target": str(em.get("target", "motion_element")),
                        "action": str(em.get("action", "slide")),
                        "material": str(em.get("type", "tech")),
                        "level": "medium",
                        "sfx": "whoosh_card" if em.get("action") == "slide" else "button_click"
                    })

    compose_path = os.path.join(work_dir, "compose.html")
    if os.path.exists(compose_path):
        try:
            with open(compose_path, "r", encoding="utf-8") as f:
                content = f.read()

            # أ) فحص استدعاءات MK المباشرة مع التوقيتات t0: MK.toolLabel(..., t0)
            pattern_mk = r"(MK\.\w+)\s*\([^)]*?([0-9]+\.?[0-9]*)\s*[,)]"
            for m in re.finditer(pattern_mk, content):
                mk_comp = m.group(1)
                try:
                    t_val = float(m.group(2))
                    if 0.0 < t_val < total_dur:
                        f_val = int(round(t_val * FPS))
                        if not any(abs(mv["frame"] - f_val) < 3 for mv in moves):
                            act_type = "slide" if "card" in mk_comp.lower() or "label" in mk_comp.lower() else "click"
                            mat_type = "glass" if "glass" in mk_comp.lower() else "tech"
                            moves.append({
                                "frame": f_val,
                                "time_s": round(t_val, 3),
                                "target": mk_comp,
                                "action": act_type,
                                "material": mat_type,
                                "level": "medium",
                                "sfx": "whoosh_card" if act_type == "slide" else "button_click"
                            })
                except Exception:
                    pass

            # ب) فحص كتل CSS @keyframes و transitions
            keyframes = re.findall(r"@keyframes\s+([a-zA-Z0-9_-]+)", content)
            for kf in keyframes:
                # إذا كانت حركة دخول واضحة
                if any(x in kf.lower() for x in ["slide", "enter", "pop", "fade"]):
                    # البحث عن فئة CSS تستخدمها
                    pass
        except Exception:
            pass

    # 6. إضافة رايزر وخاتمة الـ CTA في آخر الفيديو
    outro_t = max(0.0, total_dur - 3.5)
    outro_frame = int(round(outro_t * FPS))
    # رايزر 0.5 ثانية قبل ضربة الـ CTA
    riser_frame = max(0, outro_frame - 15)
    moves.append({
        "frame": riser_frame,
        "time_s": round(riser_frame / FPS, 3),
        "target": "cta_riser",
        "action": "riser",
        "material": "tech",
        "level": "medium",
        "sfx": "riser_0.5s"
    })
    moves.append({
        "frame": outro_frame,
        "time_s": round(outro_t, 3),
        "target": "cta_card_hero",
        "action": "hero_hit",
        "material": "tech",
        "level": "hero",
        "sfx": "sub_impact",
        "layers": ["button_click", "glass_tap", "sub_impact"]
    })

    # ترتيب الأحداث زمنياً وحساب الكثافة
    moves.sort(key=lambda x: x["frame"])

    # ضبط قاعدة وحدة الهوية الصوتية (Sonic Brand Consistency)
    # كل نوع حركة يحصل على نفس المؤثر الصوتي بالضبط طوال الفيديو
    action_sound_registry = {
        "click": "button_click",
        "slide": "whoosh_card",
        "cut": "whoosh_fast",
        "landing": "camera_shutter",
        "pop": "pop_bubble",
        "type": "keystroke",
        "riser": "riser_0.5s",
        "hero_hit": "sub_impact"
    }

    for m in moves:
        act = m["action"]
        if act in action_sound_registry and "layers" not in m:
            m["sfx"] = action_sound_registry[act]

    # حساب كثافة الأحداث (12-14 لكل 10 ثوانٍ)
    density_per_10s = round((len(moves) / max(1.0, total_dur)) * 10.0, 1)

    return {
        "total_duration_s": round(total_dur, 2),
        "total_frames": total_frames,
        "moves_count": len(moves),
        "density_per_10s": density_per_10s,
        "moves": moves
    }

def print_table(result):
    print("=" * 88)
    print(f"🎬 خريطة أحداث الحركة إلى الفريمات المباشرة (Motion-to-Frame Map)")
    print(f"المدة الكلية: {result['total_duration_s']}s | إجمالي الفريمات: {result['total_frames']} | الأحداث: {result['moves_count']}")
    print(f"كثافة الأصوات: {result['density_per_10s']} حدث / 10 ثوانٍ (المعيار الموصى به: 12-14)")
    print("-" * 88)
    print(f"{'الفريم':<8} | {'الوقت (s)':<10} | {'العنصر':<20} | {'الحركة':<12} | {'الخامة':<10} | {'المستوى':<8} | {'المؤثر المعتمد'}")
    print("-" * 88)
    for m in result["moves"]:
        sfx_label = m.get("sfx", "")
        if "layers" in m:
            sfx_label = "+".join(m["layers"])
        print(f"F{m['frame']:<7} | {m['time_s']:<10.3f} | {m['target']:<20} | {m['action']:<12} | {m['material']:<10} | {m['level']:<8} | {sfx_label}")
    print("=" * 88)

def main():
    if len(sys.argv) < 2:
        print("الاستخدام: python scripts/36_motion_mapper.py <work_dir> [--apply]")
        sys.exit(1)

    work_dir = sys.argv[1]
    apply_mode = "--apply" in sys.argv

    res = analyze_motion(work_dir)
    print_table(res)

    out_map_path = os.path.join(work_dir, "motion_map.json")
    with open(out_map_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"✓ تم حفظ خريطة الفريمات في: {out_map_path}")

    if apply_mode:
        # تحويل الخريطة إلى صيغة sfx.json المتوافقة مع 05_sfx.py
        sfx_data = {
            "version": "2.0_hybrid",
            "events": res["moves"],
            "hero": [],
            "click": [],
            "whoosh_up": [],
            "whoosh_down": [],
            "pop": [],
            "type": [],
            "riser": []
        }
        for m in res["moves"]:
            t = m["time_s"]
            act = m["action"]
            if act == "hero_hit":
                sfx_data["hero"].append({"t": t, "material": m["material"], "gain": 1.0})
            elif act == "click":
                sfx_data["click"].append(t)
            elif act == "cut" or act == "slide":
                sfx_data["whoosh_up"].append(t)
            elif act == "pop":
                sfx_data["pop"].append(t)
            elif act == "type":
                sfx_data["type"].append([t, 0.4])
            elif act == "riser":
                sfx_data["riser"].append([t + 0.5, 0.5])

        sfx_path = os.path.join(work_dir, "sfx.json")
        with open(sfx_path, "w", encoding="utf-8") as f:
            json.dump(sfx_data, f, ensure_ascii=False, indent=2)
        print(f"✓ تم تطبيق وتحديث ملف المؤثرات: {sfx_path}")

if __name__ == "__main__":
    main()
