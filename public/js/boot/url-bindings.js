// Deep-link keys that need the loaded data: the open detail tabs and the active one,
// the simulation picks, the open popup, and the legacy single-focus params. Each
// registers a {read, write} pair with js/url-state.js.

import { LIST_SEP } from "../url-state.js";
import { foldText } from "../search/query.js";
import { setModalToggle } from "../about/modals.js";
import { stripSide } from "../util.js";

export function wireUrlBindings({
  aboutModal, arrows, changelog, data, drugMap, focusCircuit, focusDrug, focusEffect,
  focusEnzyme, focusProjectionGroup, focusTarget, legendModal, meshes,
  selectConnection, selectStructure, shortcutsHelp, showNodeBrowser, showSimulation,
  simulation, sourcingModal, tabs, urlState,
}) {
  // ---- Deep links: the URL fragment IS the UI state ------------------------------
  // Everything on screen is described by the fragment, through the js/url-state.js
  // registry: which detail tabs are open and in what order, which one is active, the
  // popup showing, the scene sliders + toggles, the panel layout, the open browse
  // section, the search / filter text, and the camera. Each control registers its own
  // {read, write} pair as it is wired (see the urlState.register calls in wireControls
  // / wireToolbar / below); this block adds the ones that need the loaded data, then
  // applies the incoming URL and starts mirroring later changes back into it.
  //
  // Two url-state.js rules keep links short and safe to paste: a view at its default
  // writes nothing, and a key the URL does not carry is left alone, so a link that
  // says nothing about (say) animations never overrides that visitor's own preference.
  const linkFold = (s) => foldText(String(s == null ? "" : s));
  const findByIdOrName = (list, v) => {
    const q = linkFold(v);
    return list.find((o) => linkFold(o.id) === q)
        || list.find((o) => linkFold(o.name) === q);
  };
  // How to reopen one detail tab from the `<id>` half of its `<kind>:<id>` key. A tab
  // key IS the link value, so the URL round-trips the strip verbatim, and each opener
  // re-runs the very select* the UI would, so the 3D focus comes back with the panel.
  // Returns whether it matched. This is also the whole vocabulary the legacy single-
  // focus params resolve through, so each node kind has exactly one resolver.
  const TAB_OPENERS = {
    drug: (v) => { const d = findByIdOrName(data.drugs, v); if (d) focusDrug(d, { frame: true }); return !!d; },
    target: (v) => { const tg = findByIdOrName(data.targets, v); if (tg) focusTarget(tg, { frame: true }); return !!tg; },
    circuit: (v) => { const c = findByIdOrName(data.circuits, v); if (c) focusCircuit(c, { frame: true }); return !!c; },
    group: (v) => { const g = findByIdOrName(data.projectionGroups, v); if (g) focusProjectionGroup(g, { frame: true }); return !!g; },
    enzyme: (v) => { const e = findByIdOrName(data.enzymes || [], v); if (e) focusEnzyme(e); return !!e; },
    effect: (v) => { const e = findByIdOrName(data.effects || [], v); if (e) focusEffect(e); return !!e; },
    structure: (v) => {
      // The exact (sided) id first, so a link round-trips the very mesh the tab named;
      // then the base, which is what a hand-written `#tabs=structure:hippocampus` says.
      const exact = meshes.find((m) => linkFold(m.userData.structure.id) === linkFold(v));
      if (exact) { selectStructure(exact, { frame: true, isolate: true }); return true; }
      const q = linkFold(stripSide(v));
      const group = meshes.filter((m) => {
        const s = m.userData.structure;
        return linkFold(stripSide(s.id)) === q || linkFold(s.base_name) === q || linkFold(s.name) === q;
      });
      if (!group.length) return false;
      const rep = group.find((m) => !/_[LR]$/.test(m.userData.structure.id)) || group[0];
      selectStructure(rep, { frame: true, isolate: true });
      return true;
    },
    connection: (v) => {
      // Same two passes: the exact sided `from->to` a tab key carries, then the
      // side-stripped pair (or the pathway label) a hand-written link uses, which pins
      // both hemispheres the way a search pick does.
      const q = linkFold(v);
      const exact = arrows.find(
        (a) => linkFold(`${a.projection.from}->${a.projection.to}`) === q);
      if (exact) { selectConnection(exact, { frame: true, isolate: true }); return true; }
      const byBase = new Map();
      for (const a of arrows) {
        const p = a.projection;
        const key = `${stripSide(p.from)}->${stripSide(p.to)}`;
        (byBase.get(key) || byBase.set(key, []).get(key)).push(a);
      }
      for (const [key, arr] of byBase) {
        if (linkFold(key) === q || linkFold(arr[0].projection.label) === q) {
          selectConnection(arr[0], { frame: true, isolate: true, siblings: arr.slice(1) });
          return true;
        }
      }
      return false;
    },
    // Not a node: the Data browser, a tab whose content is the whole dataset.
    browser: () => { showNodeBrowser(); return true; },
    // Nor is this one: the Simulation tab, a view over the dataset rather than a
    // node in it. Its own `sim` key carries which drugs are in it.
    simulation: () => { showSimulation(); return true; },
  };
  const openTabKey = (key) => {
    const idx = key.indexOf(":");
    const kind = key.slice(0, idx);
    const open = idx > 0 && Object.hasOwn(TAB_OPENERS, kind) ? TAB_OPENERS[kind] : null;
    return !!open && open(key.slice(idx + 1));
  };

  // `tabs=<kind>:<id>,...`: every open detail tab, in strip order (which the user can
  // drag to change, so the order is state too). Applying opens each in turn, which
  // rebuilds the same strip and leaves the LAST one active; `tab` below corrects that
  // when the active one is not the last.
  urlState.register("tabs", {
    read: () => (tabs.keys().length ? tabs.keys().join(LIST_SEP) : null),
    write: (v) => { for (const key of v.split(LIST_SEP)) if (key) openTabKey(key); },
  });
  // `tab=<index>`: which of them is active. Omitted for the common case (the last one,
  // where opening the list already lands); `s` means the pinned Settings tab is showing
  // with detail tabs still open behind it.
  urlState.register("tab", {
    read: () => {
      const keys = tabs.keys();
      if (!keys.length) return null;
      if (tabs.activeKey() === null) return "s";
      const at = keys.indexOf(tabs.activeKey());
      return at === keys.length - 1 ? null : String(at);
    },
    write: (v) => {
      if (v === "s") { tabs.showSettings(); return; }
      const key = tabs.keys()[Number(v)];
      if (key) tabs.activate(key);
    },
  });
  // `sim=<id>[:<ratio>],...`: the Simulation tab's picked drugs, in list order, each
  // with its relative dose (omitted at the default 1, which is the common case). The
  // rest of the tab (the threshold, the solver's wish list) is a reading aid rather
  // than a view worth reproducing, so it stays out of the link.
  urlState.register("sim", {
    read: () => {
      const picks = simulation ? simulation.getDrugs() : [];
      if (!picks.length) return null;
      return picks.map((p) => (p.ratio === 1 ? p.id : `${p.id}:${p.ratio}`)).join(LIST_SEP);
    },
    write: (v) => {
      if (!simulation) return;
      simulation.setDrugs(v.split(LIST_SEP).filter(Boolean).map((part) => {
        const at = part.indexOf(":");
        return at > 0
          ? { id: part.slice(0, at), ratio: Number(part.slice(at + 1)) }
          : { id: part, ratio: 1 };
      }));
    },
  });

  // The legacy single-focus links (`#focusDrug=vortioxetine`, `#browser=1`) that are
  // already shared around: read-only aliases for one `tabs` entry, applied before it
  // (priority -10) so an explicit `tabs=` wins. They read as null, or the same focus
  // would be written twice; the first sync rewrites such a link to the canonical form.
  const LEGACY_FOCUS = {
    focusDrug: "drug", focusTarget: "target", focusReceptor: "target",
    focusStructure: "structure", focusConnection: "connection",
    focusCircuit: "circuit", focusGroup: "group", browser: "browser",
    simulation: "simulation",
  };
  for (const [param, kind] of Object.entries(LEGACY_FOCUS)) {
    urlState.register(
      param, { read: () => null, write: (v) => TAB_OPENERS[kind](v) }, -10);
  }

  // `popup=<name>`: the .modal-overlay on screen, if any. One key, because only one is
  // ever up (opening one from another, e.g. the Legend's "Sources & provenance" link,
  // closes the first). The image lightbox is deliberately absent: it shows a picture
  // reached from a panel, not a state of the UI.
  const POPUPS = {
    about: aboutModal, legend: legendModal, sources: sourcingModal,
    shortcuts: shortcutsHelp, whatsnew: changelog, drugmap: drugMap,
  };
  urlState.register("popup", {
    read: () => Object.keys(POPUPS).find((name) => POPUPS[name].isOpen) || null,
    write: (v) => {
      for (const [name, ctrl] of Object.entries(POPUPS)) {
        if (name !== v && ctrl.isOpen) ctrl.close();
      }
      if (Object.hasOwn(POPUPS, v)) POPUPS[v].open();
    },
  });
  // Every popup goes through wireModal, so one hook keeps the key current.
  setModalToggle(() => urlState.sync());
}
