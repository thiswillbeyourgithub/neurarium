// The anatomy legend (Structures / Circuits / Projections rows), its static colour
// key, and the arrow colour-mode switch that rebuilds it. Registers the `colors`
// URL key.

import { buildLegend } from "../legend/anatomy.js";
import { buildLegendKey } from "../legend/key.js";

/**
 * @param {{arrows: object[], circuitAnim: object, data: object, focusCircuit: Function,
 *          focusProjectionGroup: Function, info: object, meshById: Map, projVis: object,
 *          selectStructure: Function, selection: object, urlState: object}} deps
 */
export function wireLegends({
  arrows, circuitAnim, data, focusCircuit, focusProjectionGroup, info, meshById, projVis,
  selectStructure, selection, urlState,
}) {
  // Arrow colour mode + legend. The legend's focus-greying callback is registered
  // once here; rebuildLegend just swaps which function it delegates to, so the
  // colour toggle (which rebuilds the legend so its Projections rows match the new
  // arrow colours) never stacks onIsolate listeners.
  let signColorMode = false; // false = per-transmitter (default), true = excit/inhib
  let reflectLegend = () => {};
  selection.onIsolate((isolated, focusedArrows) => reflectLegend(isolated, focusedArrows));
  const applyArrowColors = () => {
    for (const a of arrows) {
      a.setColor(signColorMode ? a.projection.signColor : a.projection.color);
    }
  };

  const rebuildLegend = () => {
    reflectLegend = buildLegend(
      data, meshById, arrows, selection, projVis, circuitAnim, signColorMode,
      // Opening the picked structure's tab (no reframe: keep the legend pick's
      // current camera, just add the detail tab + halo, like the isolate already
      // does in the viewer).
      (mesh) => selectStructure(mesh),
      // Circuit / projection-group row picks: isolate + open the sourced detail
      // panel + tab, exactly like a drug / target row.
      focusCircuit, focusProjectionGroup,
      // The Projections section hosts an addon slot; the hook lives on the info panel.
      info.appendAddons);
    selection.refresh(); // re-grey the fresh rows for the current isolate state
  };
  rebuildLegend();
  // The static colour key (Legend section) is built once: it shows the scene's
  // encodings (gem-dot signs, drug effect colours, dotted = speculative) from the
  // meta maps and doesn't depend on the arrow colour mode.
  buildLegendKey(data);

  // Arrow colour-mode switch (Neurotransmitter | Potential): a two-state
  // segmented control in the Controls section. Picking an option recolours the
  // arrows and rebuilds the Projections legend rows to match. The switch lives
  // outside #projections-body, so buildLegend's rebuilds never touch it and these
  // listeners persist for the life of the page.
  const colorModeSwitch = document.getElementById("color-mode");
  const modeButtons = colorModeSwitch.querySelectorAll(".mode-btn");
  const setColorMode = (sign) => {
    if (sign === signColorMode) return;
    signColorMode = sign;
    for (const b of modeButtons) {
      const on = (b.dataset.mode === "sign") === sign;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    }
    applyArrowColors();
    rebuildLegend();
  };
  for (const b of modeButtons) {
    b.addEventListener("click", () => { setColorMode(b.dataset.mode === "sign"); urlState.sync(); });
  }
  // `colors=sign`: which key the arrows are coloured by (transmitter is the default).
  urlState.register("colors", {
    read: () => (signColorMode ? "sign" : null),
    write: (v) => setColorMode(v === "sign"),
    reset: () => setColorMode(false),
  });
}
