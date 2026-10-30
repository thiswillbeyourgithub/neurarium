// The Projection group view: the pathways sharing one transmitter / sign, with the
// regions they link.

import { emptySection } from "../dom.js";

const { t } = window.__I18N__;

/**
 * Populate the panel for a *projection group* (clicking a Projections legend
 * row, in either colour mode): its name, a heading saying whether it groups by
 * transmitter or by sign (carrying the group's source grade), a sourced
 * description (baked + live-refreshed from Wikipedia) with the reference link,
 * then its member pathways (the projections whose kind / sign matches the group,
 * derived not stored).
 */
export function showProjectionGroup(P, group) {
  const {
    appendPathwayList, appendReference, appendSourcedHeading, body, clearBody, data,
    el, fmtTone, foldBody, netTone, nodePill, onDrugPick, strongestBindingForKind,
  } = P;
  clearBody("group");
  body.appendChild(el("h2", "info-title", group.name));
  // The group's source grade rides its identity line (always shown, NOSOURCE when
  // llm-only), not a "Sources" block at the bottom. The description keeps its own
  // grade below.
  appendSourcedHeading(
    group.mode === "sign" ? t("group.signHeading") : t("group.kindHeading"),
    group.provenance, group.sources, true,
    group.mode === "sign" ? t("group.signHeadingSub") : null);

  // Description (LLM-authored) + the Wikipedia reference below it, then the live
  // lead refresh (upgrades the paragraph to the current WP lead when reachable),
  // via the same shared appendReference every panel uses.
  appendReference({
    url: group.wikipedia, description: group.description,
    descriptionProvenance: group.classification_provenance,
  });

  // Member pathways: the projections this group stands for. In "kind" mode that
  // is every projection of the kind; in "sign" mode every projection folding to
  // the sign. Same derivation the legend uses to colour the arrows, so the panel
  // list always matches what is lit on screen.
  const members = data.projections.filter((p) =>
    group.mode === "sign" ? p.sign === group.key : p.kind === group.key);
  appendPathwayList(t("group.pathways"), members, "group");

  // Drugs acting on this system: the mirror of the drug panel's "Projections
  // affected". Every focusable drug whose flow overlay lights this group (its
  // flowKinds includes this kind, i.e. it binds a receptor in the transmitter
  // system these pathways carry), so you can go from a pathway system to the
  // drugs that engage it. Non-directional, like the drug side. Only meaningful in
  // "kind" mode (a sign group has no transmitter system to map).
  if (group.mode === "kind") {
    const acting = (data.drugs || [])
      .filter((d) => d.focusable && (d.flowKinds || []).includes(group.key))
      // Strongest raise first, strongest lowering last (see netTone).
      .sort((a, b) => netTone(b, group.key) - netTone(a, group.key)
        || a.name.localeCompare(b.name));
    if (acting.length) {
      const wrap = el("div", "info-bindings info-interactors");
      wrap.dataset.icon = "drugs";
      wrap.appendChild(el(
        "h3", null, `${t("group.actingDrugs")} (${acting.length})`));
      wrap.appendChild(el("p", "legend-caption", t("group.actingDrugsHint")));
      const ul = el("ul");
      for (const d of acting) {
        const li = el("li", "clickable");
        li.title = d.displayName;
        li.appendChild(el("span", "bind-target", d.displayName));
        const cat = d.categoryLabels && d.categoryLabels[0];
        if (cat) li.appendChild(el("span", "legend-tag", cat));
        // Symmetric sourcing with the drug panel's "Pharmacodynamics: net neurotransmission" row:
        // the drug<->system link is one node, so both ends carry the same source,
        // the strongest-affinity binding feeding this system.
        const rep = strongestBindingForKind(d.bindings, group.key);
        if (rep) li.appendChild(nodePill(rep));
        const tone = el("span", "tone-value", fmtTone(netTone(d, group.key)));
        tone.title = t("group.toneTip");
        li.appendChild(tone);
        li.addEventListener("click", () => onDrugPick(d));
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
      body.appendChild(wrap);
    } else {
      body.appendChild(emptySection(el("h3", null, t("group.actingDrugs")), "group",
        { icon: "drugs" }));
    }
  }
  // Headed sections start folded, like the drug panel (see foldSections).
  foldBody();
}
