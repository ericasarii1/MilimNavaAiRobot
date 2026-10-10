# ══════════════════════════════════════════════════════════════════
#   MEDIA TRANSCRIPT — file audio/video langsung dirangkum isinya
#   (fitur 4 paket deep brain). Reuse llm.transcribe() semua key.
#   Otomatis aktif begitu ada provider STT; kalau belum, bot bilang
#   jujur bahwa belum bisa mendengar file.
# ══════════════════════════════════════════════════════════════════

import os
import asyncio
import tempfile
import logging

log = logging.getLogger("milim.mtranscript")

MAX_MB = 25
MAX_SECONDS = 1800


async def _extract_audio(client, media_msg, tmpdir: str) -> str | None:
    """Download & konversi ke mp3 mono 16k via ffmpeg (ringan untuk STT)."""
    try:
        path = await client.download_media(media_msg, file_name=os.path.join(
            tmpdir, "in.bin"), progress=None)
        if not path or os.path.getsize(path) > MAX_MB * 1024 * 1024:
            return None
        out = os.path.join(tmpdir, "out.mp3")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", "48k", out,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(proc.wait(), timeout=120)
        return out if os.path.exists(out) else None
    except Exception as e:
        log.debug(f"extract err: {e}")
        return None


async def transcript_media(client, media_msg, llm) -> str | None:
    """Return transkrip teks, atau None bila gagal/tak didukung."""
    from MilimNavaAiRobot import C
    if not C.PROVIDERS and not os.environ.get("GROQ_API_KEY"):
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        audio = await _extract_audio(client, media_msg, tmpdir)
        if not audio:
            return None
        try:
            with open(audio, "rb") as f:
                return await llm.transcribe(f)
        except Exception as e:
            log.debug(f"transcribe err: {e}")
            return None


def wants_transcript(text: str) -> bool:
    """User minta isi audio/video dirangkum?"""
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in ("rangkum", "ringkas", "isi", "transkrip",
                                "isi apa", "ngomong apa", "bahas apa"))
