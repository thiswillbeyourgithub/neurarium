// Pathway lists: the direction arrow glyph, one row per projection (left/right twins
// collapsed), the headed list on a structure panel, and a connection's endpoint link.

import { btn } from "./dom.js";

const { t } = window.__I18N__;

export function makePathways(P) {
  const {
    baseNameOf, baseResolves, body, data, el, nameOf, nodePill, onConnectionPick,
    onStructurePick, withTip,
  } = P;

  // One route endpoint (a structure id) for the connection panel's route line: its
  // name, made clickable to jump to (and isolate) that structure when the id
  // resolves to a modeled mesh, exactly like a "Found in" region row. A non-
  // resolving id degrades to plain text.
  const endpointEl = (id) => {
    const name = nameOf(id);
    if (id && baseResolves(id)) {
      const b = btn("conn-endpoint", name);
      b.addEventListener("click", () => onStructurePick(id));
      return b;
    }
    return el("span", null, name);
  };

  // One clickable <li> for a pathway that is a member of some grouping (a
  // A bold, colour-filled direction arrow (short shaft + a wide pointy head) for a
  // connection row: far more legible than the old thin colour bar + tiny glyph,
  // and it carries the pathway colour itself. `dir` is "out" (this structure
  // projects to the other endpoint), "in" (receives from it), or "both"
  // (reciprocal / commissural). Drawn as inline SVG so the head is genuinely wide
  // and it stays crisp at any size (a Unicode arrowhead's shape varies by font).
  const SVG_NS = "http://www.w3.org/2000/svg";

  const DIR_TIP = { out: "info.dirOut", in: "info.dirIn", both: "info.dirBoth",
    up: "info.toneUp", down: "info.toneDown" };

  // The localized "what this arrow's colour means" line for a pathway: the kind
  // label (the colour IS the projection kind, meta.projectionColors[kind]) plus the
  // neurotransmitter, matching the connection panel's type line. Empty for a pathway
  // with no kind. Shared so the arrow tooltip and that line can't drift.
  const colourMeaningOf = (proj) => {
    const kindLabel = (data.meta.kindLabels && data.meta.kindLabels[proj.kind])
      || proj.kind || "";
    return [kindLabel, proj.neurotransmitter].filter(Boolean).join(" · ");
  };

  const directionArrow = (color, dir, colourMeaning = "") => {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "conn-arrow");
    svg.setAttribute("viewBox", "0 0 26 16");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d",
      dir === "in"
        ? "M24,6 L12,6 L12,2 L2,8 L12,14 L12,10 L24,10 Z"
        : dir === "both"
        ? "M2,8 L9,2 L9,6 L17,6 L17,2 L24,8 L17,14 L17,10 L9,10 L9,14 Z"
        // Tone rows (up = raises, down = lowers): vertical, centred in the 26-wide box.
        : dir === "up"
        ? "M11,15 L11,8 L7,8 L13,1 L19,8 L15,8 L15,15 Z"
        : dir === "down"
        ? "M11,1 L11,8 L7,8 L13,15 L19,8 L15,8 L15,1 Z"
        : "M2,6 L14,6 L14,2 L24,8 L14,14 L14,10 L2,10 Z"); // "out" (default)
    path.setAttribute("fill", color || "#fff");
    svg.appendChild(path);
    // Tap-to-explain: a tap shows what the arrow means (its direction AND, when
    // known, its colour = the pathway kind), and stops the tap bubbling to the
    // clickable row it sits over, so on a phone tapping the arrow no longer navigates
    // into the pathway/region (per the request); hover shows it on desktop too.
    let tip = t(DIR_TIP[dir] || DIR_TIP.out);
    if (colourMeaning) tip += `\n${t("info.arrowColour", { label: colourMeaning })}`;
    return withTip(svg, tip);
  };

  // One pathway row, shared by every "connections" list (a structure's
  // connections, a circuit's loop, a projection group): the bold direction arrow
  // in the pathway colour, the label text, the pathway's summary source pill, and
  // a click that jumps to the connection via onConnectionPick. `dir` is passed by
  // the caller (showStructure rows are relative to the structure; circuit / group
  // rows show the full route, so they pass "both" for a reciprocal pathway else
  // "out", matching their "from -> to" label text).
  const pathwayRow = (proj, dir, labelText) => {
    const li = el("li");
    li.title = proj.label || "";
    li.appendChild(directionArrow(proj.color, dir, colourMeaningOf(proj)));
    li.appendChild(el("span", "conn-label", labelText));
    // Always show the grade pill; an unsourced pathway shows NOSOURCE, never a blank
    // (a node's provenance is never simply absent from the panel). A pathway the book
    // states only as one blanket sweep wears the orange "uncertain" badge instead of a
    // green check, its reasons leading the tooltip: same rule the binding pill follows.
    li.appendChild(nodePill(proj));
    li.addEventListener("click", () => onConnectionPick(proj));
    return li;
  };

  // Build a <ul> of pathway rows with left/right twins collapsed. `rowOf(proj)`
  // returns `{dir, label}` (the direction glyph + the row text, both using
  // hemisphere-stripped base names): mirrored twins then share direction + label,
  // so keying on `dir|label|pathway` keeps the first and drops its L/R duplicate.
  // Shared by the structure panel and the circuit/group member lists so a midline
  // source (the raphe) that projects to both hemispheres lists each target once.
  // Returns the list element + the surviving row count (for the "(N)" heading).
  const pathwayList = (projs, rowOf) => {
    const seen = new Set();
    const ul = el("ul");
    let count = 0;
    for (const proj of projs) {
      const { dir, label } = rowOf(proj);
      const key = `${dir}|${label}|${proj.label || proj.kind}`;
      if (seen.has(key)) continue;
      seen.add(key);
      ul.appendChild(pathwayRow(proj, dir, label));
      count++;
    }
    return { ul, count };
  };

  // A titled "member pathways" list (the circuit + projection-group panels): one
  // pathwayRow per projection, each showing its full from -> to route (twins
  // collapsed via pathwayList).
  const appendPathwayList = (titleText, projs, tourSec = "") => {
    if (!projs.length) return;
    const { ul, count } = pathwayList(projs, (proj) => {
      const glyph = proj.bidirectional ? "↔" : "→";
      return {
        dir: proj.bidirectional ? "both" : "out",
        label: `${baseNameOf(proj.from)} ${glyph} ${baseNameOf(proj.to)}`,
      };
    });
    const wrap = el("div", "info-connections");
    if (tourSec) wrap.dataset.tourSec = tourSec; // guided-tour section anchor
    wrap.appendChild(el("h3", null, `${titleText} (${count})`));
    wrap.appendChild(ul);
    body.appendChild(wrap);
  };

  return {
    appendPathwayList, colourMeaningOf, DIR_TIP, directionArrow, endpointEl,
    pathwayList, pathwayRow, SVG_NS,
  };
}
