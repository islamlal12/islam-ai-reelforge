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
import wave, numpy as np
import sys, os
S = os.path.abspath(sys.argv[1]) + "/"
import json
SR = 48000
_c = json.load(open(S + "caps.json"))
_s = json.load(open(S + "sfx.json"))
VEND = float(_c.get("total", 0.0))
OUTRO = float(_s.get("outro", 0.0))
DUR = VEND + OUTRO
n = int(DUR * SR) + SR
buf = np.zeros(n)
rng = np.random.RandomState(11)

# 🛡️ استخراج توقيتات الكلمات المشددة لدرع حماية الكلام (Speech Collision Guard)
hot_starts = []
for card in _c.get("cards", []):
    for w in card.get("w", []):
        if w.get("hot"):
            hot_starts.append(float(w.get("s", 0.0)))
if "words" in _c:
    for w in _c.get("words", []):
        if w.get("hot"):
            hot_starts.append(float(w.get("s", 0.0)))
hot_starts = sorted(list(set(hot_starts)))

# 🎯 تجميع توقيتات Hero Hits المسبقة لتفعيل فجوة الصمت (Quiet Gap)
HERO_TIMES = []
for _h in _s.get("hero", []) + _s.get("hero_hits", []):
    if isinstance(_h, (int, float)):
        HERO_TIMES.append(float(_h))
    elif isinstance(_h, (list, tuple)) and len(_h) > 0:
        HERO_TIMES.append(float(_h[0]))
    elif isinstance(_h, dict):
        HERO_TIMES.append(float(_h.get("t", _h.get("t0", 0.0))))

def guard_collision(t0, g):
    """
    درع حماية الكلام من التضارب (Speech Collision Guard):
    فحص توقيتات الكلمات المشددة (hot words في caps.json).
    إذا تصادف مؤثر صوتي مع بداية كلمة مشددة خلال ±80ms:
    يتم تقديمه بمقدار فريمين (60ms) كـ Lead-in أو خفض علوه بـ -6dB لمنع حجب صوت المتحدث.
    """
    for hs in hot_starts:
        if abs(t0 - hs) <= 0.080:
            if t0 >= 0.060:
                t0 -= 0.060  # تقديم فريمين (Lead-in احترافي)
                if any(abs(t0 - h2) <= 0.040 for h2 in hot_starts):
                    g *= 0.501187  # -6 dB
            else:
                g *= 0.501187  # -6 dB
            break
    return t0, g

def in_quiet_gap(t, gap=0.25):
    """
    فجوة الصمت (Quiet Gap):
    ضمان هدوء نسبي (0.2s - 0.25s) قبل أي Hero Hit بحجب أي ticks أو whooshes طفيفة
    تسبقه مباشرة لمضاعفة أثر الضربة.
    """
    for ht in HERO_TIMES:
        if 0.0 <= (ht - t) <= gap:
            return True
    return False

def add(sig, t0, g=1.0, guard=True):
    if guard and hot_starts:
        t0, g = guard_collision(t0, g)
    i = max(0, int(t0 * SR))
    j = min(n, i + len(sig))
    if j > i:
        buf[i:j] += sig[:j - i] * g

def lp(x, a0, a1):
    y = np.empty_like(x)
    z = 0.0
    for i in range(len(x)):
        a = a0 + (a1 - a0) * (i / len(x))
        z += a * (x[i] - z)
        y[i] = z
    return y

def whoosh(dur=0.34, up=True):
    L = int(dur * SR)
    t = np.arange(L) / SR
    x = rng.randn(L)
    y = lp(x, 0.03, 0.30) if up else lp(x, 0.30, 0.03)
    y /= (np.max(np.abs(y)) + 1e-9)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.6
    return y * env

def thud(f0=135, f1=58, dur=0.30):
    L = int(dur * SR)
    t = np.arange(L) / SR
    f = f0 * np.exp(np.log(f1 / f0) * t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t / 0.085)
    s += lp(rng.randn(L), 0.35, 0.05) * np.exp(-t / 0.006) * 0.35
    return s / (np.max(np.abs(s)) + 1e-9)

def tap(dur=0.09):
    L = int(dur * SR)
    t = np.arange(L) / SR
    s = lp(rng.randn(L), 0.22, 0.05) * np.exp(-t / 0.013)
    s *= np.minimum(1.0, t / 0.0012)
    return s / (np.max(np.abs(s)) + 1e-9)

def tick(f=2400, dur=0.03):
    L = int(dur * SR)
    t = np.arange(L) / SR
    s = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.006)
    return s / (np.max(np.abs(s)) + 1e-9)

W1 = whoosh(0.34, True)
W2 = whoosh(0.30, False)
TH = thud()
TP = tap()

# 🎚️ لوحة أصوات موسّعة ومضبوطة احترافياً (v4.0 Ultra Skills)
def riser(dur=0.55):
    """
    ضبط المؤثرات الصاعدة (Clamped Risers):
    تقييد مدة riser(dur) لتكون محصورة بدقة بين 0.4 إلى 0.7 ثانية
    مع قطع أسي حاد ينتهي لحظياً على فريم الصدمة دون أي تسريب بعد الضربة.
    """
    dur = float(np.clip(dur, 0.4, 0.7))
    L = int(dur * SR)
    t = np.arange(L) / SR
    p = np.clip(t / dur, 0.0, 1.0)
    y = lp(rng.randn(L), 0.02, 0.48)
    y /= (np.max(np.abs(y)) + 1e-9)
    tone = np.sin(2 * np.pi * np.cumsum(160 + 950 * (p ** 2.2)) / SR) * 0.35
    # منحنى أسي حاد ينتهي لحظياً على فريم الصدمة
    env = (np.exp(3.5 * p) - 1.0) / (np.exp(3.5) - 1.0)
    sig = (y * 0.75 + tone) * env
    sig[-1] = 0.0  # قطع حاد دون أي تسريب
    return sig / (np.max(np.abs(sig)) + 1e-9)

def pop(f0=900, f1=420, dur=0.12):
    L = int(dur * SR)
    t = np.arange(L) / SR
    f = f0 * np.exp(np.log(f1 / f0) * t / dur)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.035)
    return s / (np.max(np.abs(s)) + 1e-9)

def click(dur=0.025):
    L = int(dur * SR)
    t = np.arange(L) / SR
    s = (np.sin(2 * np.pi * 3400 * t) + 0.6 * rng.randn(L) * np.exp(-t / 0.002)) * np.exp(-t / 0.004)
    return s / (np.max(np.abs(s)) + 1e-9)

def typing(dur=0.8, cps=12):
    L = int(dur * SR)
    o = np.zeros(L)
    k = click(0.02)
    for i in range(int(dur * cps)):
        j = int((i / cps + rng.uniform(-0.01, 0.01)) * SR)
        j = max(0, min(L - len(k), j))
        o[j:j + len(k)] += k * rng.uniform(0.5, 1.0)
    return o / (np.max(np.abs(o)) + 1e-9)

def shimmer(dur=0.9):
    L = int(dur * SR)
    t = np.arange(L) / SR
    s = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / (0.25 + 0.1 * i)) for i, f in enumerate([1760, 2217, 2637, 3520]))
    return s / (np.max(np.abs(s)) + 1e-9)

def sub(dur=0.7):
    L = int(dur * SR)
    t = np.arange(L) / SR
    f = 60 * np.exp(np.log(34 / 60) * t / dur)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.22)
    return s / (np.max(np.abs(s)) + 1e-9)

def glitch(dur=0.28):
    L = int(dur * SR)
    s = np.zeros(L)
    for _ in range(7):
        a = rng.randint(0, L - 800)
        b = a + rng.randint(300, 1600)
        b = min(b, L)
        s[a:b] += np.round(rng.randn(b - a) * 3) / 3 * rng.uniform(0.4, 1.0)
    return s / (np.max(np.abs(s)) + 1e-9)

# 💥 الضربة الثلاثية للحظات الكبرى (Hero 3-Layer Stack)
def make_hero_sound(material='tech'):
    """
    توليد مصفوفة الضربة الثلاثية:
    1. Attack عالي: ضربة نفاذة حادة وسريعة (Click/Snap) لتأكيد اللحظة بدقة
    2. Mid body: جسم الصوت يمثل خامة العنصر (tech, wood/organic, glass/crystal, heavy/stone)
    3. Low sub-bass: تردد عميق 45Hz مع اضمحلال أسي 0.35s للشعور بوزن الصدمة وهيبتها
    """
    # ── الطبقة الأولى: High Attack Transient (0.04s) ──
    L_att = int(0.040 * SR)
    t_att = np.arange(L_att) / SR
    f_att = 5800.0 * np.exp(-t_att / 0.006) + 400.0
    click_tr = np.sin(2 * np.pi * np.cumsum(f_att) / SR) * np.exp(-t_att / 0.005)
    noise_tr = lp(rng.randn(L_att), 0.45, 0.10) * np.exp(-t_att / 0.004)
    attack = click_tr * 0.65 + noise_tr * 0.35
    attack /= (np.max(np.abs(attack)) + 1e-9)

    # ── الطبقة الثانية: Mid Body حسب خامة العنصر ──
    dur_mid = 0.24
    L_mid = int(dur_mid * SR)
    t_mid = np.arange(L_mid) / SR
    mat = (material or 'tech').lower()

    if mat in ('wood', 'organic'):
        f_mid = 320.0 * np.exp(-t_mid / 0.05) + 140.0
        body = np.sin(2 * np.pi * np.cumsum(f_mid) / SR) * np.exp(-t_mid / 0.07)
        mid = body + lp(rng.randn(L_mid), 0.20, 0.05) * np.exp(-t_mid / 0.015) * 0.3
    elif mat in ('glass', 'crystal'):
        body = sum(np.sin(2 * np.pi * f * t_mid) * np.exp(-t_mid / (0.05 + 0.02 * i))
                   for i, f in enumerate([1760, 2640, 3520])) * 0.4
        mid = body + lp(rng.randn(L_mid), 0.40, 0.15) * np.exp(-t_mid / 0.008) * 0.25
    elif mat in ('heavy', 'stone', 'impact'):
        f_mid = 240.0 * np.exp(-t_mid / 0.035) + 95.0
        body = np.sin(2 * np.pi * np.cumsum(f_mid) / SR) * np.exp(-t_mid / 0.08)
        mid = body + lp(rng.randn(L_mid), 0.30, 0.08) * np.exp(-t_mid / 0.012) * 0.45
    else:  # 'tech' افتراضياً
        f_mid = 440.0 * np.exp(-t_mid / 0.04) + 160.0
        fm_mod = np.sin(2 * np.pi * 320.0 * t_mid) * np.exp(-t_mid / 0.03) * 1.2
        body = np.sin(2 * np.pi * np.cumsum(f_mid) / SR + fm_mod) * np.exp(-t_mid / 0.055)
        sheen = (np.sin(2 * np.pi * 1750.0 * t_mid) + np.sin(2 * np.pi * 2620.0 * t_mid)) * np.exp(-t_mid / 0.025) * 0.25
        mid = body + sheen

    mid /= (np.max(np.abs(mid)) + 1e-9)

    # ── الطبقة الثالثة: Low Sub-bass عميق 45Hz مع اضمحلال 0.35s ──
    dur_sub = 0.75
    L_sub = int(dur_sub * SR)
    t_sub = np.arange(L_sub) / SR
    env_sub = np.exp(-t_sub / 0.35)
    # تردد أساسي 45Hz مع هارمونيك 90Hz لتعزيز السماع على شاشات وهواتف الجوال
    sub_w = (np.sin(2 * np.pi * 45.0 * t_sub) + 0.22 * np.sin(2 * np.pi * 90.0 * t_sub) * np.exp(-t_sub / 0.22)) * env_sub
    sub_w /= (np.max(np.abs(sub_w)) + 1e-9)

    # ── الدمج المتزن ──
    total_len = max(L_att, L_mid, L_sub)
    stack = np.zeros(total_len)
    stack[:L_att] += attack * 0.36
    stack[:L_mid] += mid * 0.40
    stack[:L_sub] += sub_w * 0.65
    stack /= (np.max(np.abs(stack)) + 1e-9)
    return stack

def hero_hit(t0, material='tech', gain=1.0):
    """
    إضافة الضربة الثلاثية للحظات الكبرى (Hero 3-Layer Stack):
    تدمج (Attack عالي + Mid body يمثل خامة العنصر + Low sub-bass عميق 45Hz مع اضمحلال 0.35s).
    """
    if t0 not in HERO_TIMES:
        HERO_TIMES.append(float(t0))
    stack = make_hero_sound(material=material)
    add(stack, t0, g=0.28 * gain, guard=True)
    return stack

# ── قراءة وتنفيذ المؤثرات من sfx.json ──

# 1) المؤثرات الصاعدة المقيّدة (Clamped Risers)
for item in _s.get("riser", []):
    if isinstance(item, (list, tuple)):
        te = float(item[0])
        d0 = float(item[1]) if len(item) > 1 else 0.55
    else:
        te = float(item)
        d0 = 0.55
    cd = float(np.clip(d0, 0.4, 0.7))
    r = riser(cd)
    add(r, te - cd, 0.07, guard=False)

# 2) ضربات الهيرو (Hero Hits)
for h in _s.get("hero", []) + _s.get("hero_hits", []):
    if isinstance(h, (int, float)):
        hero_hit(float(h))
    elif isinstance(h, (list, tuple)):
        t_val = float(h[0])
        mat_val = str(h[1]) if len(h) > 1 else 'tech'
        gain_val = float(h[2]) if len(h) > 2 else 1.0
        hero_hit(t_val, material=mat_val, gain=gain_val)
    elif isinstance(h, dict):
        t_val = float(h.get("t", h.get("t0", 0.0)))
        mat_val = str(h.get("material", h.get("mat", "tech")))
        gain_val = float(h.get("gain", h.get("g", 1.0)))
        hero_hit(t_val, material=mat_val, gain=gain_val)

# 3) المؤثرات التفاعلية مع احترام فجوة الصمت (Quiet Gap)
for t0 in _s.get("pop", []):
    if not in_quiet_gap(t0):
        add(pop(), t0, 0.09)

for t0 in _s.get("click", []):
    if not in_quiet_gap(t0):
        add(click(), t0, 0.08)

for item in _s.get("type", []):
    if isinstance(item, (list, tuple)):
        t0 = float(item[0])
        d0 = float(item[1]) if len(item) > 1 else 0.8
    else:
        t0 = float(item)
        d0 = 0.8
    if not in_quiet_gap(t0):
        add(typing(d0), t0, 0.06)

for t0 in _s.get("shimmer", []):
    if not in_quiet_gap(t0):
        add(shimmer(), t0, 0.05)

for t0 in _s.get("sub", []):
    add(sub(), t0, 0.22)

for t0 in _s.get("glitch", []):
    add(glitch(), t0, 0.07)

# 4) تكات العدّاد (motion-kit)
for item in _s.get("counter", []):
    if isinstance(item, (list, tuple)):
        c0 = float(item[0])
        d0 = float(item[1]) if len(item) > 1 else 1.0
    else:
        c0 = float(item)
        d0 = 1.0
    for i in range(1, 24):
        q = i / 24.0
        k = np.log2(1 / (1 - q)) / 10.0
        tc = c0 + k * d0
        if not in_quiet_gap(tc):
            add(tick(2200 + i * 40), tc, 0.09)

# 5) حركات التحريك (Whooshes & Thuds & Taps)
for t0 in _s.get("whoosh_up", []):
    if not in_quiet_gap(t0):
        add(W1, t0, 0.085)

for t0 in _s.get("whoosh_down", []):
    if not in_quiet_gap(t0):
        add(W2, t0, 0.075)

for t0 in _s.get("thud", []):
    if not in_quiet_gap(t0):
        add(TH, t0, 0.115)

for t0 in _s.get("tap", []):
    if not in_quiet_gap(t0):
        add(TP, t0, 0.075)

for item in _s.get("soft", []):
    if isinstance(item, (list, tuple)):
        t0 = float(item[0])
        g = float(item[1]) if len(item) > 1 else 0.085
    else:
        t0 = float(item)
        g = 0.085
    if not in_quiet_gap(t0):
        add(W1, t0, g)

# ── حفظ المخرجات ومعايرة الصوت ──
buf = np.clip(buf, -0.95, 0.95)
pcm = (buf * 32767).astype('<i2')
st = np.repeat(pcm[:, None], 2, axis=1).ravel()
w = wave.open(S + "sfx.wav", "wb")
w.setnchannels(2)
w.setsampwidth(2)
w.setframerate(SR)
w.writeframes(st.tobytes())
w.close()
print("sfx ok peak", round(float(np.max(np.abs(buf))), 3), "dur", round(len(pcm) / SR, 2))
