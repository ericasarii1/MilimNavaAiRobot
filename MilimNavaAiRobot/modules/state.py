# ══════════════════════════════════════════════════════════════════
#   STATE — state per chat (conv/speaking/chatbot)
# ══════════════════════════════════════════════════════════════════

import json


class StateManager:
    """State per chat (grup & private terpisah)."""

    DEFAULTS = {"conv": "santai", "speaking": True, "chatbot": "on"}

    def __init__(self, db):
        self.db = db
        self._cache = {}

    async def get(self, chat_id: int) -> dict:
        if chat_id in self._cache:
            return self._cache[chat_id]
        raw = await self.db.get(f"state:{chat_id}")
        st = dict(self.DEFAULTS)
        if raw:
            try:
                st.update(json.loads(raw))
            except Exception:
                pass
        self._cache[chat_id] = st
        return st

    async def set(self, chat_id: int, **kwargs):
        st = await self.get(chat_id)
        st.update(kwargs)
        self._cache[chat_id] = st
        await self.db.set(f"state:{chat_id}", json.dumps(st))
        return st
