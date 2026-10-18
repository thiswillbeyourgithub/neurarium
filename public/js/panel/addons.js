// Addon nodes and derived boxes: the annotation a node carries to its own insertion
// point (appendAddons, see CLAUDE.md "Addon nodes"), plus the derived fallback boxes
// (auto-modulation, active metabolites) worded conditionally with no pill.

import { flashRow, btn } from "./dom.js";

const { t } = window.__I18N__;

export function makeAddons(P) {
  const {
    data, el, nodePill,
  } = P;

  // --- Addon nodes: the panel-slot annotation kind ------------------------------
  // Every other node kind has an implied home (a binding belongs in "Direct molecular targets", an
  // enzyme row in "Metabolism"), so its collection decides where it draws. An addon
  // is the kind for a claim with no such home: it carries its OWN insertion point
  // (see tools/data_generators/addons.py), and these two pieces are the whole hook
  // system. A panel offers slots; the data decides what, if anything, fills them.
  //
  // How an addon draws, keyed by its `display`. A second form (an inline icon with a
  // tooltip, say) is one entry here plus one string in the generator's ADDON_DISPLAYS,
  // never a change at any call site.
  // The boxed callout every display form shares: the tone glyph + title on one line,
  // carrying the node's own source pill, then the claim. Only the wrapper differs
  // (a plain box, or a <details> folded to that head line).
  const addonBox = (addon, wrapTag, headTag, extraCls) => {
    const box = el(wrapTag, `addon addon-${addon.tone}${extraCls}`);
    const head = el(headTag, "addon-head");
    if (addon.glyph) head.appendChild(el("span", "addon-glyph", addon.glyph));
    if (addon.title) head.appendChild(el("strong", "addon-title", addon.title));
    head.appendChild(nodePill(addon));
    box.appendChild(head);
    box.appendChild(el("p", "addon-text", addon.text));
    return box;
  };

  const ADDON_RENDERERS = {
    // A boxed callout: the tone glyph + title on one line, carrying the node's own
    // source pill (an addon is a graded claim like a binding, not panel chrome), then
    // the claim itself.
    admonition: (addon) => addonBox(addon, "div", "div", ""),
    // The same box folded to its head line (glyph + title + pill) until clicked: a
    // background caveat that should not push the data it qualifies down the panel.
    collapsible: (addon) =>
      addonBox(addon, "details", "summary", " addon-collapsible disclosure"),
  };

  /**
   * Splice in whatever addon nodes are anchored at one panel slot. Every registered
   * slot in meta.addon_slots has exactly one of these calls; a slot with nothing
   * authored for it appends nothing, so the hook costs one Map lookup on the panels
   * of the other few thousand nodes.
   *
   * @param {HTMLElement} host  where the addons are appended
   * @param {string} ownerKind  the anchored node's kind ("drug", "receptor", ...)
   * @param {string} ownerId    that node's id (a structure anchors its BASE)
   * @param {string} slot       a meta.addon_slots key
   * @returns {number} how many addons were drawn, so a caller can fall back to a
   *   derived note only when the slot holds no authored (sourced) one.
   */
  const appendAddons = (host, ownerKind, ownerId, slot) => {
    if (!ownerId || !data.addonsBySlot) return 0;
    // An unregistered slot is a wiring bug, not a missing addon: the generator
    // validated every authored addon against this same list, so a typo here asks a
    // question no node can ever be authored to answer.
    const slots = data.meta.addonSlots;
    if (slots && !(slot in slots)) {
      console.warn(`addon slot "${slot}" is not in meta.addon_slots`);
      return 0;
    }
    let drawn = 0;
    for (const addon of data.addonsBySlot.get(`${ownerKind}:${ownerId}:${slot}`) || []) {
      const render = ADDON_RENDERERS[addon.display];
      if (render) { host.appendChild(render(addon)); drawn += 1; }
      else console.warn(`addon "${addon.id}": unknown display "${addon.display}"`);
    }
    return drawn;
  };

  /**
   * The derived twin of a `drug.metabolism` addon: a drug that is both a substrate
   * and a modulator of one isoform changes its own clearance, so its kinetics are
   * non-linear. Read off `drug.autoModulation` (js/data.js), which is an INFERENCE
   * over the enzyme rows rendered just below, so this box words itself
   * conditionally, carries no source pill, and says where it comes from: the rows
   * it reads each carry their own grade, and the coincidence is our reading, not a
   * sentence any corpus prints. An authored addon in the same slot outranks it (it
   * states a mechanism a source really attests), so the caller only falls back here
   * when the slot is empty.
   *
   * @param {object} drug
   * @returns {HTMLElement|null} the box, or null when the drug modulates no isoform
   *   that also clears it
   */
  const derivedAutoModulation = (drug) => {
    const rows = drug.autoModulation || [];
    if (!rows.length) return null;
    const labels = (role) => rows.filter((r) => r.role === role).map((r) => r.label);
    const box = derivedBox("info", t("drug.autoPkTitle"));
    // One sentence per direction: a drug can inhibit one of its own isoforms and
    // induce another (modafinil), and the two read opposite ways over time.
    const parts = [];
    const inhibits = labels("inhibitor");
    const induces = labels("inducer");
    if (inhibits.length) parts.push(t("drug.autoPkInhibits", { enzymes: inhibits.join(", ") }));
    if (induces.length) parts.push(t("drug.autoPkInduces", { enzymes: induces.join(", ") }));
    box.appendChild(el("p", "addon-text", parts.join(" ")));
    box.appendChild(el("p", "addon-derived-note", t("drug.autoPkDerived")));
    return box;
  };

  // The skeleton of a derived (viewer-computed, unpilled) addon-styled box: its tone
  // glyph + title; the caller appends the body. Shared so every derived box reads alike.
  const derivedBox = (tone, title) => {
    const box = el("div", `addon addon-${tone} addon-derived`);
    const head = el("div", "addon-head");
    const glyph = (data.meta.addonTones || {})[tone];
    if (glyph) head.appendChild(el("span", "addon-glyph", glyph));
    head.appendChild(el("strong", "addon-title", title));
    box.appendChild(head);
    return box;
  };

  // A signed tone value as the tone sections print it: "+0.97" / "−0.42", localized.
  const fmtTone = (v) => `${v < 0 ? "−" : "+"}${Math.abs(v).toLocaleString(
    window.__I18N__.lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  // A drug's net indicative tone on one system, the raw uncapped sum (0 when it sets
  // none): what the drug panel's tone section shows and the group panel ranks by. The
  // overlay's capped `weight` only scales the animation.
  const netTone = (drug, kind) => ((drug.flowSystems || {})[kind] || { sum: 0 }).sum;

  // Caution box leading "Direct molecular targets" for a drug with active
  // metabolites: the rows list only the parent's own bindings, while the metabolites
  // act too (their bindings live under Active metabolites or on their own drug panel).
  // Derived from the drug's sourced metabolite nodes, so no pill of its own; the
  // button jumps to that section, looked up at click time since it renders later.
  const derivedActiveMetabolites = (drug, body) => {
    const names = (drug.metabolites || []).map((m) => m.name);
    if (!names.length || drug.prodrug) return null;
    const box = derivedBox("caution", t("drug.metabolites"));
    const p = el("p", "addon-text", `${t(names.length > 1 ? "drug.activeMetabWarnMany" : "drug.activeMetabWarnOne",
      { names: names.join(", ") })} `);
    const go = btn("addon-jump", t("drug.activeMetabSee"));
    go.addEventListener("click", () =>
      flashRow(body.querySelector('[data-tour-sec="metabolites"]')));
    p.appendChild(go);
    box.appendChild(p);
    return box;
  };

  return {
    ADDON_RENDERERS, addonBox, appendAddons, derivedActiveMetabolites,
    derivedAutoModulation, derivedBox, fmtTone, netTone,
  };
}
