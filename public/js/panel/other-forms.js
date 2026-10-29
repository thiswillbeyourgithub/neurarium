// A drug's other stereo forms (generator DRUG_STEREO_FORMS: a racemate and its single
// enantiomer). A source often fills a section on one form only (the French label
// lists the checks for D,L-methylphenidate, none for the D form), so a section empty
// here links the form that fills it. Navigation only: one form's data is never shown
// as the other's (an enantiomer is not its racemate).

import { sectionSelector } from "./dom.js";

const { t } = window.__I18N__;

export function makeOtherForms(P) {
  const { drugById, drugNameLink, el } = P;

  // The emptySection options `opts`, plus an `extra` line linking each other form of
  // `drug` for which `has(form)` holds. The link opens that form on the same section
  // (found by the same opts, dom.js sectionSelector), so the jump lands on the answer.
  const withOtherForms = (drug, has, opts = {}) => {
    const others = (drug.stereo_forms || []).map((id) => drugById.get(id))
      .filter((d) => d && d.focusable && has(d));
    if (!others.length) return opts;
    const highlightSection = sectionSelector(opts);
    const p = el("p", "other-forms", `${t("drug.otherFormsHas")} `);
    others.forEach((d, i) => {
      if (i) p.appendChild(document.createTextNode(", "));
      p.appendChild(drugNameLink(d, d.label || d.name, { highlightSection }));
    });
    return { ...opts, extra: p };
  };

  return { withOtherForms };
}
