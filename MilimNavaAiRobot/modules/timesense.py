# ══════════════════════════════════════════════════════════════════
#   TIMESENSE — kesadaran waktu sebagai KEMAMPUAN (bukan command):
#   1. RELATIVE TIME: "besok jam 8", "3 hari lagi", "minggu depan" →
#      dihitung ke tanggal ABSOLUT (YYYY-MM-DD HH:MM) dan di-inject.
#   2. REMINDER INTENT: deteksi "ingetin aku ..." → tersimpan reminder
#      absolut + jawaban LLM memakai datanya.
#   3. TIMEZONE: seluruh hitungan pakai TZ offset dari config.
#   Ini melengkapi reminder.py (yang pakai parser sederhana) dengan
#   parser relative-time yang jauh lebih lengkap.
# ══════════════════════════════════════════════════════════════════

import re
import logging
from datetime import datetime, timedelta

log = logging.getLogger("milim.timesense")

try:
    from MilimNavaAiRobot.config import TZ_OFFSET
except Exception:
    TZ_OFFSET = 7

HARI = {"senin": 0, "selasa": 1, "rabu": 2, "kamis": 3, "jumat": 4,
        "jumat": 4, "sabtu": 5, "minggu": 6, "ahad": 6}
BULAN = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5,
         "juni": 6, "juli": 7, "agustus": 8, "september": 9,
         "oktober": 10, "november": 11, "desember": 12,
         "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
         "agu": 8, "ags": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12}

REL_RE = re.compile(
    r"\b(besok|lusa|kemarin|nanti|minggu\s*(?:depan|lalu)|bulan\s*(?:depan|lalu)|"
    r"tahun\s*(?:depan|lalu)|(?:\d+|satu|dua|tiga|empat|lima|enam|tujuh|delapan|"
    r"sembilan|sepuluh|se|beberapa)\s*(?:menit|jam|hari|minggu|bulan|tahun)\s*"
    r"(?:lagi|yang\s*lalu|kemudian)|hari\s*(?:senin|selasa|rabu|kamis|jumat|"
    r"sabtu|minggu|ahad)\s*(?:depan|ini)?)\b", re.IGNORECASE)
JAM_RE = re.compile(r"\b(?:jam\s*)?(\d{1,2})[.:](\d{2})\b|\b(?:jam\s*)?(\d{1,2})\s*(pagi|siang|sore|malam)\b",
                    re.IGNORECASE)
NUMWORD = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6,
           "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10, "se": 1,
           "beberapa": 3}


def _now() -> datetime:
    return datetime.utcnow() + timedelta(hours=TZ_OFFSET)


def _num(s: str) -> int:
    s = s.lower().strip()
    if s.isdigit():
        return int(s)
    return NUMWORD.get(s, 1)


def parse_relative(text: str):
    """Return (datetime_absolut, deskripsi) atau None."""
    t = (text or "").lower()
    now = _now()
    base = None
    m = REL_RE.search(t)
    if not m:
        return None
    frag = m.group(0)

    if "besok" in frag:
        base = now + timedelta(days=1)
    elif "lusa" in frag:
        base = now + timedelta(days=2)
    elif "kemarin" in frag:
        base = now - timedelta(days=1)
    elif "minggu depan" in frag:
        base = now + timedelta(weeks=1)
    elif "minggu lalu" in frag:
        base = now - timedelta(weeks=1)
    elif "bulan depan" in frag:
        base = now + timedelta(days=30)
    elif "bulan lalu" in frag:
        base = now - timedelta(days=30)
    elif "tahun depan" in frag:
        base = now + timedelta(days=365)
    else:
        # "X menit/jam/hari ... lagi/yang lalu"
        m2 = re.search(r"(\d+|satu|dua|tiga|empat|lima|enam|tujuh|delapan|"
                       r"sembilan|sepuluh|se|beberapa)\s*"
                       r"(menit|jam|hari|minggu|bulan|tahun)\s*"
                       r"(lagi|yang lalu|kemudian)?", t)
        if m2:
            n = _num(m2.group(1))
            unit = m2.group(2)
            past = "lalu" in (m2.group(3) or "")
            delta = {"menit": timedelta(minutes=n), "jam": timedelta(hours=n),
                     "hari": timedelta(days=n), "minggu": timedelta(weeks=n),
                     "bulan": timedelta(days=30 * n),
                     "tahun": timedelta(days=365 * n)}[unit]
            base = now - delta if past else now + delta
        else:
            # "hari senin depan"
            m3 = re.search(r"hari\s*(senin|selasa|rabu|kamis|jumat|sabtu|minggu|ahad)",
                           t)
            if m3 and "depan" in t:
                target = HARI[m3.group(1)]
                d = (target - now.weekday()) % 7
                if d == 0:
                    d = 7
                base = now + timedelta(days=d)
    if not base:
        return None

    # jam spesifik
    hm = JAM_RE.search(t)
    if hm:
        if hm.group(1):
            hh, mm = int(hm.group(1)), int(hm.group(2))
        else:
            hh = int(hm.group(3)) % 12
            period = (hm.group(4) or "").lower()
            if period in ("siang", "sore"):
                hh += 12 if hh < 12 else 0
            elif period == "malam":
                hh += 12 if hh < 12 else 0
            elif period == "pagi" and hh == 12:
                hh = 0
            mm = 0
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            base = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
            # kalau waktunya sudah lewat hari ini → esok
            if base < now:
                base += timedelta(days=1)
    return base, frag


REMIND_RE = re.compile(
    r"\b(ingetin|ingatkan|remind|bisiken|tolong ingetin)\b", re.IGNORECASE)


def is_reminder_intent(text: str) -> bool:
    return bool(REMIND_RE.search(text or "")) and bool(REL_RE.search(text or ""))


def maybe_inject(user_text: str) -> str:
    """Inject tanggal absolut untuk frasa waktu relatif di pertanyaan."""
    p = parse_relative(user_text or "")
    if not p:
        return ""
    dt, frag = p
    return (f"\n\nKONTEKS WAKTU: frasa \"{frag}\" dalam pesan user = "
            f"{dt.strftime('%A, %d %B %Y %H:%M')} (waktu lokal bot). "
            f"Pakai tanggal/waktu absolut ini di jawaban.")
