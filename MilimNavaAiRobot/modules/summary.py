# ══════════════════════════════════════════════════════════════════
#   SUMMARY — rangkum riwayat percakapan on-demand
#   "Milim rangkum" / "Milim rangkum obrolan"
#   Grup: merangkum thread grup. Private: merangkum riwayat personal.
# ══════════════════════════════════════════════════════════════════

import re
import logging

from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import C, app, db, llm, memory, state
from MilimNavaAiRobot.modules import prompts as P
from MilimNavaAiRobot.modules.helpers import humanize_delta
import time

log = logging.getLogger("milim.summary")

SUMMARY_RE = re.compile(r"\b(rangkum|ringkas|summarize)\b", re.IGNORECASE)


@app.on_message(filters.group | filters.private, group=1)
async def handle_summary(client, message: Message):
    if not message.text or not message.from_user:
        return
    text = message.text.strip()
    if not SUMMARY_RE.search(text) or len(text) > 60:
        return

    chat_id = message.chat.id
    st = await state.get(chat_id)
    is_group = chat_id != message.from_user.id and \
        message.chat.type != enums.ChatType.PRIVATE

    # kumpulkan bahan
    if is_group:
        hist = await memory.get_group(chat_id, limit=40)
        convo = "\n".join(
            f"{h.get('speaker','?')} ({humanize_delta(time.time()-h.get('ts',time.time()))}): "
            f"{h['content'][:200]}" for h in hist)
        label = "obrolan grup"
    else:
        hist = await memory.get(chat_id, message.from_user.id, limit=40)
        convo = "\n".join(
            f"{h['role']} ({humanize_delta(time.time()-h.get('ts',time.time()))}): "
            f"{h['content'][:200]}" for h in hist)
        label = "percakapan kita"

    if len(hist) < 4:
        await message.reply_text(
            "Belum cukup percakapan untuk dirangkum."
            if st["conv"] == "formal" else
            "Hmm, baru dikit sih obrolannya, nanti aja dirangkum 😅")
        return

    try:
        answer = await llm.chat([
            {"role": "system",
             "content": P.PROMPTS[st["conv"]].format(owner_id=C.OWNER_ID) +
                        "\n\nTugas spesifik sekarang: RANGKUM percakapan "
                        "berikut dalam poin-poin singkat (maks 6 poin) — "
                        "topik, keputusan, dan hal penting yang disebut. "
                        "Tetap pakai kepribadianmu."},
            {"role": "user", "content": f"Rangkum {label} ini:\n\n{convo}"},
        ])
        await message.reply_text(f"📋 **Rangkuman {label}:**\n\n{answer}",
                                 quote=True)
    except Exception as e:
        log.debug(f"summary err: {e}")
        await message.reply_text(
            "Maaf, gagal merangkum. Coba lagi nanti."
            if st["conv"] == "formal" else
            "Aduh gagal ngerangkum 😥 coba lagi ya!")
