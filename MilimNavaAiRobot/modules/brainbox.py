# ══════════════════════════════════════════════════════════════════
#   BRAINBOX — kemampuan otak tambahan (semua lokal, tanpa API):
#   1. ZONA WAKTU: "jam 3 sore di Tokyo berapa di Jakarta?"
#   2. KONVERSI SATUAN: km/mil, kg/lb, °C/°F, liter/galon, dll
#   3. KODE: user kirim potongan kode → instruksi analisis proper
#   Hasil di-inject ke konteks → jawaban presisi, bukan tebakan.
# ══════════════════════════════════════════════════════════════════

import re
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("milim.brainbox")

# ── 1. zona waktu ─────────────────────────────────────────────────
CITY_TZ = {
    "jakarta": "Asia/Jakarta", "bandung": "Asia/Jakarta",
    "medan": "Asia/Jakarta", "surabaya": "Asia/Jakarta",
    "makassar": "Asia/Makassar", "bali": "Asia/Makassar",
    "denpasar": "Asia/Makassar", "jayapura": "Asia/Jayapura",
    "tokyo": "Asia/Tokyo", "osaka": "Asia/Tokyo",
    "seoul": "Asia/Seoul", "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai", "singapore": "Asia/Singapore",
    "singapura": "Asia/Singapore", "hongkong": "Asia/Hong_Kong",
    "taipei": "Asia/Taipei", "bangkok": "Asia/Bangkok",
    "manila": "Asia/Manila", "kuala lumpur": "Asia/Kuala_Lumpur",
    "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata",
    "dubai": "Asia/Dubai", "riyadh": "Asia/Riyadh",
    "istanbul": "Europe/Istanbul", "moscow": "Europe/Moscow",
    "london": "Europe/London", "paris": "Europe/Paris",
    "berlin": "Europe/Berlin", "amsterdam": "Europe/Amsterdam",
    "madrid": "Europe/Madrid", "rome": "Europe/Rome",
    "cairo": "Africa/Cairo", "jeddah": "Asia/Riyadh",
    "new york": "America/New_York", "washington": "America/New_York",
    "boston": "America/New_York", "toronto": "America/Toronto",
    "chicago": "America/Chicago", "dallas": "America/Chicago",
    "denver": "America/Denver", "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles", "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles", "vegas": "America/Los_Angeles",
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland", "sao paulo": "America/Sao_Paulo",
    "mecca": "Asia/Riyadh", "makkah": "Asia/Riyadh",
}

TZ_RE = re.compile(
    r"(jam|pukul|waktu)\s+(\d{1,2})(?:[.:](\d{2}))?\s*"
    r"(pagi|siang|sore|malam)?\s*(?:di|in)\s+([a-z\s]{3,20}?)\s*"
    r"(?:berapa|itu|adalah|\?|$)", re.IGNORECASE)
CONV_RE = re.compile(
    r"(?:berapa|di)\s+([a-z\s]{3,20}?)\s*[\?\.]?\s*$", re.IGNORECASE)


def _parse_hour(h: int, m: int, tod: str) -> tuple:
    if not tod:
        return h, m
    tod = tod.lower()
    if tod == "pagi" and h == 12:
        h = 0
    elif tod in ("siang", "sore") and h < 12:
        h += 12
    elif tod == "malam" and h < 12:
        h += 12
    return h, m


def tz_convert(text: str) -> str:
    m = TZ_RE.search(text or "")
    if not m:
        return ""
    h = int(m.group(2)); mi = int(m.group(3) or 0); tod = m.group(4)
    city_a = m.group(5).strip().lower()
    # kota tujuan: setelah 'berapa di X' kalau ada
    m2 = re.search(r"berapa\s*(?:di|in)?\s*([a-z\s]{3,20}?)\s*[\?\.]?\s*$",
                   text, re.IGNORECASE)
    city_b = m2.group(1).strip().lower() if m2 else "jakarta"
    if city_a == city_b:
        return ""
    ta = CITY_TZ.get(city_a) or CITY_TZ.get(city_a.split()[-1])
    tb = CITY_TZ.get(city_b) or CITY_TZ.get(city_b.split()[-1])
    if not ta or not tb:
        return ""
    try:
        h, mi = _parse_hour(h, mi, tod or "")
        now = datetime.now(ZoneInfo(ta)).replace(
            hour=h, minute=mi, second=0, microsecond=0)
        there = now.astimezone(ZoneInfo(tb))
        diff = there.hour - now.hour
        out = (f"KONVERSI ZONA WAKTU (hitung pasti, pakai apa adanya):\n"
               f"- {h:02d}:{mi:02d} di {city_a.title()} = "
               f"{there.hour:02d}:{there.minute:02d} di {city_b.title()} "
               f"(selisih {diff:+d} jam)")
        return out
    except Exception as e:
        log.debug(f"tz err: {e}")
        return ""


# ── 2. konversi satuan ────────────────────────────────────────────
NUM = r"(\d+(?:[.,]\d+)?)"
UNIT_CONV = [
    # (regex, fungsi nilai→hasil teks)
    (re.compile(NUM + r"\s*(km|kilometer)\s*(?:ke|=|to)\s*(mil|miles|mile)",
                re.I), lambda v: f"{v} km = {v*0.621371:.2f} mil"),
    (re.compile(NUM + r"\s*(mil|miles|mile)\s*(?:ke|=|to)\s*(km|kilometer)",
                re.I), lambda v: f"{v} mil = {v/0.621371:.2f} km"),
    (re.compile(NUM + r"\s*(kg|kilogram)\s*(?:ke|=|to)\s*(lb|pound|lbs)",
                re.I), lambda v: f"{v} kg = {v*2.20462:.2f} lb"),
    (re.compile(NUM + r"\s*(lb|lbs|pound)\s*(?:ke|=|to)\s*(kg|kilogram)",
                re.I), lambda v: f"{v} lb = {v/2.20462:.2f} kg"),
    (re.compile(NUM + r"\s*°?\s*c(?:elcius|elsius)?\s*(?:ke|=|to)\s*"
                r"(?:°?\s*)?f(?:ahrenheit)?\b", re.I),
     lambda v: f"{v}°C = {v*9/5+32:.1f}°F"),
    (re.compile(NUM + r"\s*°?\s*f(?:ahrenheit)?\s*(?:ke|=|to)\s*"
                r"(?:°?\s*)?c(?:elcius|elsius)?\b", re.I),
     lambda v: f"{v}°F = {(v-32)*5/9:.1f}°C"),
    (re.compile(NUM + r"\s*(cm|sentimeter)\s*(?:ke|=|to)\s*(inci|inch)",
                re.I), lambda v: f"{v} cm = {v/2.54:.2f} inci"),
    (re.compile(NUM + r"\s*(inci|inch)\s*(?:ke|=|to)\s*(cm|sentimeter)",
                re.I), lambda v: f"{v} inci = {v*2.54:.2f} cm"),
    (re.compile(NUM + r"\s*(liter|l)\b\s*(?:ke|=|to)\s*(galon|gallon)",
                re.I), lambda v: f"{v} liter = {v*0.264172:.2f} galon"),
    (re.compile(NUM + r"\s*(m)\b\s*(?:ke|=|to)\s*(ft|feet|kaki)\b", re.I),
     lambda v: f"{v} m = {v*3.28084:.2f} ft"),
]


def unit_convert(text: str) -> str:
    for rx, fn in UNIT_CONV:
        m = rx.search(text or "")
        if m:
            try:
                v = float(m.group(1).replace(",", "."))
                return (f"KONVERSI SATUAN (hitung pasti):\n- {fn(v)}")
            except Exception:
                continue
    return ""


# ── 3. kode ───────────────────────────────────────────────────────
CODE_HINTS = re.compile(
    r"(def |function |class |import |const |var |let |=>|\{\}|;|"
    r"print\(|console\.log|SELECT |npm |pip |git |Traceback|Error)", re.M)
CODE_LANG = re.compile(r"\b(python|javascript|typescript|java|c\+\+|c#|"
                       r"golang|php|rust|kotlin|swift|sql|html|css|dart)\b",
                       re.I)


def code_note(text: str) -> str:
    """Potongan kode terdeteksi → instruksi jawaban teknis yang benar."""
    if not text or len(text) < 40:
        return ""
    looks_code = (text.count("\n") >= 2 and CODE_HINTS.search(text)) or \
        text.strip().startswith(("```", "def ", "class ", "import ", "const "))
    if not looks_code:
        return ""
    lang = CODE_LANG.search(text)
    lang_s = lang.group(1) if lang else ""
    return (f"\n\nATURAN ANALISIS KODE{(' (' + lang_s + ')') if lang_s else ''}:\n"
            "- Baca kodenya dengan teliti SEBELUM menjawab; jangan asumsikan.\n"
            "- Kalau ada bug, tunjuk baris mana dan kenapa, kasih versi "
            "perbaikan dalam blok kode.\n"
            "- Jelaskan singkat dulu apa yang dilakukan kodenya, baru analisis.\n"
            "- Jangan mengarang perilaku library; kalau ragu, bilang perlu "
            "dicek dokumentasinya.")


def maybe_inject(text: str) -> str:
    """Deteksi semua kemampuan lokal; return konteks untuk system prompt."""
    out = []
    for fn in (tz_convert, unit_convert):
        try:
            r = fn(text)
            if r:
                out.append(r)
        except Exception as e:
            log.debug(f"brainbox err: {e}")
    try:
        r = code_note(text)
        if r:
            out.append(r)
    except Exception:
        pass
    return ("\n\n" + "\n".join(out)) if out else ""
