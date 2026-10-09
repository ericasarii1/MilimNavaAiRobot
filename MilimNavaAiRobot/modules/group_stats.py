# ══════════════════════════════════════════════════════════════════
#   GROUP STATS — statistik aktivitas grup sebagai "pengetahuan"
#   Bukan command: Milim SELALU tahu siapa paling aktif dll, dan
#   menjawab natural kalau ditanya ("siapa paling aktif?").
# ══════════════════════════════════════════════════════════════════

import time
import logging

log = logging.getLogger("milim.gstats")

STATS_QUESTIONS = (
    "aktif|paling banyak|leaderboard|peringkat|ranking|siapa saja yang "
    "|ada siapa|sepi|rame")


def build_stats(chat_history: list, limit: int = 5) -> str:
    """Dari riwayat grup → ringkasan statistik utk system prompt."""
    if not chat_history:
        return ""
    now = time.time()
    counts = {}
    first_ts, last_ts = None, None
    for x in chat_history:
        sp = x.get("speaker", "?")
        if sp == "Milim":
            continue
        counts[sp] = counts.get(sp, 0) + 1
        ts = x.get("ts")
        if ts:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
    if not counts:
        return ""
    ranked = sorted(counts.items(), key=lambda i: -i[1])[:limit]
    lines = [f"{i+1}. {name}: {n} pesan"
             for i, (name, n) in enumerate(ranked)]
    total = sum(counts.values())
    span = ""
    if last_ts:
        age = now - last_ts
        if age < 3600:
            span = f"Pesan terakhir: {int(age//60)} menit lalu."
        elif age < 86400:
            span = f"Pesan terakhir: {int(age//3600)} jam lalu."
        else:
            span = f"Pesan terakhir: {int(age//86400)} hari lalu."
    return (
        "\n\nSTATISTIK GRUP INI (data nyata — jawab dari sini kalau "
        "ditanya soal aktivitas grup):\n"
        f"Total {total} pesan terakhir. Peringkat keaktifan:\n"
        + "\n".join(lines) + ("\n" + span if span else ""))
