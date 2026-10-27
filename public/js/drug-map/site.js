// Where the drugs map page and the 3D viewer live relative to each other, so a link
// from one to the other works on every host the two are served from:
//   - neurarium.olicorne.org (and a local tools/serve.py): both pages sit side by side
//     at the site root (index.html + drugs-map.html), so plain relative links work.
//   - drugsmap.olicorne.org: the outer reverse proxy rewrites `/` to drugs-map.html
//     (docs/drugs-map/README.md, "Hosting"), so the map is served at path `/` and every
//     other path on that host is the same container. A relative link to the viewer
//     would then load the 3D app under the map's domain, so the viewer is reached at
//     its canonical address instead.
// No DOM, no data: imported by the map (js/drug-map/view.js) and the viewer's Drugs
// list (js/legend/drugs.js).

import { LIST_SEP } from "../url-state.js";

/** The viewer's public address: one of the hardcoded SEO spots (see CLAUDE.md). */
export const NEURARIUM_URL = "https://neurarium.olicorne.org/";
/** The map page's file, relative to the site root. */
export const MAP_PAGE = "drugs-map.html";

/** True when the map is the whole site (served at `/` by the dedicated host). */
const mapIsRoot = () => location.pathname === "/";

/** The 3D viewer's address, without a hash. */
export function viewerUrl() {
  return mapIsRoot() ? NEURARIUM_URL : new URL("./", location.href).href.replace(/[?#].*$/, "");
}

/**
 * A link from the viewer to the map, optionally pre-filtered. The view rides the hash
 * in the map's own `dm*` keys (js/drug-map/view.js registerUrl), so the link is also
 * the map's deep link.
 * @param {{cats?: string[], years?: [number, number]}} [filter]
 */
export function mapUrl({ cats, years } = {}) {
  const hash = cats ? `#dmcat=${cats.join(LIST_SEP)}` : years ? `#dmyear=${years[0]}-${years[1]}` : "";
  return `${MAP_PAGE}${hash}`;
}
