# ══════════════════════════════════════════════════════════════════
#   DEEP BRAIN — paket 5 kemampuan level atas (batch terakhir):
#   1. GROUP MEMORY ARCHIVE — riwayat grup dirangkum berkala →
#      Milim ingat sejarah grup berminggu-minggu (hemat token)
#   2. MULTI-STEP PLANNING — pertanyaan kompleks: rencana → eksekusi
#      → evaluasi → revisi (upgrade agentic loop)
#   3. FACT VERIFY — klaim faktual dicek ke web sebelum dikirim
#   4. FOLLOW-UP CONTEXT — percakapan yang terputus disambung mulus
#      saat user balik (tanpa spam)
# ══════════════════════════════════════════════════════════════════

import re
import json
import time
import asyncio
import logging

log = logging.getLogger("milim.deepbrain")

# ════════════════ 1. GROUP MEMORY ARCHIVE ════════════════
ARCHIVE_KEY = "garch:{chat_id}"
COUNT_KEY = "garchcnt:{chat_id}"
ARCHIVE_EVERY = 120        # rangkum tiap N pesan grup
ARCHIVE_MAX = 3            # simpan 3 periode terakhir


def _keys(chat_id):
    return (ARCHIVE_KEY.format(chat_id=chat_id),
            COUNT_KEY.format(chat_id=chat_id))


async def get_archive(chat_id) -> str:
    key, _ = _keys(chat_id)
    return (await db_get(key)) or ""


async def bump_and_maybe_archive(chat_id: int, llm, memory):
    """Panggil tiap pesan grup. Tiap ARCHIVE_EVERY pesan → rangkum periode."""
    _, ckey = _keys(chat_id)
    try:
        cnt = int((await db_get(ckey)) or 0) + 1
        await db_set(ckey, str(cnt))
        if cnt % ARCHIVE_EVERY != 0:
            return
        hist = await memory.get_group(chat_id, limit=ARCHIVE_EVERY)
        if len(hist) < 30:
            return
        convo = "\n".join(
            f"{h.get('speaker','?')}: {(h.get('content') or '')[:120]}"
            for h in hist[-80:])
        summary = await llm.chat([
            {"role": "system", "content":
                "Rangkum percakapan grup ini: topik utama, keputusan, "
                "acara/rencana, konflik, momen lucu yang berkesan. "
                "Maksimal 5 kalimat padat, gaya catatan."},
            {"role": "user", "content": convo[:6000]}])
        if not summary:
            return
        key, _ = _keys(chat_id)
        cur = (await db_get(key)) or ""
        stamp = time.strftime("%d/%m")
        lines = [ln for ln in cur.split("\n---\n") if ln.strip()]
        lines.append(f"[periode s/d {stamp}] {summary.strip()[:500]}")
        del lines[:-ARCHIVE_MAX]
        await db_set(key, "\n---\n".join(lines))
        log.info(f"garch: arsip grup {chat_id} diperbarui")
    except Exception as e:
        log.debug(f"garch err: {e}")


def archive_prompt(archive: str) -> str:
    if not archive:
        return ""
    return ("\n\nSEJARAH GRUP (ringkasan periode-periode sebelumnya — "
            "pakai bila relevan, jangan disebut sebagai 'arsip'):\n"
            + archive.strip())


# ════════════════ 2. MULTI-STEP PLANNING ════════════════
COMPLEX_RE = re.compile(
    r"\b(bandingin|bandingkan|analisis|evaluasi|rekomendasi(?:in)?\s+"
    r"yang\s+(paling|terbaik)|step by step|cara\s+(lengkap|detail)|"
    r"jelaskan\s+(semua|lengkap|detail)|menurut\s+mu\s+mana|"
    r"pilih(?:kan)?\s+yang\s+mana)\b", re.I)


def needs_planning(text: str) -> bool:
    """Pertanyaan kompleks → jalankan mode rencana dulu."""
    if not text or len(text) < 30:
        return False
    # kompleks = trigger ATAU pertanyaan panjang multi-klausul
    return bool(COMPLEX_RE.search(text)) or (
        len(text) > 140 and text.count("?") + text.count(",") >= 2)


PLAN_ADDON = (
    "\n\nMODE PERENCANAAN AKTIF (pertanyaan kompleks):\n"
    "Sebelum menjawab, kerjakan dalam hati (jangan ditulis di jawaban):\n"
    "1. RENCANA: pecah pertanyaan jadi sub-pertanyaan yang harus dijawab.\n"
    "2. EKSEKUSI: jawab tiap sub-pertanyaan satu per satu dengan data yang "
    "ada (pakai tool bila perlu).\n"
    "3. EVALUASI: cek apakah semua terjawab & konsisten; cari celah.\n"
    "4. REVISI & TULIS FINAL: jawaban akhir yang runtut, lengkap, tapi "
    "tetap gaya ngobrol santai — jangan terlihat seperti laporan robot.\n"
    "Yang ditampilkan ke user HANYA hasil final.")


# ════════════════ 3. FACT VERIFY ════════════════
CLAIM_RE = re.compile(
    r"\b(\d{4}\s*年?|\d+\s*(juta|miliar|triliun|persen|%|km|kg|ton)|"
    r"(tahun|tanggal|bulan)\s+\d+|sejak\s+\d{4}|la(?:hir)?\s+\d{4}|"
    r"\b(new|terbaru|rilis|resmi|diumumkan|dikonfirmasi))\b", re.I)
SKIP_VERIFY = re.compile(
    r"\b(halo|wkwk|oke|siap|sip|thanks|makasih|oke|btw lucu|mantap)\b", re.I)


async def verify_facts(llm, question: str, answer: str) -> str:
    """Klaim faktual di jawaban dicek ke web. Return jawaban final."""
    if not answer or len(answer) < 120 or SKIP_VERIFY.search(answer[:60]):
        return answer
    if not CLAIM_RE.search(answer):
        return answer
    try:
        from MilimNavaAiRobot.modules import web_search as WS
        # ekstrak 1 kueri paling penting dari jawaban
        q = await llm.chat([
            {"role": "system", "content":
                "Ekstrak SATU kata kunci pencarian web (maks 8 kata) untuk "
                "memverifikasi klaim paling penting di teks berikut. "
                "Balas HANYA kata kuncinya."},
            {"role": "user", "content": answer[:600]}])
        q = (q or "").strip().strip('"')[:80]
        if not q or len(q) < 4:
            return answer
        results = await WS.web_search(q, limit=3)
        if not results:
            return answer
        check = await llm.chat([
            {"role": "system", "content":
                "Bandingkan JAWABAN dengan HASIL PENCARIAN. Jawab HANYA:\n"
                "COCOK — jika klaim utama didukung/ tidak kontradiktif\n"
                "BENERIN: <jawaban yang sudah diperbaiki sesuai fakta> — "
                "jika ada klaim terbantahkan. Pertahankan gaya."},
            {"role": "user", "content":
                f"JAWABAN:\n{answer[:1000]}\n\nHASIL PENCARIAN:\n"
                f"{results[:1500]}"}])
        c = (check or "").strip()
        if c.upper().startswith("BENERIN") and len(c) > 20:
            log.info("fact-verify: jawaban dikoreksi")
            return c[7:].strip() or answer
        return answer
    except Exception as e:
        log.debug(f"fact-verify err: {e}")
        return answer


# ════════════════ 4. FOLLOW-UP CONTEXT ════════════════
GAP_KEY = "fgap:{chat_id}:{user_id}"


async def mark_conversation(chat_id: int, user_id: int):
    """Catat waktu interaksi terakhir (dipanggil tiap jawaban bot)."""
    await db_set(GAP_KEY.format(chat_id=chat_id, user_id=user_id),
                 str(time.time()))


async def followup_context(chat_id: int, user_id: int,
                           last_history: list) -> str:
    """User balik setelah lama → konteks 'kemarin kita bahas X'."""
    try:
        raw = await db_get(GAP_KEY.format(chat_id=chat_id, user_id=user_id))
        if not raw:
            return ""
        gap = time.time() - float(raw)
        if gap < 3600:        # < 1 jam: konteks riwayat biasa sudah cukup
            return ""
        # pesan terakhir sebelum gap
        if not last_history:
            return ""
        last = None
        for h in reversed(last_history):
            if h.get("role") == "user":
                last = h
                break
        if not last:
            return ""
        hours = int(gap // 3600)
        when = (f"{hours} jam" if hours < 24 else
                f"{hours // 24} hari")
        return (
            f"\n\nKONTEKS KESENJANGAN: user ini terakhir ngobrol {when} "
            f"lalu. Pesan terakhirnya dulu: \"{(last.get('content') or '')[:150]}\". "
            "Kalau relevan, sambungkan percakapan secara mulus "
            "(misal: 'oh iya, tadi soal ...') — jangan dipaksa, dan JANGAN "
            "menyapa seperti bot yang kangen-kangenan.")
    except Exception as e:
        log.debug(f"followup err: {e}")
        return ""


# ════════════════ DB helpers (import lambat agar bebas siklus) ════════════════
async def db_get(key: str):
    from MilimNavaAiRobot import db
    return await db.get(key)


async def db_set(key: str, value: str):
    from MilimNavaAiRobot import db
    return await db.set(key, value)
