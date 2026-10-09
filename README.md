# MilimNavaAiRobot 🤖

AI Telegram Bot dengan 2 kepribadian (Formal & Santai), multi-provider LLM, dan 3 database.

## Fitur
- 🎭 2 mode percakapan (Formal/Santai) — tidak pernah tercampur
- 🤖 3 mode chatbot (ON / OFF / SMART)
- 🗣️ Mode bicara/diam (diam tetap menyimak)
- 🧠 Memory persisten per user per chat (MongoDB + Redis + PostgreSQL fallback)
- 🖼️ Baca semua media (foto, sticker, gif, video, voice, musik, dokumen, dll)
- 🔑 Multi-provider multi-key dengan sticky + fallback otomatis (38+ provider)
- ⏱️ Waktu nyata & referensi waktu relatif akurat
- 👥 Group event handler (join/left/bot-added) dengan respon AI
- 🚦 Antispam, batch merge, typing indicator, thinking status ala Claude/Gemini

## Setup
1. Edit `config.py` — isi API_ID, API_HASH, BOT_TOKEN, OWNER_ID, MONGODB_URI, minimal 1 API key
2. `pip install -r requirements.txt`
3. `python main.py`

## Struktur
```
MilimNavaAiRobot/
├── main.py              # entry point
├── config.py            # semua konfigurasi (tanpa .env)
├── prompts.py           # 2 prompt: Formal & Santai
├── database/
│   └── db.py            # MongoDB/Redis/PostgreSQL layer
├── modules/
│   ├── llm.py           # multi-provider LLM (sticky+fallback)
│   ├── memory.py        # riwayat percakapan
│   ├── media.py         # media reader
│   └── utils.py         # waktu, antispam, batcher, thinker
└── handlers/
    └── handlers.py      # semua command & message handler
```
