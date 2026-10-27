// Entry point of the drugs map page (drugs-map.html): load the dataset without its
// brain geometry, build the map (js/drug-map/view.js), and mirror its view into the URL
// hash like the viewer does (js/url-state.js), so a link reproduces what is on screen.
// The theme, version stamp and language switch are the same modules the viewer uses;
// nothing here touches three.js.

import { loadBrainData } from "./data.js";
import { createUrlState } from "./url-state.js";
import { createTheme } from "./theme.js";
import { stampVersion } from "./boot/version-stamp.js";
import { wireThemeButton } from "./boot/header-toggles.js";
import { createDrugMap } from "./drug-map/view.js";
import { viewerUrl } from "./drug-map/site.js";

const { t, lang } = window.__I18N__;

async function main() {
  stampVersion();
  wireThemeButton(createTheme());
  const viewerLink = document.getElementById("dmp-viewer");
  if (viewerLink) viewerLink.href = viewerUrl();
  const readme = document.getElementById("dmp-readme");
  if (readme && lang === "fr") readme.href = "drugs-map/README.fr.md";

  let data;
  try {
    data = await loadBrainData("data", null, { shapes: false });
  } catch (err) {
    console.error(err);
    window.showErrorBanner?.(t("status.loadError", { msg: err.message }));
    return;
  }

  const urlState = createUrlState();
  const drugMap = createDrugMap({ data, onChange: () => urlState.sync() });
  drugMap.registerUrl(urlState);
  // Apply the incoming link before the first draw (each applied key re-renders, but a
  // newer render cancels an older one, so only the last is drawn), then follow later
  // hash edits.
  urlState.applyHash();
  urlState.start();
  drugMap.render();
}

main();
