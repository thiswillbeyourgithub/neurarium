// The Effect view (BETA): the receptors / targets carrying one clinical effect, by
// mode, then the drugs that could cause it through their bindings.

import { groupByMode } from "../../receptor-effects.js";

const { t } = window.__I18N__;

/**
 * Populate the panel for one clinical *effect* (the Effects section, BETA): the
 * receptors / targets whose stored receptor_effect nodes carry it, grouped by
 * mode, each with that node's own pill; then the drugs whose bindings could reach
 * it, the drug panel's own derived join seen from the effect's end (`data.effects`,
 * the build-time index, tools/data_generators/effect_index.py). Nothing here is stored per drug, said in the caption.
 */
export function showEffect(P, effect) {
  const {
    betaSection, body, clearBody, data, derivedRow, el, foldBody, linkName, nodePill,
    onDrugPick, onTargetPick,
  } = P;
  clearBody("effect");
  body.appendChild(el("h2", "info-title", effect.label));
  const kind = el("div", "info-group", t("effect.heading"));
  kind.appendChild(el("span", "beta-tag", t("sim.beta")));
  body.appendChild(kind);
  body.appendChild(el("p", "legend-caption", t("effect.hint")));

  const owners = betaSection("effectOwners", "effect.owners", "effects.hint",
    { vars: { n: effect.owners.length }, grouped: true });
  for (const { rows } of groupByMode(effect.owners, (o) => o.node.mode, data.meta.effectModes)) {
    const group = rows.sort((a, b) => a.target.name.localeCompare(b.target.name));
    const ul = owners.group(group[0].node.modeLabel, "drug-cat");
    for (const { target, node } of group) {
      const li = el("li");
      li.appendChild(linkName(target.name,
        target.focusable ? () => onTargetPick(target) : null));
      li.appendChild(nodePill(node));
      ul.appendChild(li);
    }
  }
  owners.close();

  const drugs = betaSection("effectDrugs", "effect.drugs", "effect.drugsHint",
    { vars: { n: effect.drugs.length } });
  if (!effect.drugs.length) drugs.ul.appendChild(el("li", "info-desc", t("effect.noDrugs")));
  const sorted = [...effect.drugs]
    .sort((a, b) => a.drug.displayName.localeCompare(b.drug.displayName));
  for (const { drug, via } of sorted) {
    drugs.ul.appendChild(derivedRow(linkName(drug.displayName, () => onDrugPick(drug)), via));
  }
  drugs.close();
  foldBody();
}
