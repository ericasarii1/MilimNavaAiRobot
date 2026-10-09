# MilimNavaAiRobot 🤖

AI Telegram Bot dengan 2 kepribadian (Formal & Santai), multi-provider LLM, dan 3 database — struktur ala [SaitamaRobot](https://github.com/animekaizoku/saitamarobot).

## Fitur
- 🎭 2 mode percakapan (Formal/Santai) — tidak pernah tercampur, hanya 2 prompt runtime
- 🤖 3 mode chatbot (ON / OFF / SMART)
- 🗣️ Mode bicara/diam (diam tetap menyimak)
- 🧠 Memory persisten per user per chat (MongoDB + Redis + PostgreSQL, fallback in-memory)
- 🖼️ Baca semua media (foto, sticker, gif, video, voice, musik, dokumen, dll)
- 🔑 Multi-provider multi-key dengan sticky + fallback otomatis (OpenRouter, Gemini, Claude, dll)
- ⏱️ Waktu nyata & referensi waktu relatif akurat
- 👥 Group event handler (join/left/bot-added) dengan respon AI sesuai mode
- 🚦 Antispam, batch merge, typing indicator, thinking status ala Claude/Gemini

## Setup
**Cara 1 — .env (direkomendasikan):**
```
cp .env.example .env
# lalu isi API_ID, API_HASH, TOKEN, OWNER_ID, MONGODB_URI, OPENROUTER_KEYS
```

**Cara 2 — config.py (ala SaitamaRobot):**
```
cp MilimNavaAiRobot/sample_config.py MilimNavaAiRobot/config.py
# lalu edit nilainya langsung (config.py otomatis di-gitignore)
```

**Cara 3 — Railway:** isi semua sebagai Variables di dashboard (API_ID, API_HASH, TOKEN, OWNER_ID, MONGODB_URI, OPENROUTER_KEYS=...)

Prioritas: environment variables → config.py → default.

Lalu:
```
pip install -r requirements.txt
python -m MilimNavaAiRobot
```

## Struktur
```
MilimNavaAiRobot/          (repo root)
├── README.md
├── requirements.txt
├── .gitignore
└── MilimNavaAiRobot/      (package utama)
    ├── __init__.py        # Config loader (.env/config.py/default) + client + singletons
    ├── __main__.py        # entry point — auto-load semua modul
    ├── sample_config.py   # template config (rename jadi config.py untuk pakai)
    ├── database/
    │   └── db.py          # MongoDB/Redis/PostgreSQL + fallback in-memory
    └── modules/
        ├── __init__.py    # auto-loader (ALL_MODULES)
        ├── ai.py          # LLM multi-provider (sticky + fallback)
        ├── handlers.py    # semua handler (command, message, group event)
        ├── helpers.py     # waktu, antispam, batcher, thinker, should_respond
        ├── media.py       # media reader semua tipe
        ├── memory.py      # riwayat per user + thread grup
        ├── prompts.py     # 2 prompt (Formal & Santai) + semua teks
        └── state.py       # state per chat (conv/speaking/chatbot)
```

## Cara nambah fitur baru
Bikin file `.py` baru di `modules/` — otomatis ke-load saat bot start.
