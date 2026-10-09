# ══════════════════════════════════════════════════════════════════
#   UTILS — waktu nyata, humanize delta, antispam, batcher, thinker
# ══════════════════════════════════════════════════════════════════

import re
import time
import asyncio
import logging

from MilimNavaAiRobot import C, NAMES_RE

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


# ── thinking indicator ala claude/gemini (fitur 41) ──────────────
class Thinker:
    STEPS = ["🔍 Mencari…", "🧠 Berpikir…", "✨ Mulai menjawab…"]

    def __init__(self):
        self.task = None

    async def start(self, client, chat_id: int, smart: bool):
        if not smart:
            return None
        m = await client.send_message(chat_id, self.STEPS[0])
        self.task = asyncio.create_task(self._cycle(client, m))
        return m

    async def _cycle(self, client, m):
        i = 0
        try:
            while True:
                await asyncio.sleep(3.5)
                i = min(i + 1, len(self.STEPS) - 1)
                try:
                    await m.edit_text(self.STEPS[i])
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
    r"\?|help|bantuan|how|what|why|who|when|where)", re.IGNORECASE
)


def should_respond(st: dict, text: str, user_id: int) -> tuple:
    """Return (respond: bool, reason: str)."""
    if not st["speaking"]:
        return False, "diam"

    named = bool(NAMES_RE.search(text or ""))
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
