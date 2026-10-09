# ══════════════════════════════════════════════════════════════════
#   ERROR HANDLER — log rapi + notifikasi owner utk error serius
#   (pyrogram 2.x: pakai dispatcher error callback manual)
# ══════════════════════════════════════════════════════════════════

import traceback
import logging
import time

from MilimNavaAiRobot import C, app, LOGGER

_last_notify = 0.0
_notify_interval = 300      # maks 1 notif owner per 5 menit


async def _notify_owner(tb: str):
    global _last_notify
    now = time.time()
    if now - _last_notify < _notify_interval:
        return
    _last_notify = now
    try:
        short = tb.splitlines()[-1][:250] if tb else "?"
        await app.send_message(
            C.OWNER_ID,
            f"⚠️ **Milim Nava — Error Report**\n\n"
            f"```{short}```\n\n"
            f"Bot masih jalan, tapi ada error. Cek log Railway utk detail.")
    except Exception as e:
        LOGGER.debug(f"owner notify gagal: {e}")


def install_error_handler():
    """Pasang handler error global di dispatcher pyrogram."""
    dispatcher = app.dispatcher
    original = dispatcher._handle_error if hasattr(dispatcher, "_handle_error") else None

    async def _handle_error(client, update, users, chats, error):
        tb = traceback.format_exc(limit=8)
        LOGGER.error("Unhandled error:\n%s\nUpdate: %s", tb, str(update)[:200])
        try:
            await _notify_owner(tb)
        except Exception:
            pass
        # teruskan ke default agar tidak mengubah perilaku lain
        if original:
            try:
                await original(client, update, users, chats, error)
            except Exception:
                pass

    try:
        import pyrogram
        dispatcher_cls = type(app.dispatcher)
        # monkeypatch instance method
        import types
        app.dispatcher._handle_error = _handle_error.__get__(
            app.dispatcher, dispatcher_cls)
        LOGGER.info("Global error handler terpasang")
    except Exception as e:
        LOGGER.warning(f"Gagal pasang error handler: {e}")


install_error_handler()
