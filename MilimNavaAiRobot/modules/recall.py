# ══════════════════════════════════════════════════════════════════
#   RECALL — proaktif mengingat hal yang user ceritakan dulu (ala
#   assistant yang benar-benar kenal orangnya):
#   1. EKSTRAKSI FAKTA: dari percakapan, simpan klaim tentang user
#      ("gue mau nonton Frieren", "kerjaan gue numpuk") → ltm:userfacts.
#   2. RE-MENTION: saat user ngobrol lagi, fakta lama yang relevan
#      di-inject + kadang (probabilistik) disuruh balik nanya natural.
#   Bukan command; jalan di belakang layar tiap percakapan.
# ══════════════════════════════════════════════════════════════════

import re
import json
import time
import logging

log = logging.getLogger("milim.recall")

try:
    from MilimNavaAiRobot import db
except Exception:
    db = None

MAX_FACTS = 40
KEY = "ltm:userfacts:{chat}:{user}"

# ── deteksi klaim tentang diri user ──────────────────────────────
CLAIM_RE = re.compile(
    r"^(?:gue|aku|saya|w)\s+(?:mau|pengen|ingin|bakal|akan|lagi|tadi|"
    r"udah|sudah|gak akan|nggak akan|pengin)\b.{6,200}|"
    r"^(?:gue|aku|saya)\s+(?:benci|suka|paling suka|gak suka|nggak suka)\b.{3,200}|"
    r"\b(?:libur|kerja|tugas|ujian|ulangan|uc|final|nikah|ultah|"
    r"ulang tahun|nonton|main|download|beli|pindah|sakit|demam|"
    r"flu|lulus|wisuda)\b", re.IGNORECASE)

QUESTION_ABOUT_PAST_RE = re.compile(
    r"\b(inget|ingat|masih inget|tau gak|tahu nggak|udah gue|yang gue "
    r"bilang|kemarin|semalam|dulu)\b", re.IGNORECASE)


def _key(chat_id, user_id) -> str:
    return KEY.format(chat=chat_id, user=user_id)


async def remember_from(chat_id, user_id, text: str):
    """Simpan klaim tentang user (dedupe, maks 40, TTL alami via list)."""
    if not text or not CLAIM_RE.search(text) or len(text) > 300:
        return
    fact = text.strip()[:220]
    if db is None:
        return
    try:
        raw = await db.get(_key(chat_id, user_id))
        arr = json.loads(raw) if raw else []
        # dedupe kasar
        if any(fact.lower()[:60] == f.get("t", "").lower()[:60] for f in arr):
            return
        arr.append({"t": fact, "ts": int(time.time())})
        await db.set(_key(chat_id, user_id), json.dumps(arr[-MAX_FACTS:]))
    except Exception as e:
        log.debug(f"recall save err: {e}")


async def get_facts(chat_id, user_id, limit=12) -> list:
    if db is None:
        return []
    try:
        raw = await db.get(_key(chat_id, user_id))
        arr = json.loads(raw) if raw else []
        return arr[-limit:]
    except Exception:
        return []


def mentions_past(text: str) -> bool:
    return bool(QUESTION_ABOUT_PAST_RE.search(text or ""))


async def maybe_inject(chat_id, user_id, user_text: str) -> str:
    """Inject fakta lama yang relevan ke konteks."""
    facts = await get_facts(chat_id, user_id)
    if not facts:
        return ""
    lines = [f"- ({time.strftime('%d %b', time.localtime(f['ts']))}) {f['t']}"
             for f in facts[-10:]]
    extra = ""
    if mentions_past(user_text):
        extra = ("\nUser sedang menanyakan hal lama — gunakan fakta-fakta "
                 "di atas untuk menjawab dengan SPESIFIK.")
    return ("\n\nINGATAN JANGKA PANJANG TENTANG USER INI (hal yang pernah "
            "dia ceritakan — boleh disebut natural kalau relevan, JANGAN "
            "dipaksa semua):\n" + "\n".join(lines) + extra)
