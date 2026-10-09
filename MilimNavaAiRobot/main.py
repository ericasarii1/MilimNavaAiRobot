# ══════════════════════════════════════════════════════════════════
#   MILIM NAVA — ENTRY POINT
#   Jalankan: python main.py
# ══════════════════════════════════════════════════════════════════

import asyncio
import logging

from pyrogram import Client

import config as C
from database.db import Database
from modules.llm import LLM
from modules.memory import Memory
from modules.utils import AntiSpam, Batcher
from database.db import Database as _D

# state manager (modul kecil, langsung di sini)
class StateManager:
    """State per chat (grup & private terpisah)."""
    def __init__(self, db):
        self.db = db
        self._cache = {}

    async def get(self, chat_id: int) -> dict:
        if chat_id in self._cache:
            return self._cache[chat_id]
        raw = await self.db.get(f"state:{chat_id}")
        if raw:
            try:
                import json
                st = {**{"conv": "santai", "speaking": True, "chatbot": "on"},
                      **json.loads(raw)}
            except Exception:
                st = {"conv": "santai", "speaking": True, "chatbot": "on"}
        else:
            st = {"conv": "santai", "speaking": True, "chatbot": "on"}
        self._cache[chat_id] = st
        return st

    async def set(self, chat_id: int, **kwargs):
        import json
        st = await self.get(chat_id)
        st.update(kwargs)
        self._cache[chat_id] = st
        await self.db.set(f"state:{chat_id}", json.dumps(st))
        return st


logging.basicConfig(level=getattr(logging, C.LOG_LEVEL),
                    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
logging.getLogger("pyrogram").setLevel(logging.WARNING)
log = logging.getLogger("milim")

db = Database(C.MONGODB_URI, C.MONGODB_DB, C.REDIS_URL, C.POSTGRES_DSN)
state = StateManager(db)
memory = Memory(db)
llm = LLM(C.PROVIDERS)

app = Client(
    "milim_nava",
    api_id=C.API_ID,
    api_hash=C.API_HASH,
    bot_token=C.BOT_TOKEN,
    workers=16,
    parse_mode="markdown",
)

# injek dependensi ke handlers
import handlers.handlers as H
H.init(db, state, memory, llm)
H.register(app)


async def startup():
    await llm.start()
    log.info("🚀 Milim Nava bot starting…")
    log.info(f"   Providers : {[p.name for p in llm.providers]}")
    log.info(f"   DB        : {db.backends}")
    log.info(f"   Owner ID  : {C.OWNER_ID}")
    log.info("✔ Milim Nava siap menerima pesan!")


async def idle():
    await startup()
    await asyncio.Event().wait()


if __name__ == "__main__":
    app.run(idle())
