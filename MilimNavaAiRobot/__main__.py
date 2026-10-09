# ══════════════════════════════════════════════════════════════════
#   MILIM NAVA — Entry point (ala SaitamaRobot)
#   Jalankan: python -m MilimNavaAiRobot
# ══════════════════════════════════════════════════════════════════

import asyncio
import importlib

from pyrogram import idle

from MilimNavaAiRobot import app, startup, LOGGER
from MilimNavaAiRobot.modules import ALL_MODULES

# auto-load semua modul di modules/ (handler terpasang via decorator)
for module_name in ALL_MODULES:
    importlib.import_module("MilimNavaAiRobot.modules." + module_name)
LOGGER.info("Modules loaded: %s", ALL_MODULES)


async def main():
    async with app:          # start + connect client MTProto
        await startup()
        await idle()         # jalan sampai dimatikan


if __name__ == "__main__":
    app.run(main())
