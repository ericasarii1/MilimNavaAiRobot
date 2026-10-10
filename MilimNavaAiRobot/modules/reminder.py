# ══════════════════════════════════════════════════════════════════
#   REMINDER — pengingat tersimpan di DB, dicek background tiap menit
#   Command: "Milim ingetin aku [waktu] [pesan]"
#   Contoh:  "Milim ingetin aku 10 menit lagi minum air"
#            "Milim reminder 1 jam rapat"
# ══════════════════════════════════════════════════════════════════

import re
import time
import asyncio
import logging

from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import C, app, db, memory, state
from MilimNavaAiRobot.modules import prompts as P
from MilimNavaAiRobot.modules.helpers import now_str

log = logging.getLogger("milim.reminder")

# "10 menit" | "1 jam" | "30 detik" | "2 hari"
DUR_RE = re.compile(
    r"(\d+)\s*(detik|menit|mnt|jam|hari)", re.IGNORECASE)
REMINDER_RE = re.compile(
    r"\b(ingetin|ingatkan|reminder|remind)\b", re.IGNORECASE)


def parse_reminder(text: str):
    """Return (durasi_detik, pesan) atau None."""
    if not REMINDER_RE.search(text):
        return None
    m = DUR_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    mult = {"detik": 1, "menit": 60, "mnt": 60,
            "jam": 3600, "hari": 86400}[unit]
    duration = n * mult
    if duration < 5 or duration > 86400 * 7:
        return None
    # pesan = teks setelah durasi
    tail = text[m.end():].strip()
    tail = re.sub(r"^(lagi|nanti|kemudian)[\s,]*", "", tail,
                  flags=re.IGNORECASE)
    return duration, tail or "pengingat"


async def _reminder_loop():
    """Cek reminder yang jatuh tempo tiap 20 detik."""
    while True:
        try:
            raw = await db.get("reminders:all")
            import json
            items = json.loads(raw) if raw else []
            now = time.time()
            due = [r for r in items if r["due"] <= now]
            if due:
                items = [r for r in items if r["due"] > now]
                import json as _j
                await db.set("reminders:all", _j.dumps(items))
                for r in due:
                    st = await state.get(r["chat_id"])
                    if st["conv"] == "formal":
                        msg = (f"⏰ Pengingat: {r['text']}\n"
                               f"(diatur {r['set_when']})")
                    else:
                        msg = f"⏰ Eh, waktunya! {r['text']} (yang kamu mintain tadi ✨)"
                    try:
                        await app.send_message(r["chat_id"], msg)
                    except Exception as e:
                        log.debug(f"kirim reminder gagal: {e}")
        except Exception as e:
            log.debug(f"reminder loop err: {e}")
        await asyncio.sleep(20)


_started = False


@app.on_message(filters.group | filters.private | filters.bot, group=1)
async def handle_reminder(client, message: Message):
    global _started
    # jalankan background loop sekali
    if not _started:
        _started = True
        asyncio.create_task(_reminder_loop())

    if not message.text:
        return
    parsed = parse_reminder(message.text)
    if not parsed:
        return

    duration, rtext = parsed
    import json
    raw = await db.get("reminders:all")
    items = json.loads(raw) if raw else []
    items.append({
        "chat_id": message.chat.id,
        "user": message.from_user.first_name if message.from_user else "?",
        "text": rtext,
        "due": time.time() + duration,
        "set_when": now_str(),
    })
    await db.set("reminders:all", json.dumps(items))

    st = await state.get(message.chat.id)
    menit = duration // 60
    label = (f"{duration} detik" if duration < 60 else
             f"{menit} menit" if duration < 3600 else
             f"{duration // 3600} jam" if duration < 86400 else
             f"{duration // 86400} hari")
    if st["conv"] == "formal":
        reply = (f"Baik, pengingat telah dibuat.\n"
                 f"• Pesan: {rtext}\n"
                 f"• Waktu: {label} dari sekarang")
    else:
        reply = f"Oke! Gue ingetin \"{rtext}\" dalam {label} ya ⏰✨"
    await message.reply_text(reply, quote=True)
