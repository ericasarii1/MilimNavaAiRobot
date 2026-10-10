# ══════════════════════════════════════════════════════════════════
#   CROSS-CONTEXT — ala kode lama: percakapan DM & grup user ini
#   saling tersambung. Saat di grup → sepotong riwayat DM user ikut;
#   saat di DM → ringkasan grup tempat user aktif ikut. Berlabel jelas
#   [PRIVATE] / [GRUP: nama] supaya LLM gak salah tempat.
# ══════════════════════════════════════════════════════════════════

import logging

log = logging.getLogger("milim.crossctx")

try:
    from MilimNavaAiRobot import db
    import json
except Exception:
    db = None


async def dm_context(chat_id, user_id, limit=6) -> str:
    """Riwayat DM terbaru user (dipakai saat user aktif di grup)."""
    if db is None:
        return ""
    try:
        hist = await memory_get(chat_id, user_id, limit)
        if not hist:
            return ""
        lines = []
        for h in hist:
            who = "User" if h.get("role") == "user" else "Milim"
            lines.append(f"[PRIVATE] {who}: {h.get('content','')[:150]}")
        return ("\n\nKONTEKS PRIVATE CHAT (percakapan terakhirmu dengan "
                "user ini di DM — jangan disebut otomatis, pakai kalau "
                "relevan):\n" + "\n".join(lines))
    except Exception as e:
        log.debug(f"dmctx err: {e}")
        return ""


async def group_context(user_groups, limit=5) -> str:
    """Ringkasan aktivitas grup tempat user aktif (dipakai saat DM)."""
    if db is None or not user_groups:
        return ""
    try:
        from MilimNavaAiRobot.modules import memory as MM
        lines = []
        for cid in user_groups[-3:]:
            try:
                gh = await MM.memory.get_group(int(cid), limit=3)
                for h in gh:
                    lines.append(f"[GRUP] {h.get('speaker','?')}: "
                                 f"{h.get('content','')[:120]}")
            except Exception:
                pass
        if not lines:
            return ""
        return ("\n\nKONTEKS GRUP (obrolan terakhir di grup tempat user "
                "ini aktif — jangan disebut otomatis):\n" +
                "\n".join(lines[-8:]))
    except Exception as e:
        log.debug(f"grpctx err: {e}")
        return ""


async def memory_get(chat_id, user_id, limit):
    from MilimNavaAiRobot.modules import memory as MM
    return await MM.memory.get(chat_id, user_id, limit=limit)
