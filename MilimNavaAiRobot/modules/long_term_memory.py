# ══════════════════════════════════════════════════════════════════
#   LONG TERM MEMORY — ringkasan otomatis percakapan
#   Tiap kali riwayat personal mencapai ~30 pesan, diringkas jadi
#   2-4 kalimat (oleh LLM) dan disimpan sebagai "memori jangka panjang".
#   Saat respon, ringkasan disuntik ke prompt → Milim inget hal lama.
# ══════════════════════════════════════════════════════════════════

import json
import logging

from MilimNavaAiRobot import C, db, llm, memory
from MilimNavaAiRobot import LOGGER

log = logging.getLogger("milim.ltm")

LTR_KEY = "ltm:{chat_id}:{user_id}"
COUNT_KEY = "ltmcount:{chat_id}:{user_id}"
COMPACT_EVERY = 30      # ringkas tiap N pesan user


def _keys(chat_id, user_id):
    return (LTR_KEY.format(chat_id=chat_id, user_id=user_id),
            COUNT_KEY.format(chat_id=chat_id, user_id=user_id))


async def get_ltm(chat_id, user_id) -> str:
    key, _ = _keys(chat_id, user_id)
    return (await db.get(key)) or ""


async def add_ltm(chat_id, user_id, extra: str):
    """Tambah ringkasan baru (append, maks 2000 char — yang lama dipangkas)."""
    key, _ = _keys(chat_id, user_id)
    cur = (await db.get(key)) or ""
    new = (cur + "\n" + extra).strip()
    # pangkas baris paling lama jika terlalu panjang
    while len(new) > 2000 and "\n" in new:
        new = new.split("\n", 1)[1]
    await db.set(key, new)


async def bump_and_maybe_summarize(chat_id: int, user_id: int):
    """Panggil setelah tiap pesan user. Kalau hitungan mencapai N, ringkas."""
    _, ckey = _keys(chat_id, user_id)
    cnt = int((await db.get(ckey)) or 0) + 1
    await db.set(ckey, str(cnt))
    if cnt % COMPACT_EVERY != 0:
        return

    try:
        hist = await memory.get(chat_id, user_id, limit=COMPACT_EVERY)
        if len(hist) < 10:
            return
        old_ltm = await get_ltm(chat_id, user_id)
        convo = "\n".join(
            f"{h['role']}: {h['content'][:150]}" for h in hist[-20:])
        prompt = (
            "Ringkas fakta-fakta PENTING dan persisten dari percakapan ini "
            "(preferensi user, nama, kebiasaan, hal yang disebut berulang). "
            "Maksimal 4 kalimat, langsung poin-poin, tanpa basa-basi.\n\n"
            "PERCAKAPAN:\n" + convo)
        summary = await llm.chat([
            {"role": "system", "content":
                "Kamu asisten yang ahli meringkas percakapan menjadi "
                "memori jangka panjang yang padat."},
            {"role": "user", "content": prompt}])
        await add_ltm(chat_id, user_id, summary.strip()[:400])
        log.info(f"ltm: ringkasan tersimpan utk user {user_id}")
    except Exception as e:
        log.debug(f"summarize err: {e}")


def ltm_prompt(ltm: str) -> str:
    """Suntik ke prompt sistem — return '' kalau kosong."""
    if not ltm:
        return ""
    return ("\n\nMEMORI JANGKA PANJANG tentang user ini (fakta dari "
            "percakapan sebelumnya — pakai secara natural, jangan disebut "
            "eksplisit sebagai 'memori'):\n" + ltm.strip())
