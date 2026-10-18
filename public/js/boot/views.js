// The two view tabs (a view, not a node, so their tab keys carry no id): the Data
// browser and the Simulation (beta). Also builds the shared node navigation (`nodeNav`)
// their rows and the Sources popup's example nodes jump through, and fills the Sources
// popup's coverage tally.

import { createNodeBrowser } from "../node-browser.js";
import { createSimulation } from "../simulation.js";
import { KIND_LABELS } from "../kinds.js";
import { foldText } from "../search/query.js";
import { formatHalfLife } from "../panel/format.js";
import { buildAboutSourcing, GRADE_LABELS } from "../about/sourcing.js";

const { t } = window.__I18N__;

/**
 * @param {{arrows: object[], data: object, focusCircuit: Function, focusDrug: Function,
 *          focusProjectionGroup: Function, focusTarget: Function, info: object,
 *          meshById: Map, openDataFiles: () => void, openDetailTab: Function,
 *          selectConnection: Function, selectStructure: Function,
 *          setNo3d: Function, sourcingModal: object, urlState: object}} deps
 *   `openDataFiles` / `setNo3d` may be late-bound (their owners are wired after this)
 * @returns {{NODES_TAB_KEY: string, showNodeBrowser: () => void,
 *            showSimulation: () => void, simulation: object|null}}
 */
export function wireViews({
  arrows, data, focusCircuit, focusDrug, focusProjectionGroup, focusTarget, info, meshById,
  openDataFiles, openDetailTab, selectConnection, selectStructure, setNo3d, sourcingModal,
  urlState,
}) {
  // Fill the About panel's "Sources & provenance" block (grade key + the programmatic
  // coverage tally) from the dataset's meta. `nav` lets an expanded kind's example node
  // jump to the real entity: each callback closes the popup first so the focus is
  // visible behind it, then focuses the drug / target / structure / circuit / group.
  // One nav for every node row: the Data browser's rows, and (each wrapped to close
  // the popup first, so the focus is visible behind it) the Sources popup's examples.
  // A projection row isolates the arrow that carries it.
  const nodeNav = {
    drug: (d, opts) => focusDrug(d, { frame: true, ...opts }),
    target: (tg) => focusTarget(tg, { frame: true }),
    structure: (id) => {
      const mesh = meshById.get(id);
      if (mesh) selectStructure(mesh, { frame: true });
    },
    connection: (proj) => {
      const arrow = arrows.find((a) => a.projection === proj);
      if (arrow) selectConnection(arrow, { frame: true, isolate: true });
    },
    circuit: (c) => focusCircuit(c, { frame: true }),
    group: (g) => focusProjectionGroup(g, { frame: true }),
  };
  const sourcingNav = {
    ...Object.fromEntries(Object.entries(nodeNav).map(([k, go]) => [k, (...args) => {
      sourcingModal.close();
      go(...args);
    }])),
    // Not an example node but the whole list: the popup's "Open the Data browser"
    // line. Reads `showNodeBrowser` at call time, since it is only assigned below.
    browser: () => { sourcingModal.close(); showNodeBrowser(); },
  };
  buildAboutSourcing(data.meta, { data, nav: sourcingNav });

  // The Data browser: the same nodes the tally counts, listed one by one. It opens
  // as a **detail tab** rather than expanding in the accordion, because thousands of
  // rows want the whole pane; its DOM is a detached container the browser owns, so
  // the filter text, the selects and the scroll position all survive a tab switch
  // (the panel only hosts it, see info.showNodeBrowser).
  // Its nav is `nodeNav` above (a browser row is already in the open panel, so no
  // popup to close).
  // Its tab key. Unlike every other detail tab this one identifies a *view*, not a
  // node, so it carries no id; the deep-link layer maps it to `#browser=1`.
  const NODES_TAB_KEY = "browser:1";
  // Open (or re-activate) the Data browser tab. Assigned just below; a no-op if the
  // section's markup is missing, so the deep link + the row can call it blind.
  let showNodeBrowser = () => {};
  const nodesToggle = document.getElementById("nodes-toggle");
  if (nodesToggle) {
    const nodesBody = document.createElement("div");
    nodesBody.id = "nodes-body";
    const nodeBrowser = createNodeBrowser({
      body: nodesBody,
      data,
      deps: {
        t,
        formatHalfLife,
        nav: nodeNav,
      },
      ui: {
        pill: info.provenancePill,
        fold: foldText,
        kindLabel: (k) => t(KIND_LABELS[k] || k),
        gradeLabel: (g) => t(GRADE_LABELS[g] || g),
        // The downloadable-file list already lives in the About popup; point at it
        // rather than shipping a second copy of the same links.
        openDataFiles,
      },
    });
    // Lazy: collecting every node walks the whole dataset, so building waits for the
    // first open rather than running at boot; reopening is then just a re-host.
    showNodeBrowser = () => {
      nodeBrowser.open();
      info.showNodeBrowser(nodesBody);
      openDetailTab(NODES_TAB_KEY, t("panel.nodes"), showNodeBrowser);
    };
    // The rows are a wide table and read nothing off the scene, so the browser opens
    // maximized (this visit only, see setNo3d's `persist`).
    nodesToggle.addEventListener("click", () => {
      setNo3d(true, { persist: false });
      showNodeBrowser();
    });
  }

  // Simulation (beta): the same detail-tab shape as the Data browser above (a view,
  // not a node, so its key carries no id and the deep-link layer maps it to
  // `#simulation=1`), and the same detached container, since the picked drugs and the
  // solver's wish list are state a tab switch must not throw away. The drug list
  // itself rides the URL under `sim`, registered further down with the other views.
  const SIM_TAB_KEY = "simulation:1";
  let showSimulation = () => {};
  let simulation = null;
  const simToggle = document.getElementById("simulation-toggle");
  if (simToggle) {
    const simBody = document.createElement("div");
    simBody.id = "simulation-body";
    simulation = createSimulation({
      body: simBody,
      data,
      deps: { t, nav: { drug: (d) => focusDrug(d, { frame: true }) } },
      ui: { fold: foldText },
    });
    simulation.setOnChange(() => urlState.sync(200));
    showSimulation = () => {
      simulation.open();
      info.showSimulation(simBody);
      openDetailTab(SIM_TAB_KEY, t("panel.simulation"), showSimulation);
    };
    // Two plots and a solver want the whole pane, and none of it lights the scene
    // (it is pharmacology, not anatomy), so the tab opens maximized for this visit.
    simToggle.addEventListener("click", () => {
      setNo3d(true, { persist: false });
      showSimulation();
    });
  }

  return { NODES_TAB_KEY, showNodeBrowser, showSimulation, simulation };
}
