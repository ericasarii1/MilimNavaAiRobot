# ══════════════════════════════════════════════════════════════════
#   MEDIA GEN & REACTION — fitur canggih tambahan:
#   7. IMAGE GEN     : "Milim bikinin gambar ..." → image (Pollinations,
#                      gratis tanpa API key)
#   8. YOUTUBE SUM   : share link YT → ambil transcript → rangkum
#   9. SMART REACTION: kadang balas pakai reaction emoji/sticker, seperti
#                      manusia (bukan selalu paragraf)
# ══════════════════════════════════════════════════════════════════

import re
import io
import time
import logging
import urllib.parse

import aiohttp
from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import C, app, db, state, llm
from MilimNavaAiRobot.modules.helpers import now_str

log = logging.getLogger("milim.mediagen")

# ─────────────────── 7. IMAGE GENERATION ───────────────────
IMG_TRIGGER = re.compile(
    r"\b(bikinin|buatin|buatkan|bikin|gambarin|gambar|generate|bikinin gambar|"
    r"bikin gambar|buatin gambar|image)\b.{0,20}\b(gambar|image|foto|lukisan|"
    r"ilustrasi|poster|logo)\b|"
    r"\b(gambar|image)\b.{0,15}\b(kucing|anjing|pemandangan|mobil|robot|"
    r"orang|karakter|anime|kota|gunung|laut|astronot|dragon|naga)\b", re.I)
POLL = "https://image.pollinations.ai/prompt/"


async def generate_image(prompt: str, width=768, height=768) -> bytes | None:
    q = urllib.parse.quote(prompt[:400])
    url = (f"{POLL}{q}?width={width}&height={height}&nologo=true&"
           f"seed={int(time.time()) % 99999}")
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=90)) as ses:
            async with ses.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if len(data) > 2000:
                        return data
                log.debug(f"pollinations http {resp.status}")
    except Exception as e:
        log.debug(f"imggen err: {e}")
    return None


IMAGE_STYLE = ("high quality, detailed, vibrant, artistic, 4k, "
               "professional composition")


def is_image_request(text: str) -> bool:
    return bool(text and IMG_TRIGGER.search(text) and len(text) < 300)


async def handle_image_request(message: Message, text: str) -> bool:
    """Generate & kirim gambar. Return True kalau ditangani."""
    # prompt untuk generator: bersihkan kata perintah
    p = re.sub(r"\b(milim|lim|nava|tolong|dong|ya|please|bikinin|buatin|"
               r"buatkan|bikin|generate|gambarin)\b", " ", text, flags=re.I)
    p = re.sub(r"\s+", " ", p).strip() or text
    img = await generate_image(f"{p}, {IMAGE_STYLE}")
    st = await state.get(message.chat.id)
    if not img:
        await message.reply_text(
            "Maaf, gagal membuat gambar saat ini."
            if st["conv"] == "formal" else
            "Aduh gagal bikin gambarnya 😥 coba lagi bentar ya!")
        return True
    try:
        await message.reply_photo(io.BytesIO(img),
                                  caption=f"🎨 {p[:150]}", quote=True)
    except Exception as e:
        log.debug(f"send photo err: {e}")
        return False
    return True


# ─────────────────── 8. YOUTUBE SUMMARIZER ───────────────────
YT_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)"
    r"([A-Za-z0-9_-]{11})")


def extract_yt_id(text: str):
    m = YT_RE.search(text or "")
    return m.group(1) if m else None


async def get_yt_transcript(vid: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        tr = api.fetch(vid, languages=["id", "en"])
        txt = " ".join(s.text for s in tr.snippets)
        return txt[:6000]
    except Exception as e:
        log.debug(f"yt transcript err: {e}")
        return ""


async def summarize_youtube(message: Message, text: str, vid: str) -> bool:
    st = await state.get(message.chat.id)
    transcript = await get_yt_transcript(vid)
    if not transcript:
        await message.reply_text(
            "Maaf, tidak ada transkrip untuk video ini (mungkin fiturnya "
            "dimatikan oleh pembuatnya)."
            if st["conv"] == "formal" else
            "Hmm, video ini nggak ada transkrip-nya 😅 jadi gue nggak bisa "
            "dengerin isinya. Coba video lain ya!")
        return True
    try:
        answer = await llm.chat([
            {"role": "system", "content":
                "Rangkum transkrip video YouTube berikut untuk user: "
                "poin-poin utama (maks 6), gagasan inti, dan kesimpulan. "
                "Bahasa Indonesia, ringkas, siap dibaca. Jangan mengarang "
                "di luar isi transkrip."},
            {"role": "user", "content": f"TRANSKRIP:\n{transcript}"},
        ])
        await message.reply_text(
            f"📹 **Rangkuman video:**\n\n{answer}", quote=True)
    except Exception as e:
        log.debug(f"yt summary err: {e}")
        await message.reply_text("Gagal merangkum video ini, coba lagi nanti.")
    return True


# ─────────────────── 9. SMART REACTION ───────────────────
# bot kadang "nimbrung" via reaction emoji, bukan selalu balas panjang
REACT_CHANCE = 0.22
_react_last = {}
POSITIVE_EMOJI = ["❤️", "🔥", "👍", "😂", "🎉", "💯"]
FUN_RE = re.compile(
    r"\b(wkwk|haha|hehe|ngakak|lucu|keren|mantap|nice|bagus|anjir|"
    r"gokil|sad|sedih|capek|lelah|btw)\b", re.I)


def maybe_should_react(chat_id: int, text: str) -> str | None:
    """Return emoji kalau bot sebaiknya cuma react, else None."""
    import random
    if not text or len(text) > 200:
        return None
    if not FUN_RE.search(text):
        return None
    if random.random() > REACT_CHANCE:
        return None
    now = time.time()
    if now - _react_last.get(chat_id, 0) < 120:
        return None      # jangan terlalu sering
    _react_last[chat_id] = now
    return random.choice(POSITIVE_EMOJI)


async def send_reaction(client, message: Message, emoji: str) -> bool:
    try:
        await client.send_reaction(chat_id=message.chat.id,
                                   message_id=message.id, emoji=emoji)
        return True
    except Exception as e:
        log.debug(f"react err: {e}")
        return False
