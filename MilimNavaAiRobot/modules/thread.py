# ══════════════════════════════════════════════════════════════════
#   THREAD — kesadaran alur topik (ala assistant yang ingat "bates
#   antar-bicara"):
#   1. TOPIC JUMP: user tiba-tiba ganti topik total di tengah obrolan
#      → bot sadar & bisa bilang natural "eh balik ke tadi—" atau
#      sekadar TAU konteksnya beda (tanpa kebingungan menyatukan).
#   2. UNANSWERED: ada pertanyaan user yang BELUM terjawab dari
#      beberapa pesan lalu → diingatkan ke LLM supaya tidak terlewat.
#   3. OPEN LOOP: janji/bot bilang "nanti gue cek" → dilacak supaya
#      dibalas nanti (loop terbuka).
# ══════════════════════════════════════════════════════════════════

import re
import json
import time
import logging

log = logging.getLogger("milim.thread")

try:
    from MilimNavaAiRobot import db
except Exception:
    db = None

KEY = "ct:thread:{chat}"
MAX_T = 20
STALE = 60 * 30        # 30 menit = topik dianggap ganti

Q_RE = re.compile(r"\?+\s*$|\b(berapa|gimana|kapan|dimana|kenapa|mengapa|"
                  r"apa itu|siapa|bisa gak|bisa nggak)\b", re.IGNORECASE)


async def _load(chat_id):
    if db is None:
        return {"topics": [], "open_q": None, "loop": None}
    try:
        raw = await db.get(KEY.format(chat=chat_id))
        return json.loads(raw) if raw else {"topics": [], "open_q": None, "loop": None}
    except Exception:
        return {"topics": [], "open_q": None, "loop": None}


async def _save(chat_id, st):
    if db is None:
        return
    try:
        await db.set(KEY.format(chat=chat_id), json.dumps(st))
    except Exception as e:
        log.debug(f"thread save err: {e}")


def _keywords(text: str) -> set:
    stop = {"yang", "dengan", "untuk", "ini", "itu", "gue", "lo", "kamu",
            "aku", "saya", "apa", "gimana", "kenapa", "dari", "kayak",
            "banget", "wkwk", "aja", "dan", "atau", "kalau", "kalo"}
    return {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", text or "")
            if w.lower() not in stop}


async def update(chat_id, user_text: str, bot_answered: bool):
    """Update jejak topik + tandai pertanyaan terbuka."""
    st = await _load(chat_id)
    now = int(time.time())
    kw = list(_keywords(user_text))[:8]
    if kw:
        st["topics"].append({"kw": kw, "ts": now})
        st["topics"] = st["topics"][-MAX_T:]
    if Q_RE.search(user_text or ""):
        st["open_q"] = {"q": (user_text or "")[:200], "ts": now}
    elif bot_answered and st.get("open_q") and now - st["open_q"]["ts"] < STALE:
        st["open_q"] = None
    await _save(chat_id, st)


async def instruction(chat_id, user_text: str) -> str:
    st = await _load(chat_id)
    now = int(time.time())
    parts = []
    # topic jump: topik sekarang beda dari sebelumnya?
    cur = _keywords(user_text)
    if cur and st["topics"] and len(st["topics"]) >= 2:
        prev = set(st["topics"][-2]["kw"])
        if prev and len(cur & prev) == 0 and now - st["topics"][-2]["ts"] < STALE:
            last = ", ".join(list(prev)[:4])
            parts.append(
                f"User baru saja berganti topik total (dari: {last}). "
                "Boleh sadar transisinya secara natural (sekali saja, "
                "jangan berlebihan).")
    # pertanyaan lama belum terjawab?
    oq = st.get("open_q")
    if oq and now - oq["ts"] > 90:
        parts.append(
            f"PENTING: pertanyaan user beberapa pesan lalu belum "
            f"terjawab: \"{oq['q']}\" — kalau masih relevan, jawab juga.")
    if parts:
        return "\n\nTHREAD AWARENESS:\n- " + "\n- ".join(parts)
    return ""
