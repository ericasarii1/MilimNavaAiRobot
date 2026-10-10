# ══════════════════════════════════════════════════════════════════
#   CONTINUITY — konsistensi pendapat & cerita (ala assistant yang
#   punya "jati diri"):
#   1. OPINION LEDGER: jawaban yang mengandung pilihan/juara/pendapat
#      kuat ("juara 1 = X", "gue paling suka Y") disimpan per chat.
#   2. ANTI-FLIP: kalau user nanya hal yang SAMA lagi dan jawaban baru
#      bertentangan → instruksi ke LLM untuk konsisten ATAU bilang
#      jujur kalau mau ganti pendapat.
#   3. SELF-CORRECTION LEGIT: kalau user membantah dengan argumen,
#      boleh ganti pendapat ASAL menyebut perubahan itu secara natural.
# ══════════════════════════════════════════════════════════════════

import re
import json
import time
import logging

log = logging.getLogger("milim.continuity")

try:
    from MilimNavaAiRobot import db
except Exception:
    db = None

KEY = "ct:opinions:{chat}"
MAX_OPS = 60

# ── ekstraksi opini dari jawaban ─────────────────────────────────
OP_RE = re.compile(
    r"(?:juara\s*(?:1|satu|pertama)|nomor\s*(?:1|satu)|paling\s+(?:bagus|"
    r"best|suka|favorit|punya)|terbaik\s+(?:adalah|versi|sih)|favorit\s+"
    r"(?:gue|aku|saya)\s+(?:adalah|sih)|pilih(?:an)?\s+(?:gue|aku|saya)?)"
    r"[^\n.]{0,80}", re.IGNORECASE)


def extract_opinion(answer: str):
    m = OP_RE.search(answer or "")
    return m.group(0).strip()[:120] if m else None


async def store_opinion(chat_id, answer: str):
    op = extract_opinion(answer)
    if not op or db is None:
        return
    try:
        raw = await db.get(KEY.format(chat=chat_id))
        arr = json.loads(raw) if raw else []
        arr.append({"t": op, "ts": int(time.time())})
        await db.set(KEY.format(chat=chat_id), json.dumps(arr[-MAX_OPS:]))
    except Exception as e:
        log.debug(f"opinion save err: {e}")


# ── deteksi pertanyaan yang mirip topik opini lama ───────────────
ASK_OP_RE = re.compile(
    r"\b(juara|nomor\s*1|terbaik|paling\s+(?:bagus|suka)|favorit|pilih)\b",
    re.IGNORECASE)


def _words(s: str) -> set:
    return set(re.findall(r"[a-z0-9]{4,}", (s or "").lower()))


async def check_consistency(chat_id, user_text: str) -> str:
    """Return instruksi konsistensi kalau ada risiko kontradiksi."""
    if db is None or not ASK_OP_RE.search(user_text or ""):
        return ""
    try:
        raw = await db.get(KEY.format(chat=chat_id))
        arr = json.loads(raw) if raw else []
    except Exception:
        return ""
    if not arr:
        return ""
    qwords = _words(user_text)
    relevant = []
    for o in arr[-15:]:
        ow = _words(o["t"])
        # topik terkait kalau >=1 kata kunci bertabrakan (bukan stopword umum)
        if ow and qwords and len(ow & qwords) >= 1:
            relevant.append(o["t"])
    if not relevant:
        return ""
    return ("\n\nKONSISTENSI PENDAPAT: sebelumnya kamu pernah bilang: \"" +
            "\"; \"".join(relevant[-3:]) +
            "\". Kalau pertanyaan ini menyangkut hal yang sama, JANGAN "
            "mengganti jawaban diam-diam. Tetap konsisten — atau kalau "
            "memang mau ganti pendapat, sebutkan secara jujur dan natural "
            "kenapa berubah pikiran.")
