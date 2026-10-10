# ══════════════════════════════════════════════════════════════════
#   PERSONA — kepribadian tambahan yang bisa diatur owner
#   "Milim dari sekarang panggil gue bos"     → dipanggil "bos"
#   "Milim bio kamu: asisten yang sarkas"     → masuk prompt
#   "Milim reset persona"                     → kembalikan awal
# ══════════════════════════════════════════════════════════════════

import re
import json
import logging

from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import C, app, db, state

log = logging.getLogger("milim.persona")

CALLME_RE = re.compile(r"\b(panggil (gue|aku|saya|gw))\s+(.+)", re.IGNORECASE)
BIO_RE = re.compile(r"\b(bio kamu|karakter kamu|kepribadian kamu)\s*[:\-]?\s*(.+)",
                    re.IGNORECASE)
RESET_RE = re.compile(r"\breset persona\b", re.IGNORECASE)
PERSONA_KEY = "persona:global"


async def get_persona() -> dict:
    raw = await db.get(PERSONA_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


async def set_persona(**kw):
    p = await get_persona()
    p.update(kw)
    await db.set(PERSONA_KEY, json.dumps(p))
    return p


def persona_prompt(p: dict) -> str:
    """Bagian prompt tambahan dari persona — return '' jika kosong."""
    parts = []
    if p.get("callme"):
        parts.append(f"Panggil pengguna dengan sebutan: \"{p['callme']}\".")
    if p.get("bio"):
        parts.append(f"Karakter tambahan yang HARUS dipegang: {p['bio']}")
    return ("\n\nPERSONA TAMBAHAN (dari owner — WAJIB diikuti):\n- "
            + "\n- ".join(parts)) if parts else ""


@app.on_message(filters.private | filters.bot, group=1)
async def handle_persona(client, message: Message):
    if not message.text or not message.from_user:
        return
    if message.from_user.id != C.OWNER_ID:
        return
    text = message.text.strip()

    if RESET_RE.search(text) and len(text) < 30:
        await db.delete(PERSONA_KEY)
        st = await state.get(message.chat.id)
        await message.reply_text(
            "Persona dikembalikan ke bawaan."
            if st["conv"] == "formal" else
            "Oke, persona udah gue reset ke awal ✨")
        return

    m = CALLME_RE.search(text)
    if m and len(text) < 100:
        callme = m.group(3).strip().strip('"')[:50]
        await set_persona(callme=callme)
        st = await state.get(message.chat.id)
        await message.reply_text(
            f"Baik, mulai sekarang Anda akan dipanggil \"{callme}\"."
            if st["conv"] == "formal" else
            f"Sip! Mulai sekarang gue panggil lo \"{callme}\" ya 😄")
        return

    m = BIO_RE.search(text)
    if m and len(text) < 300:
        bio = m.group(2).strip().strip('"')[:300]
        await set_persona(bio=bio)
        st = await state.get(message.chat.id)
        await message.reply_text(
            "Karakter tambahan telah disimpan."
            if st["conv"] == "formal" else
            f"Gotcha! Karakter baru: {bio} ✨")
        return
