// Re-export of the guided-tour engine, which lives in js/tour/ (index.js is the
// step machine; overlay.js, layout.js and scroll.js its parts).

import { createTour } from "./tour/index.js";

export { createTour };
