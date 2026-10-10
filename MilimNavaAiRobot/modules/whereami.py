# ══════════════════════════════════════════════════════════════════
#   WHEREAMI — kesadaran lokasi & koneksi sosial Milim (ala assistant
#   yang tahu dia lagi ada di mana dan siapa yang kenal dia):
#   1. Milim mencatat SETIAP grup tempat dia aktif (judul grup, jumlah
#      anggota yang pernah ngobrol, waktu terakhir aktif).
#   2. "Lo lagi di grup mana aja?" → jawab dengan daftar grup ASLI
#      (bukan karangan) + status aktif per grup.
#   3. PRIVASI DM: "lo lagi chat sama siapa?" → daftar user yang lagi/
#      baru saja DM dia + topik singkat, gaya ghibah — tapi AMAN:
#      HANYA nama & topik umum, tidak membuka isi pesan pribadi.
# ══════════════════════════════════════════════════════════════════

import re
import json
import time
import logging

log = logging.getLogger("milim.whereami")

try:
    from MilimNavaAiRobot import db
except Exception:
    db = None

GKEY = "wa:groups"          # semua grup tempat milim aktif
UKEY = "wa:dm:{user}"       # percakapan DM per user (topik umum)
DMLIST = "wa:dmusers"       # daftar user yang pernah DM
STALE = 60 * 60 * 24 * 3    # 3 hari = dianggap tidak aktif lagi

ASK_GROUP_RE = re.compile(
    r"\b(lagi (?:di )?grup mana|grup mana aja|grup apa aja|ada di grup|"
    r"dimana aja lo|di mana aja lo|grup yang lo|grup yang kamu|"
    r"ikut grup|anggota grup mana)\b", re.IGNORECASE)
ASK_DM_RE = re.compile(
    r"\b(lagi (?:chat|ngobrol) sama siapa|siapa yang (?:chat|ngobrol|dm)|"
    r"ada siapa di dm|siapa aja yang (?:chat|dm)|dm siapa aja|"
    r"private chat sama siapa|pc sama siapa)\b", re.IGNORECASE)


async def _get(key, default):
    if db is None:
        return default
    try:
        raw = await db.get(key)
        return json.loads(raw) if raw else default
    except Exception:
        return default


async def _set(key, val):
    if db is None:
        return
    try:
        await db.set(key, json.dumps(val))
    except Exception as e:
        log.debug(f"whereami save err: {e}")


async def touch_group(chat_id: int, title: str, speaker: str):
    """Catat aktivitas grup (dipanggil tiap jawaban di grup)."""
    now = int(time.time())
    groups = await _get(GKEY, {})
    g = groups.get(str(chat_id), {"title": title or "Grup", "users": {},
                                  "last": 0})
    g["title"] = title or g.get("title", "Grup")
    g["last"] = now
    if speaker:
        u = g.setdefault("users", {})
        u[speaker] = now
        # simpan maksimal 30 user terbaru per grup
        if len(u) > 30:
            u = dict(sorted(u.items(), key=lambda kv: -kv[1])[:30])
            g["users"] = u
    groups[str(chat_id)] = g
    # potong daftar grup maks 25
    if len(groups) > 25:
        groups = dict(sorted(groups.items(),
                             key=lambda kv: -kv[1].get("last", 0))[:25])
    await _set(GKEY, groups)


async def touch_dm(user_id: int, name: str, topic_hint: str = ""):
    """Catat aktivitas DM (nama + topik umum, bukan isi pesan)."""
    now = int(time.time())
    users = await _get(DMLIST, {})
    rec = users.get(str(user_id), {"name": name, "last": 0, "topic": ""})
    rec["name"] = name
    rec["last"] = now
    if topic_hint:
        rec["topic"] = topic_hint[:80]
    users[str(user_id)] = rec
    if len(users) > 40:
        users = dict(sorted(users.items(),
                            key=lambda kv: -kv[1].get("last", 0))[:40])
    await _set(DMLIST, users)


def _active(ts: int) -> str:
    if time.time() - ts < 60 * 30:
        return "AKTIF barusan"
    mins = int((time.time() - ts) / 60)
    if mins < 60 * 24:
        return f"terakhir aktif {mins} menit lalu"
    return f"terakhir aktif {mins // 1440} hari lalu"


async def maybe_inject(chat_id, is_private: bool, user_text: str) -> str:
    """Inject daftar grup/DM kalau user nanyain."""
    t = user_text or ""
    if ASK_GROUP_RE.search(t) and not is_private or \
       (ASK_GROUP_RE.search(t) and is_private):
        groups = await _get(GKEY, {})
        if not groups:
            return ("\n\nINFO LOKASI: user menanyakan grup mana saja "
                    "yang kamu ikuti. Data belum tersedia — jawab jujur "
                    "kalau daftarnya belum kecatat.")
        lines = []
        for cid, g in sorted(groups.items(), key=lambda kv: -kv[1].get("last", 0))[:15]:
            n_users = len(g.get("users", {}))
            lines.append(f"- {g.get('title', 'Grup')} — {n_users} user "
                         f"pernah ngobrol di situ, {_active(g['last'])}")
        return ("\n\nDAFTAR GRUP TEMPAT KAMU AKTIF (data nyata dari "
                "sistem, ini yang harus kamu sebut — bukan karangan):\n"
                + "\n".join(lines) +
                "\nSaat ini kamu sedang berada di percakapan ini; "
                "grup-grup di atas adalah tempat kamu juga aktif.")
    if ASK_DM_RE.search(t) and is_private:
        users = await _get(DMLIST, {})
        if not users:
            return ("\n\nINFO DM: user menanyakan siapa yang chat "
                    "private sama kamu. Belum ada data — jawab jujur.")
        lines = []
        for uid, r in sorted(users.items(), key=lambda kv: -kv[1].get("last", 0))[:12]:
            topic = f" — topik: {r['topic']}" if r.get("topic") else ""
            lines.append(f"- {r.get('name', '?')} {topic}, "
                         f"{_active(r['last'])}")
        return ("\n\nDAFTAR USER YANG CHAT PRIVATE SAMA KAMU (data "
                "nyata): ini boleh diceritakan gaya ghibah/gosip yang "
                "seru, TAPI batasi hanya NAMA + TOPIK UMUM di bawah — "
                "JANGAN pernah membuka isi detail pesan pribadi mereka:\n"
                + "\n".join(lines))
    return ""
