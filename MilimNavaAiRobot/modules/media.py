# ══════════════════════════════════════════════════════════════════
#   MEDIA READER — gambar/sticker/gif/video/voice/musik/dokumen/
#   video note/kontak/lokasi/poll — semua dibaca & dijelaskan
# ══════════════════════════════════════════════════════════════════

import os
import io
import base64
import logging
from typing import Optional

log = logging.getLogger("milim.media")


async def read_media(client, msg) -> dict:
    """Return {'b64': str|None, 'desc': str} untuk dikirim ke AI."""
    out = {"b64": None, "desc": ""}
    parts = []

    try:
        if msg.photo:
            out["b64"] = await _download_b64(client, msg.photo.file_id)
            parts.append("[Pengguna mengirim FOTO — analisis isi gambar di atas]")
            if msg.caption:
                parts.append(f"Caption: {msg.caption}")

        elif msg.sticker:
            st = msg.sticker
            emoji = st.emoji or ""
            if st.is_animated or st.is_video:
                parts.append(f"[Pengguna mengirim STICKER ANIMASI {emoji} "
                             f"(set: {st.set_name or 'unknown'})]")
                b64 = await _download_b64(client, st.file_id, thumb=st.thumb)
                if b64:
                    out["b64"] = b64
                    parts.append("[Sticker dilampirkan — jelaskan apa yang terlihat]")
            else:
                out["b64"] = await _download_b64(client, st.file_id)
                parts.append(f"[Pengguna mengirim STICKER {emoji} — analisis gambar di atas]")

        elif msg.animation:
            a = msg.animation
            parts.append(f"[Pengguna mengirim GIF: '{a.file_name or 'tanpa nama'}' "
                         f"durasi {a.duration}s]")
            if msg.caption:
                parts.append(f"Caption: {msg.caption}")

        elif msg.video:
            v = msg.video
            parts.append(f"[Pengguna mengirim VIDEO: '{v.file_name or 'tanpa nama'}' "
                         f"durasi {v.duration}s resolusi {v.width}x{v.height}]")
            if msg.caption:
                parts.append(f"Caption: {msg.caption}")

        elif msg.video_note:
            vn = msg.video_note
            parts.append(f"[Pengguna mengirim VIDEO NOTE bulat {vn.duration}s — "
                         f"user sedang berbicara langsung ke kamu]")

        elif msg.voice:
            parts.append(f"[Pengguna mengirim PESAN SUARA {msg.voice.duration}s — "
                         f"user berbicara; respons seolah mendengar ucapannya]")
            if msg.caption:
                parts.append(f"Caption: {msg.caption}")

        elif msg.audio:
            au = msg.audio
            parts.append(f"[Pengguna mengirim MUSIK/AUDIO: '{au.title or au.file_name}' "
                         f"oleh {au.performer or 'unknown'} durasi {au.duration}s]")

        elif msg.document:
            d = msg.document
            parts.append(f"[Pengguna mengirim DOKUMEN: '{d.file_name or 'file'}' "
                         f"ukuran {d.file_size or 0} bytes, mime {d.mime_type or 'unknown'}]")
            if (d.file_size or 0) < 300_000:
                try:
                    fname = await client.download_media(d.file_id, file_name="/tmp/milim_doc")
                    with open(fname, "rb") as f:
                        raw = f.read()
                    os.remove(fname)
                    try:
                        text = raw.decode("utf-8")[:6000]
                    except UnicodeDecodeError:
                        text = f"[File biner {d.mime_type or ''}, tak terbaca sebagai teks]"
                    parts.append(f"ISI FILE:\n{text}")
                except Exception as e:
                    parts.append(f"[Gagal membaca file: {e}]")
            if msg.caption:
                parts.append(f"Caption: {msg.caption}")

        elif msg.contact:
            c = msg.contact
            parts.append(f"[Kontak dibagikan: {c.first_name} {c.last_name or ''} "
                         f"tel {c.phone_number}]")

        elif msg.location:
            loc = msg.location
            parts.append(f"[Lokasi dibagikan: lat {loc.latitude}, lon {loc.longitude}]")

        elif msg.poll:
            p = msg.poll
            opts = ", ".join(o.text for o in p.options)
            parts.append(f"[Polling: '{p.question}' opsi: {opts}]")

    except Exception as e:
        log.debug(f"read_media err: {e}")

    out["desc"] = " ".join(parts)
    return out


async def _download_b64(client, file_id: str, thumb=None) -> Optional[str]:
    try:
        path = await client.download_media(file_id, file_name="/tmp/milim_img")
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
        if len(data) > 2_000_000:
            data = await _compress(data)
        return base64.b64encode(data).decode()
    except Exception as e:
        log.debug(f"download b64 err: {e}")
        return None


def _compress(data: bytes) -> bytes:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return data
