# ══════════════════════════════════════════════════════════════════
#   UTILS — waktu nyata, humanize delta, antispam, batcher, thinker
# ══════════════════════════════════════════════════════════════════

import re
import time
import asyncio
import logging

from pyrogram import enums
from MilimNavaAiRobot import C, NAMES_RE, NAMES_MATCH_RE, db, llm

log = logging.getLogger("milim.util")

TZ = __import__("datetime").timezone(__import__("datetime").timedelta(hours=C.TZ_OFFSET))


# ── waktu & tanggal (fitur 20, 29) ───────────────────────────────
def now_str() -> str:
    from datetime import datetime
    return datetime.now(TZ).strftime("%A, %d %B %Y • %H:%M:%S WIB")


def humanize_delta(seconds: float) -> str:
    s = int(seconds)
    if s < 5:
        return "baru saja"
    if s < 60:
        return f"{s} detik yang lalu"
    m = s // 60
    if m < 60:
        return f"{m} menit yang lalu"
    h = m // 60
    if h < 24:
        return f"{h} jam yang lalu"
    d = h // 24
    if d < 7:
        return f"{d} hari yang lalu"
    w = d // 7
    if w < 5:
        return f"{w} minggu yang lalu"
    mo = d // 30
    if mo < 12:
        return f"{mo} bulan yang lalu"
    return f"{d // 365} tahun yang lalu"


# ── antispam / anti-abuse (fitur 27) ─────────────────────────────
class AntiSpam:
    def __init__(self):
        self.user_times = {}
        self.user_last = {}
        self.lock = asyncio.Lock()

    async def check(self, user_id: int) -> bool:
        async with self.lock:
            now = time.time()
            arr = [t for t in self.user_times.get(user_id, []) if now - t < C.ANTISPAM_WINDOW]
            if len(arr) >= C.ANTISPAM_BURST:
                self.user_times[user_id] = arr
                return False
            last = self.user_last.get(user_id, 0)
            if now - last < C.ANTISPAM_MIN_INTERVAL:
                await asyncio.sleep(C.ANTISPAM_MIN_INTERVAL - (now - last))
            self.user_times[user_id] = arr + [time.time()]
            self.user_last[user_id] = time.time()
            return True


# ── batch merge spam (fitur 38) ──────────────────────────────────
class Batcher:
    def __init__(self):
        self.pending = {}
        self.lock = asyncio.Lock()

    async def push(self, chat_id, user_id, text, media_desc="") -> object:
        """Return merged text (str) jika pesan terakhir batch, False jika masih menunggu."""
        k = (chat_id, user_id)
        async with self.lock:
            ent = self.pending.get(k)
            if not ent:
                ent = {"msgs": [], "event": asyncio.Event(), "timer": None}
                self.pending[k] = ent
            ent["msgs"].append((text, media_desc))
            if ent["timer"] and not ent["timer"].done():
                ent["timer"].cancel()
            ent["timer"] = asyncio.create_task(self._later(ent))
        await ent["event"].wait()
        async with self.lock:
            if self.pending.get(k) is ent:
                del self.pending[k]
                texts = [t for t, _ in ent["msgs"] if t]
                meds = [m for _, m in ent["msgs"] if m]
                if meds:
                    texts.extend(meds)
                return "\n".join(texts) or ""
        return False

    async def _later(self, ent):
        await asyncio.sleep(C.BATCH_WINDOW)
        ent["event"].set()


# ── thinking indicator natural (fitur 41, revisi) ────────────────
# Bukan template kaku: frasa di-generate LLM sesuai mode (santai/formal),
# di-cache 6 jam per chat. Fallback bank frasa kalau LLM gagal.
_BANK = {
    "santai": [
        "sebentar, gue cek dulu ya…",
        "hmm, gue pikirin dulu…",
        "oke, lagi gue rangkum…",
        "sabar dikit, gue proses…",
        "bentar ya, gue cari…",
    ],
    "formal": [
        "Mohon tunggu, saya periksa terlebih dahulu…",
        "Sebentar, saya pertimbangkan dulu…",
        "Baik, saya susun jawabannya…",
        "Mohon bersabar, sedang saya proses…",
        "Saya cek dahulu informasinya…",
    ],
}
_THINK_CACHE_TTL = 6 * 3600


def _bank_steps(conv: str) -> list:
    import random
    key = "formal" if conv == "formal" else "santai"
    pool = _BANK[key][:]
    random.shuffle(pool)
    return pool


async def _gen_steps(llm, conv: str) -> list:
    """Minta LLM 3 frasa singkat penanda proses, sesuai mode percakapan."""
    try:
        gaya = ("SANTUn/gaul, pakai 'gue/lo', santai akrab"
                if conv != "formal" else
                "FORMAL/sopan, pakai 'saya/Anda'")
        out = await llm.chat([
            {"role": "system", "content":
                f"Buat 3 frasa SINGKAT (maks 6 kata) penanda bahwa AI sedang "
                f"memproses jawaban, dengan gaya {gaya}. Frasa harus variatif, "
                f"natural seperti manusia yang sedang berpikir/mencari, bukan "
                f"kata teknis. Emoji maksimal 1 di akhir. Balas persis 3 baris, "
                f"tanpa nomor, tanpa penjelasan tambahan."},
            {"role": "user", "content": "buat sekarang"}])
        lines = [x.strip(" -•*") for x in (out or "").splitlines()
                 if x.strip()]
        lines = [x for x in lines if 2 < len(x) < 60][:3]
        return lines if len(lines) == 3 else []
    except Exception as e:
        log.debug(f"think gen err: {e}")
        return []


_THINK_MEM = {}          # {(chat_id, conv): (ts, [frasa])}


async def _get_steps(llm, chat_id: int, conv: str) -> list:
    """Frasa penanda proses — SELALU di-generate AI sesuai mode percakapan.
    Cache 6 jam per (chat, mode); bank frasa hanya dipakai kalau AI gagal."""
    mk = (chat_id, conv)
    hit = _THINK_MEM.get(mk)
    if hit and time.time() - hit[0] < _THINK_CACHE_TTL:
        return hit[1]
    key = f"thinkfrasa:{chat_id}:{conv}"
    try:
        raw = await db.get(key)
        if raw:
            import json as _j
            arr = _j.loads(raw)
            if arr and isinstance(arr, list) and len(arr) >= 2:
                _THINK_MEM[mk] = (time.time(), arr)
                return arr
    except Exception:
        pass
    # belum ada → MINTA ke AI sekarang (bukan template)
    if llm is not None:
        try:
            got = await asyncio.wait_for(_gen_steps(llm, conv), timeout=15)
        except Exception as e:
            log.debug(f"think gen timeout/err: {e}")
            got = []
        if got:
            _THINK_MEM[mk] = (time.time(), got)
            try:
                import json as _j
                await db.set(key, _j.dumps(got))
            except Exception:
                pass
            return got
    # AI gagal → bank (jaring pengaman terakhir)
    return _bank_steps(conv)


class Thinker:
    def __init__(self):
        self.task = None

    async def start(self, client, chat_id: int, smart: bool,
                    conv: str = "santai", llm=None):
        if not smart:
            return None
        steps = await _get_steps(llm, chat_id, conv) if llm else _bank_steps(conv)
        m = await client.send_message(chat_id, steps[0])
        self.task = asyncio.create_task(self._cycle(client, m, steps))
        return m

    async def _cycle(self, client, m, steps):
        i = 0
        try:
            while True:
                await asyncio.sleep(3.5)
                i = min(i + 1, len(steps) - 1)
                try:
                    await m.edit_text(steps[i])
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    async def stop(self, client, m):
        if self.task:
            self.task.cancel()
        if m:
            try:
                await m.delete()
            except Exception:
                pass


# ── decision: kapan bot merespon (fitur 5) ───────────────────────
QUESTION_HINTS = re.compile(
    r"(apa|apakah|siapa|kapan|dimana|di mana|bagaimana|gimana|kenapa|mengapa|"
    r"tolong|bantu|bisa|jelaskan|berapa|coba|buatkan|carikan|"
    r"yang mana|yang mananya|kok bisa|kok gitu|"
    r"\?|help|bantuan|how|what|why|who|when|where)", re.IGNORECASE
)


def should_respond(st: dict, text: str, user_id: int) -> tuple:
    """Return (respond: bool, reason: str)."""
    if not st["speaking"]:
        return False, "diam"

    named = bool(NAMES_MATCH_RE.search(text or ""))
    if st["chatbot"] == "on":
        return True, "on"
    if st["chatbot"] == "off":
        return (named, "named" if named else "")
    # smart
    if named:
        return True, "named"
    if text and QUESTION_HINTS.search(text):
        return True, "smart-question"
    return False, ""


# ── typing kontinu (Telegram typing hanya ~5 detik) ──────────────
class TypingLoop:
    """Kirim ulang 'typing' tiap 4 detik selama AI berpikir,
    supaya indikator tidak hilang saat model reasoning lama."""

    def __init__(self):
        self.task = None

    async def start(self, client, chat_id: int):
        self.task = asyncio.create_task(self._loop(client, chat_id))
        return self

    async def _loop(self, client, chat_id):
        try:
            while True:
                try:
                    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
                except Exception:
                    pass
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def stop(self, client, chat_id):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await client.send_chat_action(chat_id, enums.ChatAction.CANCEL)
        except Exception:
            pass

# ── sanitizer: buang prefix metadata yang bocor dari riwayat ────────
_META_PREFIX = re.compile(
    r"^\s*(?:"
    r"\(\s*(?:baru saja|\d+\s*(?:detik|menit|jam|hari|minggu|bulan|tahun)"
    r"\s*yang lalu)\s*\)\s*[:\-]?\s*"
    r"|\[[^\]\n]{0,40}?,\s*(?:baru saja|\d+\s*(?:detik|menit|jam|hari"
    r"|minggu|bulan|tahun)\s*yang lalu)\]\s*:?\s*"
    r"|\(\s*pesan dari [^)\n]{0,40}\)\s*[:\-]?\s*"
    r"|\(\s*info waktu\s*:[^)\n]{0,80}\)\s*[:\-]?\s*"
    r")+", re.IGNORECASE)


_META_ANYWHERE = re.compile(
    r"\s*\(\s*info waktu\s*:[^)\n]{0,80}\)\s*",
    re.IGNORECASE)


def strip_meta_prefix(text: str) -> str:
    """Buang metadata ([nama, waktu] / (5 menit yang lalu) / (pesan dari X) /
    (info waktu: ...)) yang disalin LLM ke jawaban — awalan maupun di tengah."""
    if not text:
        return text
    out = text
    for _ in range(4):
        new = _META_PREFIX.sub("", out, count=1)
        if new == out:
            break
        out = new.lstrip()
    # sisanya di tengah kalimat pun dibuang
    out = _META_ANYWHERE.sub(" ", out)
    # header proses internal yang bocor: "JAWABAN:", "DRAF:", "KOREKSI:", "VERSI FINAL:"
    out = re.sub(r"^\s*(?:JAWABAN|DRAF|KOREKSI|VERSI FINAL|FINAL ANSWER)\s*:\s*\n?",
                 "", out, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip() if not text.endswith("\n") else out

# ── normalize output: perbaiki typo nama & kata Indonesia umum ──────
# Hanya menambal kesalahan PASTI (bukan gaya santai). Case-preserving.
def _fix_fullname(m):
    src = m.group(0)
    if src.isupper():
        return "MILIM NAVA"
    return "Milim Nava"


_TYPO_FIX = [
    # nama lengkap: case kanonik, dihitung khusus
    (re.compile(r"\bMilim\s+[Nn]ava\b|\bMILIM\s+NAVA\b|\bMilim\s+Mava\b", re.I), _fix_fullname),
    (re.compile(r"\bMilin\b", re.I), "Milim"),
    (re.compile(r"\bMlim\b", re.I), "Milim"),
    (re.compile(r"\bMilm\b", re.I), "Milim"),
    (re.compile(r"\bwargi\b", re.I), "warga"),
    (re.compile(r"\bwarga\s+negara\b", re.I), "warga negara"),
]
# kata umum yang jelas typo — HANYA di mode formal (santai boleh "gk" dll? tidak: tetap rapi)
_TYPO_COMMON = [
    (re.compile(r"\byng\b", re.I), "yang"),
    (re.compile(r"\bdgn\b", re.I), "dengan"),
    (re.compile(r"\bdr\b", re.I), "dari"),
    (re.compile(r"\bkrn\b", re.I), "karena"),
    (re.compile(r"\btsb\b", re.I), "tersebut"),
    (re.compile(r"\bsbg\b", re.I), "sebagai"),
    (re.compile(r"\btdk\b", re.I), "tidak"),
    (re.compile(r"\bdpt\b", re.I), "dapat"),
    (re.compile(r"\bsdh\b", re.I), "sudah"),
    (re.compile(r"\bblm\b", re.I), "belum"),
    (re.compile(r"\bjgn\b", re.I), "jangan"),
    (re.compile(r"\bjd\b", re.I), "jadi"),
]


def _preserve_case(match, repl):
    if callable(repl):
        return repl(match)
    src = match.group(0)
    if src.isupper():
        return repl.upper()
    if src[:1].isupper():
        return repl.capitalize()
    return repl


def normalize_output(text: str, formal: bool = False) -> str:
    """Tampal typo nama & singkatan kasar. Gaya santai user tidak dirusak."""
    if not text:
        return text
    out = text
    for rx, rep in _TYPO_FIX:
        out = rx.sub(lambda m, r=rep: _preserve_case(m, r), out)
    if formal:
        for rx, rep in _TYPO_COMMON:
            out = rx.sub(lambda m, r=rep: _preserve_case(m, r), out)
    return out
