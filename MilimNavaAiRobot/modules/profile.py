# ══════════════════════════════════════════════════════════════════
#   PROFILE — user profile terstruktur per user (key-value di DB)
#   Auto-learn: fakta penting diekstrak otomatis dari percakapan
#   Command natural:
#     "Milim profil gue"        → lihat profil
#     "Milim lupa [fakta]"      → hapus satu fakta
#     "Milim inget: nama gue X" → simpan langsung
# ══════════════════════════════════════════════════════════════════

import re
import json
import logging

log = logging.getLogger("milim.profile")

PROF_KEY = "profile:{user_id}"
AUTO_LEARN_EVERY = 10       # ekstrak tiap N pesan user


def _key(user_id: int) -> str:
    return PROF_KEY.format(user_id=user_id)


async def get_profile(db, user_id: int) -> dict:
    raw = await db.get(_key(user_id))
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


async def save_profile(db, user_id: int, prof: dict):
    await db.set(_key(user_id), json.dumps(prof, ensure_ascii=False))


PROFILE_PROMPT = (
    "\n\nPROFIL USER (fakta terverifikasi — pakai bila relevan, "
    "jangan tanya ulang yang sudah ada):\n{prof}")


def profile_addon(prof: dict) -> str:
    if not prof:
        return ""
    lines = "\n".join(f"- {k}: {v}" for k, v in prof.items())
    return PROFILE_PROMPT.format(prof=lines)


EXTRACT_PROMPT = (
    "Ekstrak fakta PERSISTEN tentang user dari percakapan berikut "
    "(nama, panggilan, pekerjaan, hobi, preferensi, domisili, ulang tahun, "
    "hal yang dia suka/benci). HANYA fakta yang jelas, jangan menebak.\n"
    "Jawab JSON object saja: {\"nama fakta\": \"nilainya\"} — atau {} "
    "kalau tidak ada fakta baru.\n\nPERCAKAPAN:\n{convo}")


async def auto_learn(llm, db, user_id: int, convo_text: str) -> dict:
    """Ekstrak fakta baru dari percakapan → merge ke profil."""
    try:
        out = await llm.chat([
            {"role": "system", "content":
                "Kamu ekstraktor data. Jawab JSON object murni saja."},
            {"role": "user", "content":
                EXTRACT_PROMPT.format(convo=convo_text[:1500])}
        ])
        m = re.search(r"\{.*\}", out or "", re.S)
        if not m:
            return {}
        new = json.loads(m.group(0))
        if not isinstance(new, dict):
            return {}
        prof = await get_profile(db, user_id)
        added = {}
        for k, v in new.items():
            k = str(k).strip().lower()[:30]
            v = str(v).strip()[:120]
            if k and v and prof.get(k) != v:
                prof[k] = v
                added[k] = v
        if added:
            await save_profile(db, user_id, prof)
        return added
    except Exception as e:
        log.debug(f"auto learn err: {e}")
        return {}


# ─────────────── command natural (dipanggil dari handlers) ───────────────
VIEW_RE = re.compile(r"\b(profil gue|profil saya|profile|profilku|profil aku)\b", re.I)
FORGET_RE = re.compile(r"\b(?:lupa|hapus)\s+(?:profil\s+)?(?:gue|aku|saya)?\s*[:\-]?\s*(.+)", re.I)
REMEMBER_RE = re.compile(r"\b(?:inget|ingat|catat profil)\s*[:\-]?\s*(\w+)\s*[:\-]?\s*(.+)", re.I)


async def handle_profile_command(db, user_id: int, text: str):
    """Return (reply_text, handled). Dipanggil dari handler utama."""
    t = text.strip()

    if VIEW_RE.search(t) and len(t) < 40:
        prof = await get_profile(db, user_id)
        if not prof:
            return ("Profilmu masih kosong. Obrol aja santai, pelan-pelan "
                    "gue kenalan sama lo 😄", True)
        lines = "\n".join(f"• **{k}:** {v}" for k, v in prof.items())
        return (f"👤 **Profil lo:**\n{lines}", True)

    m = FORGET_RE.search(t)
    if m and len(t) < 60:
        frag = m.group(1).strip().lower()
        prof = await get_profile(db, user_id)
        removed = [k for k in prof if k in frag or frag in k]
        for k in removed:
            del prof[k]
        await save_profile(db, user_id, prof)
        if removed:
            return (f"Oke, gue lupain: {', '.join(removed)} 🗑️", True)
        return ("Gak nemu fakta itu di profil lo 🤔", True)

    m = REMEMBER_RE.search(t)
    if m and len(t) < 120:
        k, v = m.group(1).strip().lower()[:30], m.group(2).strip()[:120]
        prof = await get_profile(db, user_id)
        prof[k] = v
        await save_profile(db, user_id, prof)
        return (f"Tercatat! {k}: {v} 📝", True)

    return None, False
