# ══════════════════════════════════════════════════════════════════
#   SCHEDULER — fitur proaktif (bot nyapa duluan)
#   1. DAILY DIGEST : tiap pagi kirim cuaca + berita + reminder + sapaan
#   2. REMINDER loop sudah ada di reminder.py (dipakai bersama)
#   Command:
#     "Milim digest on"        → aktifkan digest harian (jam 7 default)
#     "Milim digest jam 8"     → set jam kirim
#     "Milim digest off"       → matikan
# ══════════════════════════════════════════════════════════════════

import re
import json
import time
import asyncio
import logging

from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import C, app, db, llm, state
from MilimNavaAiRobot.modules import prompts as P
from MilimNavaAiRobot.modules.helpers import now_str

log = logging.getLogger("milim.scheduler")

DIGEST_KEY = "digest:{chat_id}"
DIGEST_RE = re.compile(r"\b(digest|rangkuman pagi|sapaan pagi)\b", re.I)
HOUR_RE = re.compile(r"\bjam\s+(\d{1,2})\b", re.I)


def _key(chat_id):
    return DIGEST_KEY.format(chat_id=chat_id)


async def get_digest_conf(chat_id: int) -> dict:
    raw = await db.get(_key(chat_id))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {"on": False, "hour": 7, "last_sent": ""}


async def save_digest_conf(chat_id: int, conf: dict):
    await db.set(_key(chat_id), json.dumps(conf))


async def build_digest(chat_id: int) -> str:
    """Bangun isi digest: cuaca + berita + reminder + sapaan personal."""
    from MilimNavaAiRobot.modules import web_search as WS
    st = await state.get(chat_id)
    formal = st["conv"] == "formal"
    parts = []

    # cuaca
    try:
        w = await WS._weather("Jakarta")
        if w:
            parts.append(("☀️ Cuaca: " if not formal else "Cuaca: ") + w)
    except Exception:
        pass

    # berita
    try:
        news = await WS._news("berita Indonesia hari ini", limit=4)
        if news:
            parts.append(("📰 Berita hari ini:\n" if not formal
                          else "Berita terkini:\n") + news)
    except Exception:
        pass

    # reminder hari ini
    try:
        raw = await db.get("reminders:all")
        items = json.loads(raw) if raw else []
        now = time.time()
        soon = [r for r in items
                if r["chat_id"] == chat_id and r["due"] - now < 86400
                and r["due"] > now]
        if soon:
            lines = "\n".join(
                f"• {r['text']} ({int((r['due']-now)//60)} menit lagi)"
                for r in soon[:5])
            parts.append(("⏰ Pengingat hari ini:\n" if not formal
                          else "Pengingat:\n") + lines)
    except Exception:
        pass

    body = "\n\n".join(parts)
    if not body:
        return ""

    # sapaan personal via LLM
    try:
        greet = await llm.chat([
            {"role": "system", "content":
                ("Buat sapaan pagi singkat (1-2 kalimat) yang hangat dan "
                 "personal dalam bahasa Indonesia santai gaul. Langsung isi, "
                 "tanpa preamble." if not formal else
                 "Buat sapaan pagi singkat (1-2 kalimat) yang sopan dalam "
                 "bahasa Indonesia formal. Langsung isi, tanpa preamble.")},
            {"role": "user", "content": f"Waktu sekarang: {now_str()}"}
        ])
        head = greet.strip() if greet else ("Selamat pagi!" if not formal
                                            else "Selamat pagi.")
    except Exception:
        head = "Selamat pagi! ☀️" if not formal else "Selamat pagi."

    return f"{head}\n\n{body}"


async def _digest_loop():
    """Cek tiap menit: apakah ada chat yang waktunya kirim digest."""
    while True:
        try:
            # scan semua conf digest (pola key: digest:<chat_id>)
            # db tak punya list_key → simpan indeks terpisah
            raw_idx = await db.get("digest:index")
            idx = json.loads(raw_idx) if raw_idx else []
            hour_now = time.localtime(time.time() + C.TZ_OFFSET * 3600).tm_hour
            day = time.strftime("%Y-%m-%d",
                                time.localtime(time.time() + C.TZ_OFFSET * 3600))
            for chat_id in idx:
                conf = await get_digest_conf(chat_id)
                if not conf.get("on"):
                    continue
                if conf.get("hour", 7) != hour_now:
                    continue
                if conf.get("last_sent") == day:
                    continue
                body = await build_digest(chat_id)
                if body:
                    try:
                        await app.send_message(chat_id, body)
                        conf["last_sent"] = day
                        await save_digest_conf(chat_id, conf)
                    except Exception as e:
                        log.debug(f"digest kirim err {chat_id}: {e}")
        except Exception as e:
            log.debug(f"digest loop err: {e}")
        await asyncio.sleep(60)


_started = False


@app.on_message(filters.group | filters.private, group=1)
async def handle_digest_cmd(client, message: Message):
    global _started
    if not _started:
        _started = True
        asyncio.create_task(_digest_loop())

    if not message.text:
        return
    t = message.text.strip()
    if not DIGEST_RE.search(t) or len(t) > 40:
        return

    chat_id = message.chat.id
    conf = await get_digest_conf(chat_id)
    st = await state.get(chat_id)
    formal = st["conv"] == "formal"

    # index (agar loop tahu chat mana yang perlu dicek)
    raw_idx = await db.get("digest:index")
    idx = json.loads(raw_idx) if raw_idx else []
    if chat_id not in idx:
        idx.append(chat_id)
        await db.set("digest:index", json.dumps(idx))

    low = t.lower()
    if "off" in low or "mati" in low:
        conf["on"] = False
        await save_digest_conf(chat_id, conf)
        await message.reply_text(
            "Digest harian dimatikan."
            if formal else "Oke, sapaan pagi otomatis gue matiin 👋", quote=True)
        return

    m = HOUR_RE.search(low)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            conf["hour"] = h
    conf["on"] = True
    await save_digest_conf(chat_id, conf)
    await message.reply_text(
        f"Digest harian aktif. Akan dikirim tiap jam {conf['hour']:02d}:00."
        if formal else
        f"Sip! Tiap jam {conf['hour']:02d}:00 gue bakal kirim "
        f"rangkuman pagi + cuaca + berita ke sini ☀️", quote=True)
