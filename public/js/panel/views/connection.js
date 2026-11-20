// The Connection view: one projection (pathway) with its endpoints, transmitter, sign
// and sources.

const { t } = window.__I18N__;

export function show(P, proj) {
  const {
    body, clearBody, colourMeaningOf, finishBody, data, el, endpointEl, nodePill, sourceBackedPill,
  } = P;
  clearBody("connection");
  body.appendChild(el("h2", "info-title", proj.label || t("info.connection")));
  // Type line: the connection's analogue of a structure's group line ("Lobe"
  // etc.), stating plainly what this node is (a projection / neuron pathway).
  body.appendChild(el("div", "info-group", t("info.projectionType")));

  // The pathway's one source grade (strongest over its citations), shown on
  // each data row below so every claim (route, transmitter, description) carries
  // its own badge, rather than a single block at the bottom that leaves it
  // unclear which node it backs. The tooltip lists the citation(s).
  const provPill = () => nodePill(proj);

  // Route line: from -> to (or <-> for a bidirectional/commissural link), each
  // endpoint clickable to jump to (and isolate) that structure.
  const route = el("div", "info-route");
  route.appendChild(endpointEl(proj.from));
  route.appendChild(el("span", "conn-dir", proj.bidirectional ? "↔" : "→"));
  route.appendChild(endpointEl(proj.to));
  route.appendChild(provPill());
  body.appendChild(route);

  // Kind swatch + kind/transmitter text + its source badge. The kind line used to
  // state two claims at once ("Excitatory · Glutamate") under the pathway's single
  // grade, so a sentence that only said region A projects to region B also published
  // a green check on the transmitter AND on the sign that colours the arrow in
  // Potential mode. Each is its own graded node now (see the generator's
  // quotes/attestation.py), so each gets its own pill, and a part no cited quote
  // names reads grey rather than borrowing the route's check.
  const claims = proj.claims || {};
  // The shared node pill, so a sub-claim carrying uncertainty bullets reads orange.
  const claimPill = (claim) => sourceBackedPill((claim && claim.grade) || "llm", claim);
  const meta = el("div", "info-meta");
  const swatch = el("span", "swatch line");
  swatch.style.background = proj.color || "#fff";
  meta.appendChild(swatch);
  // A signed pathway splits into two rows (the sign here, the transmitter below);
  // a modulatory one makes no sign claim at all, so its single line ("Histaminergic
  // · Histamine") is entirely the transmitter claim. Localized via the shared
  // colourMeaningOf so this type line and the arrow's colour-meaning tooltip cannot
  // drift.
  const kindLabel = (data.meta.kindLabels && data.meta.kindLabels[proj.kind])
    || proj.kind || "";
  meta.appendChild(el("span", null, claims.sign ? kindLabel : colourMeaningOf(proj)));
  meta.appendChild(claimPill(claims.sign || claims.transmitter));
  body.appendChild(meta);
  if (claims.sign && proj.neurotransmitter) {
    const nt = el("div", "info-meta");
    // An invisible swatch keeps this row aligned under the kind line above it
    // (same indent, no second colour chip: the arrow has only one colour).
    const spacer = el("span", "swatch line");
    spacer.style.visibility = "hidden";
    nt.appendChild(spacer);
    nt.appendChild(el("span", null, proj.neurotransmitter));
    nt.appendChild(claimPill(claims.transmitter));
    body.appendChild(nt);
  }

  // Short description + its source badge (inline at the end, like the receptor
  // baked-description pill).
  if (proj.description) {
    const p = el("p", "info-desc", proj.description);
    p.appendChild(document.createTextNode(" "));
    p.appendChild(provPill());
    body.appendChild(p);
  }
  finishBody(); // no headed section to fold, but the footer still closes it
}
