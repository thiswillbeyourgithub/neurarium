"""Render the emitted dataset as one Markdown page per node, served under ``/api/``.

The text twin of the viewer's detail panels, for LLM agents and anything that cannot run
WebGL: ``/api/`` lists every page, ``/api/drug/sertraline`` holds that drug's
stored fields, each claim tagged with its grade + quote id and the verbatim quotes listed once
at the end of the page.

**Stored fields only**, with one exception: the BETA ``/api/effect/<id>`` pages (an effect
-> the receptors whose stored nodes carry it -> the drugs whose bindings could reach it),
the same index the viewer's Effects panel reads (``data_generators/effect_index.py``),
labelled as derived on the page. Everything the viewer derives in the browser (presynaptic
modulation, net neurotransmission, pharmacokinetic interactions, the simulation) is not here, so
nothing duplicates the JS that computes it. The rendering is generic (a record's keys in
order, nested values as bullets), so a new data field shows up with no edit here.

Built into the Docker image (``docker/Dockerfile``, ``api`` stage), never committed:
``python tools/render_api.py --out <dir>``. ``--effects-out <file>`` also (or only) writes
the viewer's effect index (``effect_index.to_json``, served at ``/derived/effects.json``;
``tools/serve.py`` calls ``write_effects`` itself). Stdlib only.
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

PUBLIC = Path(__file__).resolve().parent.parent / "public"
COLLECTIONS = ("structures", "projections", "circuits", "projection_groups",
               "receptors", "drugs", "metabolites", "addons")

# Presentation-only fields: geometry and colours mean nothing as text.
SKIP = {"id", "name", "color", "position", "shape_file", "shape", "focusable", "mirror",
        "structure_image", "structure_image_gallery"}
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
        self.addons: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for a in data["addons"]:
            self.addons.setdefault((a["owner_kind"], a["owner"]), []).append(a)

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
        if q:
            self.cited.setdefault(q["id"], q)
            return f"[{grade} {q['id']}]" + (f" ({extra})" if extra else "")
        # A bare database row links where the viewer's Ki tooltip does: its own
        # reference URL, else the corpus's generic one.
        url = self.page_link(corpus, ref.get("page"))
        if url and "http" not in extra:
            extra = f"{extra}; {url}" if extra else url
        return f"[{grade}] {where}" + (f" ({extra})" if extra else "")

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
            for k, x in v.items():
                if self.is_ref(x):
                    out.append(f"{pad}- {k}: {self.source(x)}")
                elif self.is_scalar(x):
                    out.append(f"{pad}- {self.linked(k, k, key) or k}: {self.scalar(k, x, key)}")
                else:
                    out.append(f"{pad}- {self.linked(k, k, key) or k}:")
                    out += self.value(k, x, depth + 1, key)
            return out
        if isinstance(v, list):
            out = []
            for item in v:
                if not isinstance(item, dict):
                    out.append(f"{pad}- {self.scalar(key, item, key)}")
                    continue
                head = "; ".join(f"{k}: {self.scalar(k, x, key)}" for k, x in item.items()
                                 if self.is_scalar(x))
                out.append(f"{pad}- {head or '(item)'}")
                for k, x in item.items():
                    if not self.is_scalar(x):
                        out.append(f"{pad}  - {k}:")
                        out += self.value(k, x, depth + 2, key)
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

    def sources_section(self) -> list[str]:
        """The quotes this page cited, once each, in first-cited order."""
        if not self.cited:
            return []
        lines = ["", "## Sources", ""]
        for qid, q in self.cited.items():
            where = self.corpora.get(q.get("corpus"), {}).get("ref", q.get("corpus"))
            has_page = q.get("page") not in (None, "")
            page = f", {q['page']}" if has_page else ""
            # The page's public URL, the link the viewer's tooltip shows (see page_link).
            link = self.page_link(q.get("corpus"), q['page'] if has_page else None)
            link = f" {link}" if link else ""
            lines.append(f"- `{qid}` ({where}{page}){link}: \"{q['quote']}\"")
        return lines

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
        lines += ["", f"## Mediating receptors and targets ({len(e['owners'])})"]
        for label, owners in effect_index.owners_by_mode(e, self.modes):
            lines += ["", f"### {label}", ""]
            for o in owners:
                srcs = " ".join(self.source(s) for s in o["node"].get("sources") or [])
                doubt = ", ".join(u["kind"] for u in o["node"].get("uncertainty") or [])
                note = f" (uncertain: {doubt})" if doubt else ""
                lines.append(f"- {self.link(o['kind'], o['id'])}{note} {srcs}".rstrip())
        lines += ["", f"## Drugs that could cause it (derived, {len(e['drugs'])})", ""]
        for d in sorted(e["drugs"], key=lambda d: str(d["drug"].get("name") or d["drug"]["id"]).lower()):
            via = ", ".join(f"{self.link('target', b['target'])} {b['action']}"
                            + (f" via {b['via_metabolite']}" if b.get("via_metabolite") else "")
                            for b, _ in d["via"])
            lines.append(f"- {self.link('drug', d['drug']['id'])}: {via}")
        lines += self.sources_section()
        return "\n".join(lines) + "\n"

    def page(self, kind: str, ident: str, rec: dict[str, Any]) -> str:
        self.cited: dict[str, dict[str, Any]] = {}
        if kind == "effect":
            return self.effect_page(ident)
        title = rec.get("name") or rec.get("label") or ident
        lines = [f"# {title}", "", f"Kind: {kind}. Id: `{ident}`."]
        if kind in TAB_KIND:
            lines.append(f"Open in the viewer: {llms_txt.SITE_URL}/#tabs={TAB_KIND[kind]}:{ident}")
        if rec.get("mirror"):
            lines.append("Paired: stated once for the right hemisphere, the left twin is implied.")
        lines.append("Each claim lists its sources as [grade quote_id]; the verbatim quotes are under "
                     "Sources at the end (also in /data/quotes.jsonl by id). A source without a quote "
                     f"id (a database row) is spelled out inline. Index: [all pages]({API}/).")
        facts = [(k, v) for k, v in rec.items() if k not in SKIP and self.is_scalar(v)]
        if facts:
            lines += ["", "## Facts", ""]
            lines += [f"- {k}: {self.scalar(k, v, kind)}" for k, v in facts]
        for k, v in rec.items():
            if k in SKIP or self.is_scalar(v):
                continue
            lines += ["", f"## {k.replace('_', ' ')}", ""] + self.value(k, v, 0, kind)
        for a in self.addons.get((kind, ident), []):
            lines += ["", f"## Note ({a.get('tone', 'info')})", ""]
            lines += self.value("note", {k: v for k, v in a.items()
                                         if k not in ("id", "owner_kind", "owner")}, 0)
        lines += self.sources_section()
        return "\n".join(lines) + "\n"

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
            page_path(out / kind, ident).write_text(r.page(kind, ident, rec), encoding="utf-8")
            n += 1
        (out / kind / "index.md").write_text(r.index(version, [kind]), encoding="utf-8")
    (out / "index.md").write_text(r.index(version), encoding="utf-8")
    # Served (status 404) for any /api address with no page, so a mistyped or guessed
    # id still leads somewhere: the full list, ids shown, is the way out.
    (out / "not_found.md").write_text(r.index(version, lead=NOT_FOUND), encoding="utf-8")
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
