// The drug map's plot title: one sentence saying what is on screen, derived from the
// view (never authored per preset), e.g.
//   {cats: {antipsychotic_atypical, antipsychotic_conventional}, only: [d1..d5, dat, h1],
//    color: "nbn"}
//   -> "Antipsychotics by dopaminergic and H1 binding, colored by nomenclature"
// A class set that covers whole families is named by the family ("Antipsychotics"), a
// target set that covers whole transmitter systems by the system ("dopaminergic"), so
// the sentence stays short; past MAX_ITEMS it falls back to a count, still naming the
// systems the targets belong to when those are few ("6 dopaminergic targets"). Picked
// keys from several feature sources (targets, `tone:<kind>`, `effect:<id>`) each get
// their own clause: "All drugs by D2 and H1 binding and sedation". DOM-free (node
// tests): the caller passes `t` and the groupings the controls already built.

import { EFFECT_PREFIX, TONE_PREFIX } from "./model.js";

/** Past this many named classes / systems / targets, the title gives a count. */
export const MAX_ITEMS = 5;

// "Dopaminergic" -> "dopaminergic" mid-sentence, but "GABAergic" / "D2" stay as they are.
const lowerFirst = (s) => (s.length > 1 && s[1] === s[1].toLowerCase() && s[1] !== s[1].toUpperCase()
  ? s[0].toLowerCase() + s.slice(1) : s);

// A receptor / target key, as opposed to a tone or a body-effect key.
const isTarget = (k) => !k.startsWith(TONE_PREFIX) && !k.startsWith(EFFECT_PREFIX);

/**
 * A target's name as a title says it: the shorter of the name and its trailing
 * parenthesised alias, so "Monoamine oxidase A (MAO-A)" -> "MAO-A" but "μ (MOR)" -> "μ".
 * @param {string} name
 * @returns {string}
 */
export function shortName(name) {
  const m = /^(.*\S)\s*\(([^()]+)\)$/.exec(name);
  return m && m[2].length < m[1].length ? m[2] : m ? m[1] : name;
}

/**
 * Name a picked set by its whole groups first, then the leftover members one by one.
 * @param {string[]} picked
 * @param {[string, string[]][]} groups  [label, member keys]
 * @param {(key: string) => string} nameOf
 * @returns {string[]}
 */
export function nameSet(picked, groups, nameOf) {
  const left = new Set(picked);
  const out = [];
  for (const [label, keys] of groups) {
    if (keys.length && keys.every((k) => left.has(k))) {
      out.push(label);
      for (const k of keys) left.delete(k);
    }
  }
  for (const k of picked) if (left.has(k)) out.push(nameOf(k));
  return out;
}

/**
 * @param {object} view  the drug map view (js/drug-map/model.js DEFAULT_VIEW shape)
 * @param {{t: Function, families: [string, string[]][], systems: [string, string[]][],
 *   catName: (key: string) => string, nameOf: (key: string) => string}} ctx
 *   families: class families [label, class keys]; systems: the axes picker's groups for
 *   `view.sources` [label, feature keys]; catName: a class's PLURAL label ("Antihistamines");
 *   nameOf: a feature's full name (a target's is shortened here, shortName)
 * @returns {string}
 */
export function plotTitle(view, { t, families, systems, catName, nameOf: fullName }) {
  // An effect label keeps its parenthesis ("Extrapyramidal symptoms (parkinsonism)").
  const nameOf = (k) => (isTarget(k) ? shortName(fullName(k)) : fullName(k));
  const list = (items) => (items.length < 2 ? items.join("")
    : `${items.slice(0, -1).join(", ")}${t("drugmap.ttl.and")}${items[items.length - 1]}`);
  // One feature as an axis: a target by its affinity, a tone or an effect by its name.
  const axisName = (k) => (isTarget(k) ? t("drugmap.ttl.affinity", { name: nameOf(k) })
    : t("drugmap.ttl.named", { name: lowerFirst(nameOf(k)) }));

  let subject = t("drugmap.ttl.all");
  if (view.cats) {
    const names = nameSet([...view.cats], families, catName);
    subject = names.length > MAX_ITEMS ? t("drugmap.ttl.manyClasses", { n: view.cats.size })
      : list(names.map((s, i) => (i ? lowerFirst(s) : s)));
  }

  const only = view.only;
  let title;
  if (only && !only.length) title = t("drugmap.ttl.none", { subject });
  else if (only && only.length === 1) title = t("drugmap.ttl.byOne", { subject, x: axisName(only[0]) });
  else if (only && only.length === 2) {
    title = t("drugmap.ttl.byTwo", { subject, x: axisName(only[0]), y: axisName(only[1]) });
  } else if (only) {
    // Only the keys the picker offers (a link may name a target no mapped drug binds,
    // which has no display name and moves no point), like the Axes summary.
    const known = only.filter((k) => systems.some(([, keys]) => keys.includes(k)));
    const parts = [];
    const targets = known.filter(isTarget);
    if (targets.length) {
      const groups = systems.filter(([, keys]) => keys.some(isTarget));
      const names = nameSet(targets, groups, nameOf).map(lowerFirst);
      // Too many to list: count them, naming their systems when those are few.
      const owners = groups.filter(([, keys]) => targets.some((k) => keys.includes(k))).map(([label]) => lowerFirst(label));
      parts.push(names.length <= MAX_ITEMS ? t("drugmap.ttl.binding", { list: list(names) })
        : owners.length <= 3 ? t("drugmap.ttl.manySystemTargets", { n: targets.length, list: list(owners) })
          : t("drugmap.ttl.manyTargets", { n: targets.length }));
    }
    // Tones and effects: one clause each, a whole group named by its label.
    for (const [prefix, one, many] of [[TONE_PREFIX, "drugmap.ttl.tones", "drugmap.ttl.manyTones"],
      [EFFECT_PREFIX, "drugmap.ttl.effects", "drugmap.ttl.manyEffects"]]) {
      const keys = known.filter((k) => k.startsWith(prefix));
      if (!keys.length) continue;
      const groups = systems.filter(([, ks]) => ks.some((k) => k.startsWith(prefix)));
      const names = nameSet(keys, groups, nameOf).map(lowerFirst);
      parts.push(names.length <= MAX_ITEMS ? t(one, { list: list(names) }) : t(many, { n: keys.length }));
    }
    title = t("drugmap.ttl.by", { subject, list: list(parts) });
  } else {
    title = t("drugmap.ttl.by", { subject, list: list(view.sources.map((s) => t(`drugmap.ttl.src.${s}`))) });
  }

  if (view.color !== "category") {
    title = t("drugmap.ttl.color", { title, mode: lowerFirst(t(`drugmap.color.${view.color}`)) });
  }
  if (view.years) {
    title = t("drugmap.ttl.years", { title, from: view.years[0] || "…", to: view.years[1] < 9999 ? view.years[1] : "…" });
  }
  return title;
}
