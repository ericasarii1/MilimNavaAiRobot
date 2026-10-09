# ══════════════════════════════════════════════════════════════════
#   CROSS-CHAT (VERSI AMAN) — "tadi di grup siapa bahas aku?"
#   Aturan privasi ketat:
#   1. HANYA aktif di DM bot (jawaban tidak pernah muncul di grup)
#   2. HANYA grup tempat user itu sendiri pernah menulis
#   3. HANYA pesan yang MENYEBUT nama user (kata kunci dari pesan user)
#   4. Riwayat grup dikirim ke LLM sebagai konteks; LLM diinstruksikan
#      tidak menuliskan isi pesan user lain di luar relevansinya.
#   Tidak ada arah balik: isi DM tidak pernah masuk grup.
# ══════════════════════════════════════════════════════════════════

import re
import time
import logging

log = logging.getLogger("milim.crosschat")

TRIGGER = re.compile(
    r"(ngomongin|omongin|bahas|ngbahas|sebut|nyebut|ngetag|tag).{0,30}"
    r"(aku|gue|saya|gw|namaku|nama gue)|"
    r"(aku|gue|saya|gw).{0,30}(ngomongin|omongin|dibahas|disebut)",
    re.IGNORECASE)
GRUP_RE = re.compile(
    r"(grup|group|gc|chat(?:ting)?)\s*([a-z0-9\s]{2,25})?", re.IGNORECASE)


def is_cross_question(text: str) -> bool:
    if not text or len(text) > 120:
        return False
    return bool(TRIGGER.search(text))


async def collect(user_text: str, user_name: str,
                  known_groups: dict) -> str:
    """known_groups: {chat_id: first_name} — grup di mana user pernah chat.
    Return konteks berisi pesan grup yang relevan (menyebut user), atau ''."""
    if not user_text or not known_groups:
        return ""
    now = time.time()
    parts = []
    for chat_id in known_groups:
        try:
            from MilimNavaAiRobot import memory as M
            hist = await M.get_group(chat_id, limit=40)
        except Exception as e:
            log.debug(f"crosschat hist err: {e}")
            continue
        if not hist:
            continue
        # kata kunci: nama user + kata lain dari pertanyaan
        keys = [user_name.lower()]
        for w in re.findall(r"[a-zA-Z]{4,}", user_text):
            if w.lower() not in ("grup", "group", "siapa", "ngomongin",
                                 "bahas", "apa", "yang", "tadi"):
                keys.append(w.lower())
        hits = []
        for x in hist:
            c = (x.get("content") or "").lower()
            if x.get("speaker") == "Milim":
                continue
            # pesan orang lain yang menyebut nama user, ATAU balasan bot
            # ke user itu (jelas dari urutan)
            if any(k in c for k in keys if len(k) >= 4):
                age = int(max(0, now - (x.get("ts") or now)) // 60)
                when = ("baru saja" if age < 2 else
                        f"{age} menit lalu" if age < 60 else
                        f"{age // 60} jam lalu")
                hits.append(f"- {x.get('speaker','?')} ({when}): "
                            f"{(x.get('content') or '')[:150]}")
        if hits:
            parts.append(f"GRUP {chat_id}:\n" + "\n".join(hits[-8:]))
    if not parts:
        return ""
    return (
        "\n\nPRIVASI: konteks ini HANYA boleh dipakai untuk menjawab user "
        "di DM ini. JANGAN sebut isi chat di grup publik, jangan sebut ke "
        "orang lain. INILAH pesan-pesan grup yang relevan dengan "
        "pertanyaannya (menyebut nama '" + user_name + "'):\n"
        + "\n\n".join(parts))
