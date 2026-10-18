"""The corpus #16 store (BDPM, the French public drug database): where its files live,
how its bulk tables read, and the drug -> French INN -> product join.

Shared by the RCP fetchers (``tools/fetch/fetch_bdpm.py`` for section 5.2,
``tools/fetch/fetch_bdpm_rcp.py`` for sections 4.2 / 4.3 / 4.4), the EMA EPAR fallback
and the formulation pass; the join rules are documented in ``fetch_bdpm.py``'s module
docstring. Stdlib only.

Built with the help of Claude Code.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import chirality
from text_fold import strip_accents

ROOT = Path(__file__).resolve().parents[3]                      # repo root


SITE = "https://base-donnees-publique.medicaments.gouv.fr"


TABLE_URL = SITE + "/download/file/{name}"


RCP_URL = SITE + "/medicament/{cis}/extrait"


BASE_DIR = ROOT / "data_sources" / "bdpm"


RAW_DIR = BASE_DIR / "raw"


PAGES_DIR = BASE_DIR / "pages"


PRODUCTS_FILE = "CIS_bdpm.txt"


COMPO_FILE = "CIS_COMPO_bdpm.txt"


CACHE_PATH = ROOT / "tools" / "generated_cache" / "bdpm_labels.json"


BRAND_WORKLIST = ROOT / "tools" / "generated_cache" / "brand_worklist.json"


# A French INN the folded English name and the FR Wikipedia title both miss. Values are
# folded molecule keys (see ``fold``); only add one after checking the BDPM spelling.
FR_ALIASES: dict[str, tuple[str, ...]] = {
    "amphetamine_d": ("DEXAMFETAMINE",),
    "amphetamine_dl": ("AMFETAMINE",),
    "methylphenidate_d": ("DEXMETHYLPHENIDATE",),
    "methylphenidate_dl": ("METHYLPHENIDATE",),     # the French products are racemic
    "methamphetamine": ("METAMFETAMINE",),
    # Divalproate is valproate's own salt complex (Depakote); valpromide (Depamide) is a
    # different molecule and stays out.
    "valproate": ("VALPROATE", "ACIDE VALPROIQUE", "DIVALPROATE"),
}


# Salt / hydrate / counter-ion words a substance line wraps around its molecule.
SALT_WORDS = {
    "ACETATE", "ANHYDRE", "BASE", "BENZOATE", "BESILATE", "BITARTRATE", "BROMHYDRATE", "BROMURE",
    "CHLORHYDRATE", "CHLORURE", "CITRATE", "DIHYDRATE", "DICHLORHYDRATE", "EMBONATE",
    "FUMARATE", "GLUCONATE", "HEMIFUMARATE", "HEMIHYDRATE", "HEMISULFATE",
    "HEMITARTRATE", "HYDROGENOTARTRATE", "HYDROGENOFUMARATE", "HYDROGENOSUCCINATE",
    "IODURE", "LACTATE", "MALATE", "MALEATE", "MESILATE", "MESYLATE", "METHANESULFONATE",
    "METHYLSULFATE", "MONOHYDRATE", "MONOHYDRATEE", "NAPADISILATE", "OXALATE", "PALMITATE",
    "PAMOATE", "PHOSPHATE",
    "SESQUIHYDRATE", "SUCCINATE", "SULFATE", "TARTRATE", "TOSILATE", "TRIHYDRATE",
    "CARBONATE", "SODIQUE", "POTASSIQUE", "DIPOTASSIQUE", "DISODIQUE", "DIMESILATE",
    "MONOSODIQUE", "CALCIQUE", "DE", "D", "SODIUM", "POTASSIUM",
    "CALCIUM", "MAGNESIUM", "SEL", "SOUS", "FORME",
}


# A product that is not a plain immediate-release form, read off the denomination and
# the form column. Its peak belongs to a different product (see the module docstring).
MODIFIED_RELEASE = re.compile(
    r"\bL\.?\s?P\.?\b|LIB[EÉ]RATION\s+(?:PROLONG|MODIFI|RETARD|CONTR[OÔ]L)|"
    r"GASTRO-?R[EÉ]SISTANT|\bCHRONO\b|\bRETARD\b|\bDEPOT\b|\bDÉPÔT\b|\bLI\b",
    re.IGNORECASE)


# Generic manufacturers' house names: a denomination carrying one is a generic even when
# its first word is not the INN (rare, but a "BIOGARAN" product is never a brand).
GENERIC_LABS = {
    "ACCORD", "ALMUS", "ALTER", "ARROW", "BIOGARAN", "CRISTERS", "EG", "EVOLUGEN",
    "MYLAN", "QUALIMED", "RANBAXY", "RATIOPHARM", "SANDOZ", "TEVA", "VIATRIS",
    "ZENTIVA", "ZYDUS", "SUN", "AUROBINDO", "KRKA", "UPSA CONSEIL", "GNR", "PANPHARMA",
}


# Routes whose product acts where applied, not as the systemic drug.
LOCAL_ROUTES = re.compile(r"cutan[ée]e|ophtalmique|auriculaire|dentaire|gingivale",
                          re.IGNORECASE)


def fold(text: str) -> str:
    """Accent-fold + uppercase + collapse to letters/digits separated by one space."""
    t = strip_accents(text).upper()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", t).split())


def molecule_key(substance: str, salt_words: frozenset[str] | set[str] = SALT_WORDS
                 ) -> tuple[str, str | None]:
    """A substance line reduced to ``(molecule, stereo tag)``. ``salt_words`` lets
    another table (EMA's English substances) strip its own counter-ion words.

    >>> molecule_key("CHLORHYDRATE DE FLUOXÉTINE")
    ('FLUOXETINE', None)
    >>> molecule_key("CITALOPRAM (BROMHYDRATE DE)")
    ('CITALOPRAM', None)
    >>> molecule_key("OXALATE D'ESCITALOPRAM")
    ('ESCITALOPRAM', None)
    >>> molecule_key("SODIUM (VALPROATE DE)")
    ('VALPROATE', None)
    >>> molecule_key("ACIDE VALPROÏQUE")
    ('ACIDE VALPROIQUE', None)
    """
    stem, tag = chirality.split_stereo(substance)
    words = [w for w in fold(re.sub(r"\([^)]*\)", " ", stem)).split()
             if w not in salt_words]
    if not words:      # an inverted line, "SODIUM (VALPROATE DE)": the molecule is inside
        words = [w for w in fold(stem).split() if w not in salt_words]
    return " ".join(words), tag


def is_homeopathic(substance: str) -> bool:
    return "HOMEOPATH" in fold(substance)


def drug_keys(drug: dict, fr_titles: dict) -> set[str]:
    """Every folded name the drug can appear under in the substance table."""
    names = [drug.get("name") or ""]
    if drug["id"] in fr_titles:
        names.append(fr_titles[drug["id"]])
    # A stereo-qualified name ("Methylphenidate (D)", "Amphetamine (D,L)") is never
    # reduced, or its qualifier would be dropped and the racemate's products joined to
    # the single enantiomer: such drugs join only through ``FR_ALIASES``. Others are
    # reduced the same way a substance line is ("Sodium oxybate" -> OXYBATE) and kept
    # whole too (a name that is all salt words, "lithium", must still match).
    if any("(" in n for n in names):
        keys = set(FR_ALIASES.get(drug["id"], ()))
        return keys | {k + "E" for k in keys if not k.endswith("E")}
    keys = {fold(n) for n in names} | {molecule_key(n)[0] for n in names}
    # The French INN often only adds a final -e (vigabatrin -> VIGABATRINE, pizotifen
    # -> PIZOTIFENE, bupropion -> BUPROPIONE). Still an exact match on the whole key.
    keys |= {k + "E" for k in keys if k and not k.endswith("E")}
    keys.update(FR_ALIASES.get(drug["id"], ()))
    return {k for k in keys if k}


def read_table(path: Path) -> list[list[str]]:
    """One latin-1 TSV as rows of stripped cells."""
    text = path.read_bytes().decode("latin-1")
    return [[c.strip() for c in line.split("\t")] for line in text.splitlines() if line]


def load_products(rows: list[list[str]]) -> dict[str, dict]:
    """``CIS_bdpm.txt`` rows -> ``{cis: {denomination, form, route, status, marketed, holder}}``."""
    out: dict[str, dict] = {}
    for r in rows:
        if len(r) < 7:
            continue
        out[r[0]] = {"cis": r[0], "denomination": r[1], "form": r[2], "route": r[3],
                     "status": r[4], "marketed": r[6] == "Commercialisée",
                     "holder": r[10].strip() if len(r) > 10 else ""}
    return out


def load_compo(rows: list[list[str]]) -> dict[str, list[dict]]:
    """``CIS_COMPO_bdpm.txt`` rows -> ``{cis: [{name, nature, link}]}``.

    ``nature`` is ``SA`` (substance active) or ``FT`` (fraction thérapeutique, the same
    active restated as its base); ``link`` ties an FT to its SA, so the number of
    distinct links is the number of actives.
    """
    out: dict[str, list[dict]] = {}
    for r in rows:
        if len(r) < 8:
            continue
        out.setdefault(r[0], []).append({"name": r[3], "nature": r[6], "link": r[7]})
    return out


def single_active(lines: list[dict]) -> bool:
    """Whether a product has exactly one active substance (combinations are skipped)."""
    return len({ln["link"] for ln in lines}) == 1


def matches(drug_id: str, keys: set[str], lines: list[dict]) -> bool:
    """Whether a single-active product's substance IS this drug (exact molecule match).

    Only the ``SA`` line is read: a prodrug's ``FT`` line names what it becomes
    (lisdexamfetamine's is DEXAMFETAMINE), which is not the product's drug.
    """
    for ln in lines:
        if ln["nature"] != "SA":
            continue
        if is_homeopathic(ln["name"]):
            return False
        mol, tag = molecule_key(ln["name"])
        if mol in keys and chirality.tag_allowed(tag, drug_id):
            return True
    return False


def only_partners(lines: list[dict], keys: set[str], partners) -> bool:
    """Whether a combination pairs the drug with nothing but ``partners`` (folded
    molecule keys): levodopa + carbidopa yes, levodopa + carbidopa + entacapone no."""
    others = {molecule_key(ln["name"])[0] for ln in lines if ln["nature"] == "SA"} - keys
    return bool(others) and others <= set(partners)


def products_for(drug: dict, keys: set[str], products: dict, compo: dict,
                 partners=()) -> list[dict]:
    """Every single-active product whose substance is ``drug``, plus, when
    ``partners`` is given, its combinations with only those molecules (the RCP 4.x
    workup join only, ``fetch_bdpm_rcp.COMBO_PARTNERS``: a combination's 5.2 states
    the combination's kinetics, so this pass never asks for them)."""
    out = []
    for cis, lines in compo.items():
        if cis in products and matches(drug["id"], keys, lines) and (
                single_active(lines) or (partners and only_partners(lines, keys, partners))):
            out.append({**products[cis], "substances": [ln["name"] for ln in lines]})
    return out


def brand_of(product: dict, keys: set[str]) -> str | None:
    """The brand a product's denomination names, or None for a generic.

    The brand part is the denomination's first word ("HAVLANE, comprimé sécable" ->
    ``HAVLANE``, "THERALENE 5 mg, ..." -> ``THERALENE``, "DEPAKINE CHRONO 500 mg" ->
    ``DEPAKINE``): the trailing words are dosage or a product-line suffix, not a second
    brand. Generic-exclusion rule: the product is a generic, and gives no brand, when
    that first word is a word of the drug's INN or of any of the product's substance
    lines (French generics are named "<INN> <LAB>": "LOPRAZOLAM TEVA",
    "ACIDE VALPROÏQUE ARROW", "VALPROATE DE SODIUM MYLAN"), when the INN appears later
    in the brand part (a range name, not a product brand: "GRANIONS DE LITHIUM"), or
    when the denomination carries a generic manufacturer's house name (``GENERIC_LABS``).
    A product for a local route (skin, eye, ear: ``LOCAL_ROUTES``) gives no brand
    either: "LITHIODERM" is a lithium skin gel, not a brand of the drug modeled here.

    >>> brand_of({"denomination": "HAVLANE, comprimé sécable", "substances": ["LOPRAZOLAM"]}, {"LOPRAZOLAM"})
    'HAVLANE'
    >>> brand_of({"denomination": "LOPRAZOLAM TEVA 1 mg, comprimé", "substances": ["LOPRAZOLAM"]}, {"LOPRAZOLAM"})
    """
    if LOCAL_ROUTES.search(product.get("route") or ""):
        return None
    raw = product["denomination"].split(",")[0].strip()
    m = re.match(r"[^\W\d_][\w'’.-]*", raw)
    if not m:
        return None
    word = m.group(0).rstrip(".-")
    head = fold(word)
    if len(head) < 3:
        return None
    inn_words = {w for k in keys for w in k.split()}
    for s in product.get("substances") or []:
        inn_words.update(fold(re.sub(r"\([^)]*\)", " ", s)).split())
    if head in inn_words or set(fold(raw).split()[1:]) & {w for k in keys for w in k.split()}:
        return None
    if set(fold(raw).split()) & GENERIC_LABS:
        return None
    return word


def brands_for(products: list[dict], keys: set[str]) -> list[dict]:
    """Distinct ``{name, quote, cis}`` brands of the marketed products, first CIS wins."""
    out: dict[str, dict] = {}
    for p in sorted(products, key=lambda p: p["cis"]):
        if not p["marketed"] or "active" not in p["status"].lower():
            continue
        quote = brand_of(p, keys)
        if quote and fold(quote) not in out:
            out[fold(quote)] = {"name": display_brand(quote), "quote": quote,
                                "cis": p["cis"]}
    return list(out.values())


def display_brand(quote: str) -> str:
    """The table's upper-case brand in the casing the stored brands use ("Havlane")."""
    return "-".join(part.capitalize() for part in quote.split("-"))


def is_plain_oral(product: dict) -> bool:
    text = f"{product['denomination']} {product['form']}"
    return "orale" in product["route"].lower() and not MODIFIED_RELEASE.search(text)


def rank(products: list[dict], keys: set[str]) -> list[tuple[dict, str]]:
    """Marketed products in the order an RCP is tried, each with the ``why`` it was."""
    marketed = [p for p in products
                if p["marketed"] and "active" in p["status"].lower()]
    plain = [p for p in marketed if is_plain_oral(p)]
    if plain:
        pool, why = plain, "plain oral"
    else:
        # Never a local route (an eye drop's 5.2 is not systemic kinetics) or a patch
        # (a sustained-delivery peak, like a modified-release one).
        pool = [p for p in marketed
                if not MODIFIED_RELEASE.search(f"{p['denomination']} {p['form']}")
                and not LOCAL_ROUTES.search(p["route"])
                and "transdermique" not in p["route"].lower()]
        why = "no plain-oral product; non-modified-release {route}"
    # A brand-name product (the originator's RCP, usually the fullest 5.2) before a
    # generic restating it; then CIS order for determinism.
    pool = sorted(pool, key=lambda p: (brand_of(p, keys) is None, p["cis"]))
    return [(p, why.format(route=p["route"]) + ("" if brand_of(p, keys) is None
                                                  else ", brand-name product"))
            for p in pool]


# A numbered sub-heading left as a plain paragraph ("<p>4.4. Mises en garde ...</p>"):
# capitalised and short, so a body cross-reference ("(voir rubriques 4.4 et 5.3)") is not one.
_PLAIN_HEAD = r"<p>\s*{num}\.?\s+[A-ZÀ-Ý][^<]{{2,110}}</p>"


def section_body(page_html: str, number: str, anchor: str) -> str | None:
    """The raw HTML of one RCP section (``number`` like ``"5.2"``, its ``anchor`` name
    like ``"RcpPropPharmacocinetiques"``), from just after its heading paragraph up to
    the next level-1/2 heading, or None when the page lacks it. An ANSM page marks the
    heading with an id / anchor, an EMA SmPC only by its ``AmmAnnexeTitre2`` text (or, when
    the converter missed it, a short bare numbered paragraph). Shared by every
    section reader (5.2 here, 4.2 / 4.3 / 4.4 in ``fetch_bdpm_rcp.py``)."""
    m = re.search(r"id=['\"]" + re.escape(number + ".") + r"[^'\"]*['\"]", page_html)
    if not m:
        m = re.search(r"name=['\"]" + re.escape(anchor) + r"['\"]", page_html)
    if not m:   # an EMA SmPC (justelesRCP data/eu/): a bare numbered heading, no anchor
        m = re.search(r"<(?:p|h\d)[^>]*class=\"?AmmAnnexeTitre2\"?[^>]*>\s*"
                      + re.escape(number) + r"\.?\s", page_html)
    plain = None
    if not m:   # an SmPC whose PDF converter missed the heading: a short bare paragraph
        plain = _PLAIN_HEAD.format(num=re.escape(number))
        m = re.search(plain, page_html)
    if not m:
        return None
    close = None if plain else re.compile(r"</(?:p|h\d)>", re.I).search(page_html, m.end())
    start = close.end() if close else m.end() if plain else len(page_html)
    end_m = re.search(r"class=\"?AmmAnnexeTitre[12]\"?"
                      + ("|" + _PLAIN_HEAD.format(num=r"\d+\.\d+") if plain else ""),
                      page_html[start:])
    if end_m:
        stop = page_html.rfind("<", start, start + end_m.start())   # the heading's <p
        return page_html[start:stop if stop > start else start + end_m.start()]
    return page_html[start:]


def html_lines(body: str) -> list[str]:
    """An RCP HTML slice as text lines, one paragraph per line, bullets stripped."""
    body = re.sub(r"</(p|li|td|tr|div|h\d)>|<br\s*/?>", "\n", body, flags=re.I)
    out = []
    for line in re.sub(r"<[^>]+>", "", body).splitlines():
        line = " ".join(html.unescape(line).replace("\xa0", " ").split()).lstrip("·•▪- ")
        if len(line) > 1:
            out.append(line)
    return out


def fr_titles() -> dict[str, str]:
    """drug id -> the French Wikipedia title the brand pass (corpus #10) resolved."""
    if not BRAND_WORKLIST.exists():
        return {}
    wl = json.loads(BRAND_WORKLIST.read_text(encoding="utf-8"))
    return {did: v["fr_title"] for did, v in wl.items() if v.get("fr_title")}
