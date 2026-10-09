# ══════════════════════════════════════════════════════════════════
#   NOTES — catatan per user, tersimpan permanen di DB
#   "Milim catat: ..."      → simpan
#   "Milim catatan"         → lihat semua
#   "Milim hapus catatan 2" → hapus nomor
# ══════════════════════════════════════════════════════════════════

import re
import json
import logging

from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import C, app, db, state
from MilimNavaAiRobot.modules import prompts as P
from MilimNavaAiRobot.modules.helpers import now_str

log = logging.getLogger("milim.notes")

NOTE_ADD = re.compile(r"\b(catat)\s*[:\s]\s*(.+)", re.IGNORECASE)
NOTE_LIST = re.compile(r"\b(catatan|lihat catatan|daftar catatan)\b"
                       r"\s*$", re.IGNORECASE)
NOTE_DEL = re.compile(r"\b(hapus catatan)\s*(\d+)", re.IGNORECASE)
MAX_NOTES = 50


def _key(user_id):
    return f"notes:{user_id}"


async def _get(user_id):
    raw = await db.get(_key(user_id))
    return json.loads(raw) if raw else []


async def _set(user_id, notes):
    await db.set(_key(user_id), json.dumps(notes))


@app.on_message(filters.group | filters.private, group=1)
async def handle_notes(client, message: Message):
    if not message.text or not message.from_user:
        return
    text = message.text.strip()
    user_id = message.from_user.id
    st = await state.get(message.chat.id)
    formal = st["conv"] == "formal"

    # ── tambah catatan ──
    m = NOTE_ADD.match(text)
    if m and m.start() < 20:   # "Milim catat: ..." di awal
        notes = await _get(user_id)
        if len(notes) >= MAX_NOTES:
            await message.reply_text(
                "Catatan sudah penuh (50). Hapus beberapa dulu ya."
                if formal else
                "Waduh catatanmu udah penuh (50) 😅 Hapus dulu yang lama ya!")
            return
        notes.append({"text": m.group(2).strip()[:500],
                      "when": now_str()})
        await _set(user_id, notes)
        await message.reply_text(
            f"Catatan #{len(notes)} tersimpan."
            if formal else
            f"Oke, gue catat! (#{len(notes)}) 📝")
        return

    # ── lihat catatan ──
    if NOTE_LIST.search(text) and len(text) < 40:
        notes = await _get(user_id)
        if not notes:
            await message.reply_text(
                "Belum ada catatan."
                if formal else
                "Belum ada catatan nih. Bilang aja \"Milim catat: ...\" 📝")
            return
        lines = [f"{i+1}. {n['text']}  ({n['when']})"
                 for i, n in enumerate(notes)]
        await message.reply_text("📄 Catatanmu:\n" + "\n".join(lines))
        return

    # ── hapus catatan ──
    m = NOTE_DEL.search(text)
    if m:
        idx = int(m.group(2)) - 1
        notes = await _get(user_id)
        if 0 <= idx < len(notes):
            removed = notes.pop(idx)
            await _set(user_id, notes)
            await message.reply_text(
                f"Catatan \"{removed['text'][:50]}\" telah dihapus."
                if formal else
                f"Sip, catatannya udah gue hapus 🗑️")
        else:
            await message.reply_text(
                "Nomor catatan tidak ditemukan."
                if formal else
                "Hmm, nomor catatannya nggak ada tuh 🤔")
        return
