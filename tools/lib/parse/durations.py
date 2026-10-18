"""Duration parsing shared by the pharmacokinetics passes (T½, Tmax, formulations):
``durations_in`` / ``durations_in_fr`` turn one English / French line into
``{hours, hours_max?}`` records, ``PEAK_RE`` spots a line naming a peak, and
``sentences`` cuts a stored page into its checkable units. Stdlib only.

Built with the help of Claude Code.
"""
from __future__ import annotations

import re


# One number, optionally a range "X-Y" / "X to Y", then a time unit. Handles the en
# dash Stahl uses for ranges ("24-48") and decimals ("2.7 hours").
_DURATION = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)\s*(?:[-–]|to)?\s*(?P<hi>\d+(?:\.\d+)?)?\s*"
    r"(?P<unit>minute|min|hour|hr|day|week)s?\b",
    re.IGNORECASE,
)


_UNIT_HOURS = {
    "minute": 1 / 60, "min": 1 / 60,
    "hour": 1.0, "hr": 1.0,
    "day": 24.0, "week": 168.0,
}


def parse_duration(line: str) -> dict | None:
    """Parse the first duration in ``line`` into ``{hours, hours_max?}`` (or None).

    Chooses the unit from the matched token and converts to canonical hours; a range
    ("24-48 hours") yields ``hours`` + ``hours_max``. Returns None when the line names
    no ``<number> <time-unit>`` duration.

    Parameters
    ----------
    line
        A candidate half-life line.

    Returns
    -------
    dict or None
        ``{"hours": float, "hours_max": float?}`` or None.
    """
    m = _DURATION.search(line)
    if not m:
        return None
    unit = _UNIT_HOURS[m.group("unit").lower()]
    lo = float(m.group("lo")) * unit
    rec = {"hours": round(lo, 3)}
    if m.group("hi"):
        hi = float(m.group("hi")) * unit
        if hi >= lo:
            rec["hours_max"] = round(hi, 3)
    return rec


# A line worth offering: it names a PEAK. Kept permissive on purpose (a worklist
# vetoes nothing), but it must name the peak itself, never merely an "onset", which is
# the clinical-effect fact this pass must not confuse with a Tmax.
PEAK_RE = re.compile(
    r"(t\s*_?max\b|\bc\s*max\b|peak\s+(?:plasma|serum|blood)|"
    r"peak\s+(?:plasma\s+|serum\s+)?(?:concentration|level)|"
    r"maximum\s+(?:plasma\s+|serum\s+)?concentration|time\s+to\s+peak|"
    r"reach(?:es|ed|ing)?\s+(?:its\s+)?peak|"
    # French (corpus #16 BDPM RCPs): "concentrations plasmatiques maximales", "pic
    # plasmatique". Phrases no English page holds, so the English scan is unchanged.
    r"concentrations?\s+(?:plasmatiques?\s+|s[ée]riques?\s+)?maximales?|"
    r"pics?\s+(?:plasmatiques?|s[ée]riques?|de\s+concentration))", re.IGNORECASE)


def durations_in(line: str) -> list[dict]:
    """Every ``{hours, hours_max?}`` duration stated in one line, left to right.

    The applier gates a judged Tmax against this list, so a number the quote does not
    contain cannot be written. Reuses :func:`parse_duration`'s unit table rather
    than restating it, since the two passes must agree on what "2-4 h" means.

    Parameters
    ----------
    line
        A candidate line.

    Returns
    -------
    list of dict
        One record per duration found; empty when the line states none.
    """
    out: list[dict] = []
    for m in _DURATION.finditer(line):
        unit = _UNIT_HOURS[m.group("unit").lower()]
        lo = float(m.group("lo")) * unit
        rec = {"hours": round(lo, 3)}
        hi = m.group("hi")
        if hi:
            hi_h = float(hi) * unit
            if hi_h >= lo:
                rec["hours_max"] = round(hi_h, 3)
        out.append(rec)
    return out


# The French duration shape of an RCP: "1 heure", "1,5 h", "1 h 30", "1 à 3 heures",
# "entre 2 et 4 heures", "30 min à 1 heure 30", "30 minutes". Separate from
# the English table above so the English corpora's parsed durations
# never change under them.
_NUM_FR = r"\d+(?:[.,]\d+)?"


_UNIT_FR = r"(?:heures?|h|minutes?|min|jours?|semaines?)(?![^\W\d_])"


# One amount: "1,5 h", "30 minutes", or hours-and-minutes "1 h 30" / "1h30" / "1 heure 30".
_AMOUNT_FR = (rf"(?:(?P<{{g}}h>\d+)\s*h(?:eures?)?\s*(?P<{{g}}m>[0-5]\d)(?!\s*(?:%|\d|[.,]\d))"
              rf"|(?P<{{g}}n>{_NUM_FR})\s*(?P<{{g}}u>{_UNIT_FR})?)")


_DURATION_FR = re.compile(
    r"(?P<entre>\bentre\s+)?" + _AMOUNT_FR.format(g="lo")
    + r"(?:\s*(?P<conn>[-–]|à|et)\s*" + _AMOUNT_FR.format(g="hi") + r")?",
    re.IGNORECASE)


_UNIT_HOURS_FR = {"heure": 1.0, "h": 1.0, "minute": 1 / 60, "min": 1 / 60,
                  "jour": 24.0, "semaine": 168.0}


def _hours_fr(m, g: str, unit: str | None) -> float | None:
    """One matched amount in hours, or None when it carries no unit."""
    if m.group(f"{g}h"):
        return int(m.group(f"{g}h")) + int(m.group(f"{g}m")) / 60
    unit = (m.group(f"{g}u") or unit or "").lower().rstrip("s")
    if not unit:
        return None
    return float(m.group(f"{g}n").replace(",", ".")) * _UNIT_HOURS_FR[unit]


def durations_in_fr(line: str) -> list[dict]:
    """``durations_in`` for a French line (decimal comma, "à" ranges, "1 h 30").

    A range's low end borrows the high end's unit ("1 à 3 heures"). "et" joins a range
    only after "entre": "en 2 et 3 heures respectivement" is two values, not a range.

    >>> durations_in_fr("un Tmax atteint en 1 heure environ")
    [{'hours': 1.0}]
    >>> durations_in_fr("entre 1,5 et 3 heures, ou 30 minutes")
    [{'hours': 1.5, 'hours_max': 3.0}, {'hours': 0.5}]
    >>> durations_in_fr("30 min à 1 heure 30 plus tard; environ 1h30 après")
    [{'hours': 0.5, 'hours_max': 1.5}, {'hours': 1.5}]
    >>> durations_in_fr("atteintes respectivement en 2 et 3 heures")
    [{'hours': 2.0}, {'hours': 3.0}]
    """
    out: list[dict] = []
    for m in _DURATION_FR.finditer(line):
        has_hi = bool(m.group("hih") or m.group("hin"))
        hi = _hours_fr(m, "hi", None) if has_hi else None
        hi_unit = m.group("hiu") if has_hi else None
        lo = _hours_fr(m, "lo", hi_unit if has_hi else None)
        if lo is None:
            continue
        lo = round(lo, 3)
        if hi is None:
            out.append({"hours": lo})
        elif m.group("conn").lower() == "et" and not m.group("entre"):
            out += [{"hours": lo}, {"hours": round(hi, 3)}]
        elif hi >= lo:
            out.append({"hours": lo, "hours_max": round(hi, 3)})
        else:
            out.append({"hours": lo})
    return out


def sentences(text: str):
    """Yield the page's checkable units: one sentence, or one flattened table row.

    A stored article keeps each table as ``"cell | cell | ..."`` lines, which carry no
    sentence punctuation, so splitting on ``.``/``;`` leaves such a row whole and it
    stays quotable verbatim exactly as the Ki passes quote it.
    """
    for raw in text.splitlines():
        line = raw.strip().lstrip("#*->").strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.;])\s+", line):
            part = part.strip()
            if part:
                yield part
