# ══════════════════════════════════════════════════════════════════
#   CATCHUP — "Milim gue ketinggalan apa?" sebagai KEMAMPUAN
#   Bukan command: saat user nanya soal yang terjadi di grup, Milim
#   selalu punya ringkasan pesan-pesan TERAKHIR (termasuk saat user
#   tidak aktif) yang diinject ke konteks → jawab natural.
# ══════════════════════════════════════════════════════════════════

import re
import time
import logging

log = logging.getLogger("milim.catchup")

CATCHUP_TRIGGER = re.compile(
    r"\b(ketinggalan|ketinggalan apa|kejadian apa|yang terjadi|abis apa|"
    r"terakhir apa|yang gue lewat|kenapa bisa|daritadi ngomongin apa|"
    r"ngomongin apa|lagi bahas apa| Kemana aja)\b", re.IGNORECASE)


def detect_catchup(text: str) -> bool:
    return bool(text) and len(text) < 80 and bool(
        CATCHUP_TRIGGER.search(text))


def build_catchup(group_history: list, user_name: str,
                  max_items: int = 12) -> str:
    """Ringkasan pesan grup terakhir utk konteks 'yang lewat'."""
    if not group_history:
        return ""
    now = time.time()
    # pesan sejak user ini terakhir aktif (atau 24 jam terakhir)
    user_last = None
    for x in reversed(group_history):
        if x.get("speaker") == user_name and x.get("role") == "user":
            user_last = x.get("ts")
            break
    since = user_last or (now - 86400)
    missed = [x for x in group_history
              if (x.get("ts") or 0) > since
              and x.get("speaker") not in (user_name, "Milim")]
    if not missed:
        return ""
    lines = []
    for x in missed[-max_items:]:
        age = int(max(0, now - (x.get("ts") or now)) // 60)
        when = ("baru saja" if age < 2 else
                f"{age} menit lalu" if age < 60 else
                f"{age // 60} jam lalu")
        lines.append(f"- {x.get('speaker','?')} ({when}): "
                     f"{(x.get('content') or '')[:150]}")
    return (
        "\n\nRIWAYAT TERBARU GRUP (pesan yang lewat — pakai untuk menjawab "
        "kalau user nanya apa yang terjadi / apa yang dia lewati):\n"
        + "\n".join(lines))
