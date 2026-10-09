# ══════════════════════════════════════════════════════════════════
#   MILIM NAVA — Entry point (ala SaitamaRobot)
#   Jalankan: python -m MilimNavaAiRobot
# ══════════════════════════════════════════════════════════════════

import asyncio
import importlib

from pyrogram import filters, enums
from pyrogram.types import Message

from MilimNavaAiRobot import (C, app, db, llm, memory, state, startup,
                              LOGGER)

# dynamic load semua modul (ala SaitamaRobot ALL_MODULES)
from MilimNavaAiRobot.modules import ALL_MODULES  # noqa: F401

for module_name in ALL_MODULES:
    importlib.import_module("MilimNavaAiRobot.modules." + module_name)
LOGGER.info("Modules loaded: %s", ALL_MODULES)


# /start, /help, /status
@app.on_message(filters.command(["start", "help"]) & filters.private)
async def cmd_start(client, message: Message):
    st = await state.get(message.chat.id)
    from MilimNavaAiRobot.modules.helpers import START_TEXT, status_text
    await message.reply_text(START_TEXT.format(status=status_text(st)),
                             quote=True)
    from MilimNavaAiRobot.modules.helpers import mark_active
    mark_active(message.chat.id)


@app.on_message(filters.command(["status"]))
async def cmd_status(client, message: Message):
    st = await state.get(message.chat.id)
    from MilimNavaAiRobot.modules.helpers import status_text
    await message.reply_text(status_text(st), quote=True)


async def main():
    async with app:                      # start + connect client
        await startup()
        from pyrogram import idle
        await idle()                     # jalan sampai dimatikan


if __name__ == "__main__":
    app.run(main())
