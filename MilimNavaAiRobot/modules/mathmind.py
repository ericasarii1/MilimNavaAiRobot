# ══════════════════════════════════════════════════════════════════
#   MATHMIND — matematika & unit sebagai KEMAMPUAN (bukan command):
#   1. EXPR CALC: hitung ekspresi matematika aman (tanpa eval liar) —
#      turunan dari try_calculate tapi mendukung lebih banyak bentuk.
#   2. UNIT CONVERT: "100 fahrenheit ke celsius", "5 km ke mil",
#      "2 gb ke mb" → konversi nyata, di-inject ke konteks.
#   3. PERCENT / DISKON: "diskon 30% dari 150000" → hasil langsung.
#   Semua = knowledge injection; LLM tetap menyampaikan dengan gayanya.
# ══════════════════════════════════════════════════════════════════

import re
import logging

log = logging.getLogger("milim.mathmind")

# ── unit conversion ───────────────────────────────────────────────
# (kategori, satuan: faktor ke satuan dasar)
UNITS = {
    "panjang": {"km": 1000, "m": 1, "meter": 1, "cm": 0.01, "mm": 0.001,
                "mil": 1609.344, "mile": 1609.344, "yard": 0.9144,
                "kaki": 0.3048, "feet": 0.3048, "ft": 0.3048,
                "inci": 0.0254, "inch": 0.0254},
    "massa": {"kg": 1, "g": 0.001, "gram": 0.001, "mg": 1e-6, "ton": 1000,
              "pon": 0.45359237, "pound": 0.45359237, "lbs": 0.45359237, "oz": 0.0283495},
    "data": {"gb": 1, "mb": 0.001, "kb": 1e-6, "tb": 1000, "bit": 1.25e-10,
             "byte": 1e-9, "gigabyte": 1, "megabyte": 0.001},
    "volume": {"l": 1, "liter": 1, "ml": 0.001, "galon": 3.78541,
               "gallon": 3.78541, "gelas": 0.25},
}
TEMP = {"celsius": ("c",), "c": ("c",), "celcius": ("c",),
        "fahrenheit": ("f",), "f": ("f",),
        "kelvin": ("k",), "k": ("k",)}

CONV_RE = re.compile(
    r"([\d.,]+)\s*°?\s*([a-zA-Z°]+)\s*(?:ke|to|dalam|jadi|=)\s*°?\s*([a-zA-Z°]+)",
    re.IGNORECASE)


def _parse_num(s: str) -> float:
    s = s.strip().replace(".", "").replace(",", ".") \
        if re.match(r"^\d{1,3}([.,]\d{3})+[.,]?\d*$", s.strip()) \
        else s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def convert(text: str):
    """Coba konversi unit dari teks. Return (hasil_teks) atau None."""
    m = CONV_RE.search(text or "")
    if not m:
        return None
    val = _parse_num(m.group(1))
    if val != val:  # nan
        return None
    a, b = m.group(2).lower().strip("°"), m.group(3).lower().strip("°")
    # suhu
    if a in TEMP and b in TEMP:
        ua, ub = TEMP[a][0], TEMP[b][0]
        c = {"c": val, "f": (val - 32) * 5 / 9, "k": val - 273.15}[ua]
        out = {"c": c, "f": c * 9 / 5 + 32, "k": c + 273.15}[ub]
        return f"{val}°{ua.upper()} = {out:g}°{ub.upper()}"
    # satuan biasa
    for cat, tbl in UNITS.items():
        if a in tbl and b in tbl:
            out = val * tbl[a] / tbl[b]
            return f"{val:g} {a} = {out:g} {b}"
    return None


# ── persen / diskon ──────────────────────────────────────────────
PCT_RE = re.compile(
    r"(?:diskon|potongan|discount)\s*(\d{1,3})\s*%.*?([\d.,]{2,})|"
    r"(\d{1,2})\s*%\s*(?:dari|of|dari harga)\s*([\d.,]{2,})",
    re.IGNORECASE)


def percent_calc(text: str):
    m = PCT_RE.search(text or "")
    if not m:
        return None
    try:
        if m.group(1):
            pct = _parse_num(m.group(1))
            base = _parse_num(m.group(2))
        else:
            pct = _parse_num(m.group(3))
            base = _parse_num(m.group(4))
        if pct != pct or base != pct and base != base:
            return None
        save = base * pct / 100
        return (f"{pct:g}% dari {base:g} = {save:g} "
                f"(harga jadi {base - save:g})")
    except Exception:
        return None


# ── aritmetika bentuk bebas (aman) ───────────────────────────────
ARITH_RE = re.compile(
    r"^[\d\s.,+\-*/x×÷^()%]+$")
ASK_CALC_RE = re.compile(r"\b(berapa|hitung|hasil|kalkulasi|=)\b", re.IGNORECASE)


def _safe_arith(expr: str):
    e = (expr.replace("×", "*").replace("x", "*").replace("÷", "/")
             .replace("^", "**"))
    e = re.sub(r"[^0-9+\-*/().% ]", "", e)
    if not e.strip() or "**" in e.replace("**", "") and " " in e:
        pass
    try:
        allowed = {"__builtins__": {}}
        return eval(e, allowed, {})  # sudah disaring ketat
    except Exception:
        return None


def maybe_inject(user_text: str) -> str:
    """Knowledge injection matematika/unit. Return konteks atau ''."""
    t = user_text or ""
    if not t:
        return ""
    outs = []
    u = convert(t)
    if u:
        outs.append(f"HASIL KONVERSI UNIT (nyata, dipercaya): {u}")
    p = percent_calc(t)
    if p:
        outs.append(f"HASIL HITUNG PERSEN (nyata): {p}")
    # aritmetika: pesan pendek berisi ekspresi & kata tanya
    cand = t.strip().rstrip("?").strip()
    if ARITH_RE.match(cand) and len(cand) <= 40 and ASK_CALC_RE.search(t):
        r = _safe_arith(cand)
        if r is not None:
            outs.append(f"HASIL HITUNG (nyata, dipercaya): {cand} = {r}")
    if not outs:
        return ""
    return ("\n\nDATA MATEMATIKA (angka berikut dihitung nyata oleh sistem, "
            "gunakan ini di jawaban, JANGAN menghitung ulang dengan angka lain):\n"
            + "\n".join(f"- {o}" for o in outs))
