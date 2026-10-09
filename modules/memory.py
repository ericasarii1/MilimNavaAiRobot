# ══════════════════════════════════════════════════════════════════
#   MEMORY — riwayat per user per chat + thread grup
#   - Persisten di Database, tidak tertukar antar user/grup
#   - Tetap menyimak walau mode diam
# ══════════════════════════════════════════════════════════════════

import json
import time

import config as C


class Memory:
    def __init__(self, db):
        self.db = db

    def _key(self, chat_id, user_id):
        return f"hist:{chat_id}:{user_id}"

    async def add(self, chat_id, user_id, role, content, ts=None):
        key = self._key(chat_id, user_id)
        raw = await self.db.get(key)
        try:
            arr = json.loads(raw) if raw else []
        except Exception:
            arr = []
        arr.append({"role": role, "content": content, "ts": ts or time.time()})
        arr = arr[-C.MAX_CONTEXT_MSGS:]
        await self.db.set(key, json.dumps(arr))

    async def get(self, chat_id, user_id, limit=C.MAX_CONTEXT_MSGS):
        raw = await self.db.get(self._key(chat_id, user_id))
        try:
            arr = json.loads(raw) if raw else []
        except Exception:
            arr = []
        return arr[-limit:]

    async def clear(self, chat_id, user_id):
        await self.db.delete(self._key(chat_id, user_id))

    # thread grup utuh (semua user nyambung — fitur 33-34)
    async def add_group(self, chat_id, speaker, role, content, ts=None):
        key = f"grp:{chat_id}"
        raw = await self.db.get(key)
        try:
            arr = json.loads(raw) if raw else []
        except Exception:
            arr = []
        arr.append({"speaker": speaker, "role": role, "content": content,
                    "ts": ts or time.time()})
        arr = arr[-C.GROUP_THREAD_LIMIT:]
        await self.db.set(key, json.dumps(arr))

    async def get_group(self, chat_id, limit=20):
        raw = await self.db.get(f"grp:{chat_id}")
        try:
            arr = json.loads(raw) if raw else []
        except Exception:
            arr = []
        return arr[-limit:]
