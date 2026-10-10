# ══════════════════════════════════════════════════════════════════
#   VOICE — obrolan suara dua arah
#   STT: voice note user → teks (Groq Whisper — gratis; aktif kalau
#        GROQ_API_KEY di-set di config/env. Tanpa key: fallback info.)
#   TTS: jawaban Milim → voice note (edge-tts, gratis, suara Indonesia)
#   Perilaku: user kirim VOICE → Milim balas PAKAI SUARA juga.
#             (owner bisa matikan: "Milim teks saja")
# ══════════════════════════════════════════════════════════════════

import os
import io
import json
import asyncio
import tempfile
import logging

from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import C, app, db, state

log = logging.getLogger("milim.voice")

# ── konfigurasi ──
GROQ_API_KEY = getattr(C, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MODEL = "whisper-large-v3"
TTS_VOICE_FORMAL = "id-ID-ArdiNeural"      # pria formal
TTS_VOICE_SANTAI = "id-ID-GadisNeural"     # wanita santai
TTS_MAX_CHARS = 900
VOICE_MODE_KEY = "voice_mode:{chat_id}"    # "auto" | "teks"


# ─────────────────────────── STT ───────────────────────────
async def speech_to_text(client, voice) -> str:
    """Voice note → teks. Coba SEMUA provider API key yang ada
    (endpoint /audio/transcriptions), lalu GROQ_API_KEY khusus bila di-set."""
    try:
        import aiohttp
        raw = await client.download_media(voice.file_id, in_memory=True)
        data = raw if isinstance(raw, bytes) else raw.getbuffer().tobytes()
    except Exception as e:
        log.debug(f"voice dl err: {e}")
        return ""

    # 1) semua provider LLM yang aktif (lightvela, openrouter, dll)
    try:
        from MilimNavaAiRobot import llm as _llm
        txt = await _llm.transcribe(data)
        if txt:
            return txt
    except Exception as e:
        log.debug(f"llm.transcribe err: {e}")

    # 2) fallback: GROQ key khusus (kalau di-set)
    if GROQ_API_KEY:
        try:
            form = aiohttp.FormData()
            form.add_field("file", data,
                           filename="voice.ogg", content_type="audio/ogg")
            form.add_field("model", STT_MODEL)
            form.add_field("language", "id")
            async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=60)) as ses:
                async with ses.post(GROQ_STT_URL, data=form,
                                    headers={"Authorization":
                                             f"Bearer {GROQ_API_KEY}"}) as resp:
                    if resp.status == 200:
                        d = await resp.json()
                        return (d.get("text") or "").strip()
                    log.debug(f"groq stt {resp.status}")
        except Exception as e:
            log.debug(f"groq stt err: {e}")
    return ""


# ─────────────────────────── TTS ───────────────────────────
async def text_to_speech(text: str, formal: bool) -> bytes | None:
    """Teks → mp3 bytes (edge-tts, gratis)."""
    text = text.strip()
    if len(text) > TTS_MAX_CHARS:
        text = text[:TTS_MAX_CHARS] + "…"
    # buang markdown biar nggak dibaca "bintang bintang"
    import re
    text = re.sub(r"[*_`~#\[\]()]", "", text)
    try:
        import edge_tts
        voice = TTS_VOICE_FORMAL if formal else TTS_VOICE_SANTAI
        c = edge_tts.Communicate(text, voice)
        buf = io.BytesIO()
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue() or None
    except Exception as e:
        log.debug(f"tts err: {e}")
        return None


async def reply_voice(message: Message, text: str, formal: bool,
                      quote=True):
    mp3 = await text_to_speech(text, formal)
    if not mp3:
        await message.reply_text(text, quote=quote)
        return
    f = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    f.write(mp3)
    f.close()
    try:
        await message.reply_voice(f.name, quote=quote)
    except Exception as e:
        log.debug(f"reply_voice err: {e}")
        await message.reply_text(text, quote=quote)
    finally:
        try:
            os.unlink(f.name)
        except Exception:
            pass


# ─────────────────── mode switch (owner) ───────────────────
MODE_RE_TEXT = r"\b(teks saja|text only|jangan suara)\b"
MODE_RE_AUTO = r"\b(mode suara|balas suara|voice mode)\b"


@app.on_message(filters.private, group=1)
async def handle_voice_mode(client, message: Message):
    if not message.text or not message.from_user:
        return
    if message.from_user.id != C.OWNER_ID:
        return
    text = message.text.strip()
    key = VOICE_MODE_KEY.format(chat_id=message.chat.id)
    import re
    if re.search(MODE_RE_TEXT, text, re.I) and len(text) < 30:
        await db.set(key, "teks")
        await message.reply_text("Oke, jawaban pakai teks saja 📝")
    elif re.search(MODE_RE_AUTO, text, re.I) and len(text) < 30:
        await db.set(key, "auto")
        await message.reply_text("Oke, balasan suara dinyalakan kembali 🔊")


# ── teks gagal STT: variasi acak, bukan template tunggal ──────────
import random as _random

_FAIL_SANTAI = [
    "hmm suaranya gak kebaca nih 😅 ulangi lagi dong",
    "aduh kepotong kayanya, coba rekam ulang 👂",
    "gak jelas nangkepnya wkwk, sekali lagi ya",
    "bentar, suara lu ilang di jalan… coba kirim ulang 😅",
    "gue gak denger apa-apa nih, rekam ulang dong 🎙️",
]
_FAIL_FORMAL = [
    "Maaf, pesan suara Anda tidak berhasil saya dengar. Mohon ulangi.",
    "Sepertinya rekaman terpotong. Silakan kirim ulang, ya.",
    "Saya belum dapat menangkap isi suaranya. Mohon direkam kembali.",
    "Maaf, audio belum terbaca dengan jelas. Coba kirim sekali lagi.",
]
_NOSTT_SANTAI = [
    "wkwk gue belum bisa denger suara nih 😅 tapi gue bisa ngomong loh!",
    "suara lu masuk tapi telinga gue lagi error 🥲 teks aja dulu ya",
    "gue cuma bisa ngomong, belum bisa dengar 😔 teks dong",
]
_NOSTT_FORMAL = [
    "Maaf, pengenalan suara sedang tidak tersedia. Silakan kirim pesan teks.",
    "Untuk saat ini saya hanya dapat berbicara, belum dapat mendengar. "
    "Mohon gunakan pesan teks.",
]


def _stt_fail_text(conv: str, nostt: bool = False) -> tuple:
    formal = conv == "formal"
    if nostt:
        pool = _NOSTT_FORMAL if formal else _NOSTT_SANTAI
    else:
        pool = _FAIL_FORMAL if formal else _FAIL_SANTAI
    return _random.choice(pool), formal


# ─────────────────── handler utama voice ───────────────────
@app.on_message(filters.voice | filters.audio, group=0)
async def handle_voice(client, message: Message):
    # tandai di state supaya ai handler tahu ini voice → balas dengan suara
    st = await state.get(message.chat.id)
    key = VOICE_MODE_KEY.format(chat_id=message.chat.id)
    mode = (await db.get(key)) or "auto"

    # ── HORMATI MODE: voice hanya diproses kalau bot diizinkan bicara ──
    is_private = message.chat.type == enums.ChatType.PRIVATE
    if not st["speaking"] and not is_private:
        return  # mode diam → voice diabaikan total
    if st["chatbot"] == "off" and not is_private:
        # off: hanya kalau reply ke bot sendiri
        replied = message.reply_to_message
        if not (replied and replied.from_user
                and replied.from_user.id == client.me.id):
            return
    # smart: voice TIDAK diproses sama sekali (teks saja) — kecuali di DM
    if st["chatbot"] == "smart" and not is_private:
        return

    if not GROQ_API_KEY and not C.PROVIDERS:
        txt, formal = _stt_fail_text(st["conv"], nostt=True)
        await reply_voice(message, txt, formal)
        return

    # STT
    async def typing():
        await app.send_chat_action(message.chat.id,
                                   enums.ChatAction.TYPING)
    text = ""
    try:
        text = await speech_to_text(client, message.voice or message.audio)
    except Exception as e:
        log.debug(f"stt fail: {e}")

    if not text:
        await reply_voice(message, *_stt_fail_text(st["conv"]))
        return

    # simpan flag: balasan harus berupa voice
    if mode == "auto":
        await db.set(f"voice_reply:{message.chat.id}", "1")

    # serahkan ke pipeline AI seperti pesan teks biasa:
    # injeksikan transkrip lalu panggil handler inti langsung
    message._milim_voice_text = text
    from MilimNavaAiRobot.modules import handlers as H
    await H.handle_message(client, message)
