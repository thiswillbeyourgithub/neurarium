"""Render the emitted dataset as one Markdown page per node, served under ``/api/``.

The text twin of the viewer's detail panels, for LLM agents and anything that cannot run
WebGL: ``/api/`` lists every page, ``/api/drug/sertraline`` holds that drug's
stored fields in panel order, under the panel's own headings, subtitles and row labels
(read from ``public/js/i18n/en.js`` through the one table in ``api_sections.py``, the
stored field name kept in parentheses on a Facts line), with the panel's addons as
admonitions where its slots sit, each claim tagged with its grade + quote id on its own line (a claim's
``*_sources`` / ``*_provenance`` keys are folded into it, never a separate section) and the
verbatim quotes listed once at the end of the page. A grades legend heads every page and an
``llm`` grade is spelled out as UNSOURCED, so a reader never takes LLM memory for a citation.
Each section is also its own page, at its stored field name (``/api/drug/sertraline/bindings``, listed at
``/api/drug/sertraline/``), carrying only the sources it cites.

**Stored fields only**, with one exception: the BETA ``/api/effect/<id>`` pages (an effect
-> the receptors whose stored nodes carry it -> the drugs whose bindings could reach it),
the same index the viewer's Effects panel reads (``data_generators/effect_index.py``),
labelled as derived on the page. Everything the viewer derives in the browser (presynaptic
modulation, net neurotransmission, pharmacokinetic interactions, the simulation) is not here, so
nothing duplicates the JS that computes it. The rendering is generic (a record's keys in
order, nested values as bullets), so a new data field shows up with no edit here, though
``tests/test_panel_md_parity.py`` fails until ``api_sections.py`` decides how it is worded
(as it does for a new panel heading with no Markdown twin).

Built into the Docker image (``docker/Dockerfile``, ``api`` stage), never committed:
``python tools/render_api.py --out <dir>``. ``--effects-out <file>`` also (or only) writes
the viewer's effect index (``effect_index.to_json``, served at ``/derived/effects.json``;
``tools/serve.py`` calls ``write_effects`` itself). Stdlib only.

Every written page carries, under its title, a Caddy template (``UPTIME``, executed per
request by the ``templates`` directive on ``/api/*`` in ``docker/Caddyfile``) that on a DEV
instance says roughly how long ago the server restarted, so an agent reading a page knows
it may have changed recently. Off DEV it renders to nothing and the page reads as built.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

# Both explicit: the Docker stage runs `python -I`, which never adds the script dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "data_generators"))
from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib.structure_ids import base_id  # noqa: E402 (the one hemisphere-suffix rule)
import effect_index  # noqa: E402 (the effect -> receptors -> drugs join, BETA)
import llms_txt  # noqa: E402 (SITE_URL + the version, defined once there)
import node_id  # noqa: E402 (the id shape check_data enforces)
import api_sections as AS  # noqa: E402 (the panel's labels + layout, one table)

PUBLIC = Path(__file__).resolve().parent.parent / "public"
COLLECTIONS = ("structures", "projections", "circuits", "projection_groups",
               "receptors", "drugs", "metabolites", "addons")

# Presentation-only fields (geometry, colours, images), each with its reason there.
SKIP = set(AS.HIDDEN)
# The viewer's `#tabs=<kind>:<id>` opener for each page kind, where one exists.
TAB_KIND = {"drug": "drug", "receptor": "target", "target": "target", "structure": "structure",
            "circuit": "circuit", "group": "group", "effect": "effect"}
# What JS encodeURIComponent leaves unescaped, so a page URL matches the viewer's byte for byte.
URI_SAFE = "-_.!~*'()"
API = "/api"  # absolute links, so a page reads the same served at any address (the 404)
NOT_FOUND = ("**No page at this address.** Page paths are `/api/<kind>/<id>` with a singular "
             "kind and the record id (lowercase, underscores, e.g. `/api/drug/sertraline`, "
             "`/api/drug/amphetamine_dl`, `/api/structure/putamen_R`); a pathway id is "
             "`<from>--<to>`. Every valid page is listed below with its id.")
# What each grade means, stated once at the top of every page so a reader never takes an
# LLM-memory claim for a sourced one. Mirrors the viewer's pills (PROVENANCE_LEVELS).
GRADES = ("Grades: `verified` = the quote was found verbatim on the cited page and a separate "
          "LLM judge confirmed it states the claim; `sourced` = written from the cited document, "
          "but the quote was not checked; `llm` = UNSOURCED, produced by an LLM from memory and "
          "never checked against any document, so treat it as unverified general knowledge, not "
          "as a citation; `uncertain` bullets list reasons to doubt an otherwise backed claim. A "
          "claim with no [grade] tag next to it has no source at all.")
LLM_FLAG = " (UNSOURCED: LLM memory, unchecked)"
# A claim's sources sit under `<claim>_sources` / `<claim>_provenance`; these name the
# claim key where the stem alone does not (`category_sources` grades `categories`).
SOURCE_SUFFIXES = ("_sources", "_provenance")
CLAIM_ALIASES = {"category": ("categories",), "originator_now": ("originator",),
                 "location": ("locations", "regions")}
# Source keys that grade the record as a whole, not one field: kept as a Facts line.
RECORD_GRADES = {"classification_provenance"}
# The restart line (see the module docstring). Custom delimiters `{{%` / `%}}` so no page
# text can be taken for template syntax (render() refuses a page containing them). DEV and
# STARTED_AT are the container env (docker-compose.yml, docker/entrypoint.sh); the age is
# coarse on purpose, like /status.json's floored start time. `now`, `env`, `atoi`, `sub`,
# `div` and `unixEpoch` are sprig functions, which Caddy templates include.
UPTIME_OPEN, UPTIME_CLOSE = "{{%", "%}}"
UPTIME = (
    '{{%if and (eq (env "DEV") "1") (env "STARTED_AT")%}}'
    '{{%$up := sub (now | unixEpoch | atoi) (env "STARTED_AT" | atoi)%}}'
    "\n> This server restarted "
    "{{%if lt $up 3600%}}less than an hour"
    "{{%else if lt $up 7200%}}about an hour"
    "{{%else if lt $up 86400%}}about {{%div $up 3600%}} hours"
    "{{%else if lt $up 172800%}}about a day"
    "{{%else%}}about {{%div $up 86400%}} days{{%end%}}"
    " ago (a development instance): this page may have changed recently.\n\n"
    "{{%end%}}")


def with_uptime(text: str) -> str:
    """``text`` with the UPTIME template after its title line (blank lines around it when
    shown, so the quote never runs into the next line). Refuses page text that already holds the delimiters."""
    if UPTIME_OPEN in text or UPTIME_CLOSE in text:
        raise ValueError(f"page text contains the template delimiters {UPTIME_OPEN} / {UPTIME_CLOSE}")
    head, _, tail = text.partition("\n")
    return f"{head}\n{UPTIME}{tail}"


def with_byline(text: str) -> str:
    """``text`` with the author credit (llms_txt.BYLINE) as its own paragraph under the
    title line, so every page an LLM reads names the site and its author."""
    head, _, tail = text.partition("\n")
    return f"{head}\n\n{llms_txt.BYLINE}\n{tail}"


def stamped(text: str) -> str:
    """A page as written: the byline, then the DEV restart line, under its title."""
    return with_uptime(with_byline(text))


KIND_TITLES = {"drug": "Drugs", "metabolite": "Active metabolites", "receptor": "Receptors",
               "target": "Other drug targets", "structure": "Brain regions",
               "projection": "Pathways", "circuit": "Circuits", "group": "Projection groups",
               "effect": "Clinical effects (BETA, derived)"}


def load(data_dir: Path) -> dict[str, Any]:
    """Every emitted collection, the meta object and the quote table, keyed by name."""
    data: dict[str, Any] = {
        name: [json.loads(line) for line in
               (data_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if line]
        for name in COLLECTIONS}
    data["meta"] = json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))
    data["quotes"] = {q["id"]: q for q in (json.loads(line) for line in
                      (data_dir / "quotes.jsonl").read_text(encoding="utf-8").splitlines() if line)}
    return data


def projection_id(p: dict[str, Any]) -> str:
    return f"{p['from']}--{p['to']}"


class Renderer:
    def __init__(self, data: dict[str, Any]):
        self.quotes = data["quotes"]
        self.corpora = data["meta"]["source_corpora"]
        targets = {tid: {"id": tid, **t} for tid, t in data["meta"]["drug_targets"].items()
                   if not t.get("receptor")}
        # kind -> id -> record: the pages, and the link targets.
        self.pages: dict[str, dict[str, dict[str, Any]]] = {
            "drug": {r["id"]: r for r in data["drugs"]},
            "metabolite": {r["id"]: r for r in data["metabolites"]},
            "receptor": {r["id"]: r for r in data["receptors"]},
            "target": targets,
            "structure": {r["id"]: r for r in data["structures"]},
            "projection": {projection_id(r): r for r in data["projections"]},
            "circuit": {r["id"]: r for r in data["circuits"]},
            "group": {r["id"]: r for r in data["projection_groups"]},
        }
        self.modes = data["meta"].get("receptor_effect_modes") or {}
        self.effects = {e["id"]: e for e in effect_index.build(
            data["receptors"], data["drugs"], data["metabolites"], data["meta"])}
        self.pages["effect"] = {eid: {"name": e["label"]} for eid, e in self.effects.items()}
        # A receptor/target region list names the hemisphere-less base ("frontal"), the
        # structures list the emitted right-hand id ("frontal_R").
        self.base_to_structure = {}
        for sid in self.pages["structure"]:
            self.base_to_structure.setdefault(base_id(sid), sid)
        self.addons = data["addons"]
        self.value_labels = {k: data["meta"].get(m) or {} for k, m in AS.VALUE_LABELS.items()}

    # -- links ---------------------------------------------------------------------------
    def link(self, kind: str, ident: str, label: str | None = None) -> str:
        if kind == "structure" and ident not in self.pages["structure"]:
            ident = self.base_to_structure.get(ident, ident)
            base = self.pages["structure"].get(ident, {}).get("base_name")
            label = label or base
        if kind == "target" and ident in self.pages["receptor"]:
            kind = "receptor"
        record = self.pages.get(kind, {}).get(ident)
        if record is None:
            return label or ident
        return f"[{label or record.get('name') or record.get('label') or ident}]({API}/{kind}/{ident})"

    def linked(self, key: str, value: Any, parent: str) -> str | None:
        """``value`` as a link when ``key`` names another node, else None."""
        if not isinstance(value, str):
            return None
        if key in ("target",):
            return self.link("target", value)
        if key in ("from", "to", "structure") or parent in ("structures", "regions", "locations",
                                                            "location_sources", "profile"):
            return self.link("structure", value)
        if key == "drug_id" or (key == "owner" and parent == "drug"):
            return self.link("drug", value)
        if key == "id" and parent == "metabolites":
            return self.link("metabolite", value)
        return None

    # -- sources -------------------------------------------------------------------------
    @staticmethod
    def is_ref(v: Any) -> bool:
        return isinstance(v, dict) and ("quote_id" in v or ("corpus" in v and "provenance" in v))

    def source(self, ref: dict[str, Any]) -> str:
        grade = ref.get("provenance", "llm")
        q = self.quotes.get(ref.get("quote_id") or "")
        corpus = (q or ref).get("corpus")
        where = self.corpora.get(corpus, {}).get("ref", corpus or "unknown source")
        extra = "; ".join(f"{k}: {v}" for k, v in ref.items()
                          if k not in ("corpus", "provenance", "quote_id", "pipeline") and v is not None)
        flag = LLM_FLAG if grade == "llm" else ""
        if q:
            self.cited.setdefault(q["id"], q)
            return f"[{grade} {q['id']}]{flag}" + (f" ({extra})" if extra else "")
        # A bare database row links where the viewer's Ki tooltip does: its own
        # reference URL, else the corpus's generic one.
        url = self.page_link(corpus, ref.get("page"))
        if url and "http" not in extra:
            extra = f"{extra}; {url}" if extra else url
        return f"[{grade}]{flag} {where}" + (f" ({extra})" if extra else "")

    # -- values --------------------------------------------------------------------------
    def scalar(self, key: str, v: Any, parent: str) -> str:
        if isinstance(v, list):
            return ", ".join(self.linked(key, x, key) or str(x) for x in v)
        return self.linked(key, v, parent) or str(v)

    @staticmethod
    def is_scalar(v: Any) -> bool:
        return not isinstance(v, (dict, list)) or (
            isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v))

    def value(self, key: str, v: Any, depth: int, parent: str = "") -> list[str]:
        """Bullet lines for ``v`` (the value under ``key``), indented to ``depth``."""
        pad = "  " * depth
        if self.is_ref(v):
            return [f"{pad}- source: {self.source(v)}"]
        if isinstance(v, list) and v and all(self.is_ref(x) for x in v):
            return [f"{pad}- {self.source(x)}" for x in v]
        if isinstance(v, dict):
            out = []
            att, sourced = self.attach(v)
            for k, x in v.items():
                if k in sourced:
                    continue
                tags, nested = self.inline(v, att, k, depth + 1, key)
                if self.is_ref(x):
                    out.append(f"{pad}- {k}: {self.source(x)}")
                elif self.is_scalar(x):
                    out.append(f"{pad}- {self.linked(k, k, key) or k}: {self.scalar(k, x, key)}"
                               f"{self.flag(k, x)}{tags}")
                else:
                    out.append(f"{pad}- {self.linked(k, k, key) or k}:{tags}")
                    out += self.value(k, x, depth + 1, key)
                out += nested
            return out
        if isinstance(v, list):
            out = []
            for item in v:
                if not isinstance(item, dict):
                    out.append(f"{pad}- {self.scalar(key, item, key)}")
                    continue
                att, sourced = self.attach(item)
                # The item's own `sources` grade the item: on its line, not below it.
                own = item.get("sources")
                own_tags = (self.tags("sources", own) if "sources" not in sourced
                            and isinstance(own, list) and own else None)
                parts, rest = [], []
                for k, x in item.items():
                    if k in sourced or (k == "sources" and own_tags):
                        continue
                    tags, nested = self.inline(item, att, k, depth + 2, key)
                    if self.is_scalar(x):
                        parts.append(f"{k}: {self.scalar(k, x, key)}{self.flag(k, x)}{tags}")
                    else:
                        rest.append(f"{pad}  - {k}:{tags}")
                        rest += self.value(k, x, depth + 2, key)
                    rest += nested
                head = "; ".join(parts) or "(item)"
                out.append(f"{pad}- {head}" + (f" {own_tags}" if own_tags else ""))
                out += rest
            return out
        return [f"{pad}- {self.scalar(key, v, parent)}"]

    # -- pages ---------------------------------------------------------------------------
    def page_link(self, corpus: str | None, page: Any) -> str | None:
        """The link for one cited page, as the viewer's tooltip resolves it: the corpus's
        stored ``page_urls[page]``, else its ``{page}`` template, else its landing ``url``."""
        c = self.corpora.get(corpus, {})
        if page is not None:
            if c.get("page_urls", {}).get(str(page)):
                return c["page_urls"][str(page)]
            if c.get("page_url"):
                return c["page_url"].replace("{page}", quote(str(page), safe=URI_SAFE))
        return c.get("url")

    def effect_page(self, ident: str) -> str:
        """An effect's page (BETA): its stored owners by mode, then the derived drugs."""
        e = self.effects[ident]
        lines = [f"# {e['label']}", "", f"Kind: effect (BETA). Id: `{ident}`.",
                 f"Open in the viewer: {llms_txt.SITE_URL}/#tabs=effect:{ident}",
                 "Derived, not medical advice. The receptors and targets below carry a sourced "
                 "receptor_effect node for this effect (a statement about acting on the receptor "
                 "in that mode). The drugs are derived, never stored: one of their directional "
                 "bindings acts on such a receptor in a direction the mode covers, so each COULD "
                 "cause it; a drug listed here does not necessarily cause it. "
                 f"Index: [all pages]({API}/)."]
        owners_h, owners_intro = self.heading("effect", "owners", {})
        drugs_h, drugs_intro = self.heading("effect", "drugs", {})
        lines += ["", "## " + AS.fill(owners_h, n=len(e["owners"])), ""] + owners_intro[:-1]
        for label, owners in effect_index.owners_by_mode(e, self.modes):
            lines += ["", f"### {label}", ""]
            for o in owners:
                srcs = " ".join(self.source(s) for s in o["node"].get("sources") or [])
                doubt = ", ".join(u["kind"] for u in o["node"].get("uncertainty") or [])
                note = f" (uncertain: {doubt})" if doubt else ""
                lines.append(f"- {self.link(o['kind'], o['id'])}{note} {srcs}".rstrip())
        lines += ["", "## " + AS.fill(drugs_h, n=len(e["drugs"])), ""] + drugs_intro
        for d in sorted(e["drugs"], key=lambda d: str(d["drug"].get("name") or d["drug"]["id"]).lower()):
            via = ", ".join(f"{self.link('target', b['target'])} {b['action']}"
                            + (f" via {b['via_metabolite']}" if b.get("via_metabolite") else "")
                            for b, _ in d["via"])
            lines.append(f"- {self.link('drug', d['drug']['id'])}: {via}")
        lines += self.sources_section()
        return "\n".join(lines) + "\n"

    @staticmethod
    def claim_of(key: str, rec: dict[str, Any]) -> str | None:
        """The field a ``<claim>_sources`` / ``<claim>_provenance`` key grades, or None
        when ``key`` is not a source key (or grades the whole record)."""
        if key in RECORD_GRADES:
            return None
        for suffix in SOURCE_SUFFIXES:
            if key.endswith(suffix):
                stem = key[:-len(suffix)]
                return next((c for c in (stem, *CLAIM_ALIASES.get(stem, ())) if c in rec), None)
        return None

    @staticmethod
    def flag(key: str, v: Any) -> str:
        """The UNSOURCED warning after a bare `llm` grade value (`*_provenance`, `grade`)."""
        return LLM_FLAG if v == "llm" and (key == "grade" or key.endswith("_provenance")) else ""

    def tags(self, key: str, v: Any) -> str | None:
        """``v`` (a source key's value) as inline grade tags, or None when it is a nested
        structure (a per-region map) that needs its own bullets."""
        if isinstance(v, str):  # a bare grade (`*_provenance`)
            return f"[{v}]" + (LLM_FLAG if v == "llm" else "")
        if isinstance(v, list) and all(self.is_ref(x) for x in v):
            return " ".join(self.source(x) for x in v)
        if self.is_ref(v):
            return self.source(v)
        return None

    def attach(self, d: dict[str, Any]) -> tuple[dict[str, list[str]], set[str]]:
        """claim key -> the source keys grading it, and the set of those source keys."""
        att: dict[str, list[str]] = {}
        for k in d:
            claim = self.claim_of(k, d)
            if claim:
                att.setdefault(claim, []).append(k)
        return att, {k for ks in att.values() for k in ks}

    def inline(self, d: dict[str, Any], att: dict[str, list[str]], k: str, depth: int,
               parent: str) -> tuple[str, list[str]]:
        """(" [tags]" to append to claim ``k``'s line, nested bullets for a source that
        cannot be inlined). A bare `*_provenance` grade is shown only when no quoted source
        sits beside it, since each quote already carries its own grade."""
        keys = att.get(k, [])
        quoted = any(not isinstance(d[sk], str) for sk in keys)
        tags, nested = [], []
        for sk in keys:
            if quoted and isinstance(d[sk], str):
                continue
            tag = self.tags(sk, d[sk])
            if tag is None:
                nested += ([f"{'  ' * depth}- {sk.replace('_', ' ')}:"]
                           + self.value(sk, d[sk], depth + 1, parent))
            else:
                # Name a second source key (`originator_now_sources`) so it is not read as
                # the claim's own.
                stem = sk.rsplit("_", 1)[0]
                extra = stem.removeprefix(f"{k}_") if stem.startswith(f"{k}_") else ""
                tags.append(f"({extra.replace('_', ' ')}: {tag})" if extra else tag)
        return (" " + " ".join(tags)) if tags else "", nested

    # -- panel labels (api_sections) -------------------------------------------------------
    def fact_label(self, kind: str, k: str, rec: dict[str, Any]) -> str:
        """A Facts line's label: the panel's row label, the field name after it so a
        reader can match /data, else the bare field name."""
        lab = AS.label(kind, k)
        txt = AS.text(lab.key, rec) if lab else None
        return f"{txt} ({k})" if txt else k

    def heading(self, kind: str, k: str, rec: dict[str, Any]) -> tuple[str, list[str]]:
        """A section's heading (the panel's) and the lines opening it: the subtitle in
        italics, then the panel section it sits inside, when it has one."""
        lab = AS.label(kind, k)
        if lab is None:
            return k.replace("_", " "), []
        intro = []
        sub = AS.text(lab.sub, rec)
        if sub:
            intro += [f"*{sub}*", ""]
        parent = AS.parent_text(lab)
        if parent:
            intro += [f"In the viewer under: {parent}.", ""]
        return AS.text(lab.key, rec) or k.replace("_", " "), intro

    def worded(self, kind: str, k: str, v: Any) -> str:
        """A stored value as the panel words it (``ssri`` -> ``SSRI (ssri)``), via the
        meta label map api_sections.VALUE_LABELS names; unchanged when it has none."""
        labels = self.value_labels.get((kind, k))
        if not labels:
            return self.scalar(k, v, kind)
        one = lambda x: f"{labels[x]} ({x})" if labels.get(x) not in (None, x) else str(x)  # noqa: E731
        return ", ".join(map(one, v)) if isinstance(v, list) else one(v)

    def folded(self, kind: str, rec: dict[str, Any]) -> dict[str, str]:
        """``attribute -> inline tags`` from a per-attribute grade map (a receptor's
        ``classification``), so each grade rides its attribute's line as the pill does."""
        out: dict[str, str] = {}
        for field in (f for kd, f in AS.FOLDED if kd == kind and isinstance(rec.get(f), dict)):
            for attr, entry in rec[field].items():
                srcs = entry.get("sources")
                tag = self.tags("sources", srcs) if srcs else self.tags("grade", entry.get("grade") or "llm")
                doubt = ", ".join(u.get("kind", "") for u in entry.get("uncertainty") or [])
                out[attr] = f" {tag}" + (f" (uncertain: {doubt})" if doubt else "")
        return out

    # -- addons ------------------------------------------------------------------------------
    def notes(self, kind: str, rec: dict[str, Any]) -> dict[str | None, list[dict[str, Any]]]:
        """This page's addons by the field whose section holds them (None: page top),
        placed per api_sections.SLOT_PLACE. A ``section.*`` addon belongs to a panel
        section, so it lands on every page that shows that section."""
        out: dict[str | None, list[dict[str, Any]]] = {}
        own = {self.ident, base_id(self.ident)} if kind == "structure" else {self.ident}
        for a in sorted(self.addons, key=lambda a: a["owner_kind"] != "section"):
            pkind, fields = AS.SLOT_PLACE[a["slot"]]
            if pkind != kind or (a["owner_kind"] != "section" and a["owner"] not in own):
                continue
            field = next((f for f in fields if f in rec), None)
            if fields and field is None and a["owner_kind"] == "section":
                continue  # the section it annotates is not on this page
            out.setdefault(field, []).append(a)
        return out

    def note_lines(self, notes: list[dict[str, Any]]) -> list[str]:
        """Each addon as the panel's admonition box: a blockquote, title, tone, grade."""
        lines = []
        for a in notes:
            tags = self.tags("sources", a["sources"]) if a.get("sources") else ""
            basis = " (about this dataset, not a claim a source could back)" \
                if a.get("basis") == "dataset" else ""
            lines += ["", f"> **{a['title']}** ({a.get('tone', 'info')}){basis} {tags}".rstrip(),
                      f"> {a['text']}"]
        return lines

    def sections(self, kind: str, rec: dict[str, Any]) -> list[tuple[str, str, list[str], dict]]:
        """The page body as (slug, heading, lines, quotes cited) sections, in panel order
        (api_sections.FIELDS), headed and labelled with the panel's own words. Each source
        key renders next to the claim it grades, never in a section of its own. The
        page-top addons are left in ``self.top`` as (lines, quotes cited)."""
        att, sourced = self.attach(rec)
        out = []
        notes = self.notes(kind, rec)
        self.cited = {}
        self.top = (self.note_lines(notes.get(None, [])), self.cited)
        self.cited = {}
        facts = []
        folded = self.folded(kind, rec)
        is_section = lambda k, v: not self.is_scalar(v) or (  # noqa: E731
            AS.label(kind, k) or AS.Label(None)).section
        # A graded claim with no field of its own (a target's derived `polarity` flag):
        # its grade and its quotes still share one line, named after the claim.
        orphans: dict[str, list[str]] = {}
        for k in rec:
            stem = next((k[:-len(x)] for x in SOURCE_SUFFIXES if k.endswith(x)), None)
            if stem and k not in RECORD_GRADES and k not in sourced:
                orphans.setdefault(stem, []).append(k)
        for stem, keys in orphans.items():
            pseudo = {stem: "", **{k: rec[k] for k in keys}}
            tags, nested = self.inline(pseudo, {stem: keys}, stem, 1, kind)
            facts += [f"- {self.fact_label(kind, stem, rec)}:{tags}"] + nested
            sourced = sourced | set(keys)
        keys = AS.order(kind, rec)
        # The sections the panel shows empty (api_sections.ALWAYS): their fields hold
        # nothing worth a line, the placeholder below says so once.
        empty = AS.empty_sections(kind, rec, self.derived_sections(kind, rec))
        hush = {f for _, sec in empty for f in AS.section_fields(kind, sec.key)}
        for k in keys:
            v = rec[k]
            if k in SKIP or k in sourced or k in hush or is_section(k, v):
                continue
            line = (f"- {self.fact_label(kind, k, rec)}: {self.worded(kind, k, v)}"
                    f"{self.flag(k, v)}{folded.get(k, '')}")
            tags, nested = self.inline(rec, att, k, 1, kind)
            facts += [line + tags] + nested
        own = rec.get("sources")
        if isinstance(own, list) and own and all(self.is_ref(x) for x in own):
            # The record's own sources (a group's, a circuit's): they back the record as a
            # whole, so they sit with its facts rather than in a "sources" section.
            lab = AS.text((AS.label(kind, "sources") or AS.Label(None)).key, rec)
            name = f"{lab} (sources, this {kind} as a whole)" if lab \
                else f"sources (this {kind} as a whole)"
            facts.append(f"- {name}: {self.tags('sources', own)}")
            sourced = sourced | {"sources"}
        if facts:
            out.append(("facts", "Facts", facts, self.cited))
        folds = {f for kd, f in AS.FOLDED if kd == kind}
        for k in keys:
            v = rec[k]
            if k in SKIP or k in sourced or k in folds or k in hush or not is_section(k, v):
                continue
            self.cited = {}
            head, lines = self.heading(kind, k, rec)
            lines = lines + self.value(k, v, 0, kind)
            tags, nested = self.inline(rec, att, k, 0, kind)
            if tags:
                lines.append(f"- sources:{tags}")
            out.append((k, head, lines + nested + self.note_lines(notes.get(k, [])), self.cited))
        return self.with_empty(kind, out, empty)

    def derived_sections(self, kind: str, rec: dict[str, Any]) -> frozenset[str]:
        """Slugs a viewer-only derived list fills on this page: the drug panel's ClinPGx
        variants (receptor-variants.js variantsForDrug) keep its Pharmacogenomics
        section from reading "no information" when only CPIC is missing."""
        if kind != "drug":
            return frozenset()
        did = rec.get("id")
        named = any(did in (v.get("drugs") or [])
                    for k in ("receptor", "target") for t in self.pages[k].values()
                    for v in t.get("variants") or [])
        return frozenset({"pharmacogenomics"}) if named else frozenset()

    @staticmethod
    def with_empty(kind: str, out: list, empty: list) -> list:
        """``out`` with one placeholder section per empty panel section, each where the
        panel puts it: before the first rendered section that comes after it in panel
        order. Its heading, subtitle, enclosing sections and sentence are the panel's."""
        order = list(AS.FIELDS[kind])
        pos = lambda slug: order.index(slug) if slug in order else -1  # noqa: E731
        for slug, sec in empty:
            sub, parent = AS.section_head(kind, sec.key)
            lines = ([f"*{AS.EN[sub]}*", ""] if sub else []) \
                + ([f"In the viewer under: {parent}.", ""] if parent else []) \
                + [AS.EN[sec.none] if sec.none else AS.no_data(kind, sec.key)]
            at = order.index(AS.anchor(kind, sec.key))
            i = next((i for i, (s, *_) in enumerate(out) if s != "facts" and pos(s) > at), len(out))
            out.insert(i, (slug, AS.EN[sec.key], lines, {}))
        return out

    def header(self, kind: str, ident: str, rec: dict[str, Any], title: str) -> list[str]:
        lines = [f"# {title}", "", f"Kind: {kind}. Id: `{ident}`."]
        if kind in TAB_KIND:
            lines.append(f"Open in the viewer: {llms_txt.SITE_URL}/#tabs={TAB_KIND[kind]}:{ident}")
        if rec.get("mirror"):
            lines.append("Paired: stated once for the right hemisphere, the left twin is implied.")
        lines.append("Each claim lists its sources as [grade quote_id] on the same line; the verbatim "
                     "quotes are under Sources at the end (also in /data/quotes.jsonl by id). A source "
                     f"without a quote id (a database row) is spelled out inline. {GRADES} "
                     f"Index: [all pages]({API}/).")
        return lines

    def sources_section(self, cited: dict | None = None) -> list[str]:
        """The quotes cited (this page's, or one section's), once each, first-cited order."""
        cited = self.cited if cited is None else cited
        if not cited:
            return []
        lines = ["", "## Sources", ""]
        for qid, q in cited.items():
            where = self.corpora.get(q.get("corpus"), {}).get("ref", q.get("corpus"))
            has_page = q.get("page") not in (None, "")
            page = f", {q['page']}" if has_page else ""
            # The page's public URL, the link the viewer's tooltip shows (see page_link).
            link = self.page_link(q.get("corpus"), q['page'] if has_page else None)
            link = f" {link}" if link else ""
            lines.append(f"- `{qid}` ({where}{page}){link}: \"{q['quote']}\"")
        return lines

    def page_set(self, kind: str, ident: str, rec: dict[str, Any]) -> dict[str | None, str]:
        """``{page: Markdown}``: the full page under ``None``, plus one page per section slug
        (and an ``index`` listing them), served under ``<id>/`` so a reader can fetch only
        the part it needs."""
        if kind == "effect":
            self.cited = {}
            return {None: self.effect_page(ident)}
        title = rec.get("name") or rec.get("label") or ident
        self.ident = ident
        secs = self.sections(kind, rec)
        base = f"{API}/{kind}/{ident}"
        toc = ("Sections (each also its own page): "
               + ", ".join(f"[{h}]({base}/{slug})" for slug, h, _, _ in secs)) if secs else ""
        head = self.header(kind, ident, rec, title)
        top, cited = self.top  # the page-top addons, under the title as in the panel
        full = head + ([toc] if toc else []) + top
        cited = dict(cited)
        for _, h, body, c in secs:
            full += ["", f"## {h}", ""] + body
            for qid, q in c.items():
                cited.setdefault(qid, q)
        out: dict[str | None, str] = {None: "\n".join(full + self.sources_section(cited)) + "\n"}
        if secs:
            out["index"] = "\n".join(head + [toc, f"Full page: [{title}]({base})"]) + "\n"
        for slug, h, body, c in secs:
            sub = self.header(kind, ident, rec, f"{title}: {h}")
            sub.append(f"One section of [{title}]({base}); other sections: [{ident}]({base}/).")
            out[slug] = "\n".join(sub + ["", f"## {h}", ""] + body
                                                  + self.sources_section(c)) + "\n"
        return out

    def page(self, kind: str, ident: str, rec: dict[str, Any]) -> str:
        return self.page_set(kind, ident, rec)[None]

    def listing(self, kind: str) -> list[str]:
        """One kind's pages, by name, as a Markdown section."""
        records = self.pages[kind]
        lines = ["", f"## [{KIND_TITLES[kind]}]({API}/{kind}/) ({len(records)})", ""]
        for ident, rec in sorted(records.items(),
                                 key=lambda kv: str(kv[1].get("name") or kv[1].get("label") or kv[0]).lower()):
            name = rec.get("name") or rec.get("label") or ident
            lines.append(f"- [{name}]({API}/{kind}/{ident}) `{ident}`")
        return lines

    def index(self, version: str, kinds: list[str] | None = None, lead: str = "") -> str:
        """The page list (every kind, or just ``kinds``), under ``lead`` when given."""
        lines = [f"# Neurarium API (version {version})", ""]
        if lead:
            lines += [lead, ""]
        lines.append("One Markdown page per node of the dataset: stored fields only, each claim tagged "
                     "[grade quote_id], the verbatim quotes listed under Sources at the end of each "
                     "page, except the BETA effect pages, a derived effect -> receptors -> drugs "
                     "index. The human version (the 3D viewer) shows slightly more: what else it "
                     "computes in the browser from these facts (a drug's predicted effects, presynaptic "
                     "modulation, net neurotransmission, pharmacokinetic interactions, simulation) is not included. "
                     f"Every page: [{API}/]({API}/). Overview and raw data: {llms_txt.SITE_URL}/llms.txt")
        for kind in kinds or self.pages:
            lines += self.listing(kind)
        return "\n".join(lines) + "\n"


# A page named after one of these would overwrite the kind's listing or the 404 page.
RESERVED_PAGE_IDS = frozenset({"index", "not_found"})


def _check_page_id(kind: str, ident: Any) -> None:
    """Refuse an id that is not a plain node id before it becomes a file name, so a
    malformed record (``../x``, ``a/b``) can never write outside its kind directory."""
    if not isinstance(ident, str) or not node_id.PAGE_ID_RE.fullmatch(ident) \
            or ident in RESERVED_PAGE_IDS:
        raise ValueError(f"/api/{kind}: refusing to write page for malformed id {ident!r} "
                         f"(want {node_id.PAGE_ID_RE.pattern}, not {sorted(RESERVED_PAGE_IDS)})")


def render(data_dir: Path, out: Path, version: str) -> int:
    """Write every page under ``out`` (cleared first); returns the page count."""
    r = Renderer(load(data_dir))
    if out.exists():
        shutil.rmtree(out)
    n = 0
    for kind, records in r.pages.items():
        (out / kind).mkdir(parents=True)
        for ident, rec in records.items():
            _check_page_id(kind, ident)
            for section, text in r.page_set(kind, ident, rec).items():
                if section is None:
                    page_path(out / kind, ident).write_text(stamped(text), encoding="utf-8")
                else:  # a section page, under <id>/
                    sub = page_path(out / kind, ident).with_suffix("")
                    sub.mkdir(exist_ok=True)
                    page_path(sub, section).write_text(stamped(text), encoding="utf-8")
            n += 1
        (out / kind / "index.md").write_text(stamped(r.index(version, [kind])), encoding="utf-8")
    (out / "index.md").write_text(stamped(r.index(version)), encoding="utf-8")
    # Served (status 404) for any /api address with no page, so a mistyped or guessed
    # id still leads somewhere: the full list, ids shown, is the way out.
    (out / "not_found.md").write_text(stamped(r.index(version, lead=NOT_FOUND)), encoding="utf-8")
    return n


def write_effects(data_dir: Path, path: Path) -> int:
    """Write the viewer's effect index (``effect_index.to_json``) to ``path``; returns
    the effect count. One join for the viewer, the /api/ pages and llms.txt."""
    data = load(data_dir)
    index = effect_index.build(data["receptors"], data["drugs"], data["metabolites"],
                               data["meta"])
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written aside then renamed over, so a concurrent reader (tools/serve.py) sees the
    # old file or the new one, never a truncated one.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(effect_index.to_json(index), ensure_ascii=False,
                              separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
    return len(index)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--public", type=Path, default=PUBLIC,
                        help="Site root holding data/ and version.js (default: ../public).")
    parser.add_argument("--out", type=Path,
                        help="Directory to write the pages into (cleared first). Never under public/.")
    parser.add_argument("--effects-out", type=Path,
                        help="File to write the viewer's effect index into. Never under public/.")
    args = parser.parse_args()
    if not (args.out or args.effects_out):
        parser.error("give --out, --effects-out or both")
    if args.out:
        n = render(args.public / "data", args.out, llms_txt.app_version(args.public))
        print(f"wrote {n} pages + index.md to {args.out}")
    if args.effects_out:
        n = write_effects(args.public / "data", args.effects_out)
        print(f"wrote {n} effects to {args.effects_out}")


if __name__ == "__main__":
    main()
