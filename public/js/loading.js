// Startup loading overlay: a centered progress bar shown while the dataset is
// fetched and the brain's meshes are built, so a slow first load gives feedback
// instead of a blank canvas (the data is several JSONL files + ~40 shape files,
// then the SDF meshing). Pure DOM, no three.js.
//
// The markup lives static AND visible in index.html (#loading), so it paints on
// the very first frame, before any ES module finishes parsing; this module only
// drives the bar and fades the overlay out. If the markup is missing it degrades
// to no-ops, so the app never depends on it.

/**
 * Wire the static #loading overlay.
 * @returns {{ setProgress(frac:number, label?:string):void, done():void, fail():void }}
 */
export function createLoadingScreen() {
  const root = document.getElementById("loading");
  const bar = document.getElementById("loading-bar");
  const caption = document.getElementById("loading-caption");
  if (!root) return { setProgress() {}, done() {}, fail() {} };

  // Only ever move the bar forward: the fetch + mesh phases report independently
  // and a later phase must never visually rewind an earlier one.
  let current = 0;
  function setProgress(frac, label) {
    const f = Math.max(current, Math.min(1, Number(frac) || 0));
    current = f;
    if (bar) bar.style.width = `${(f * 100).toFixed(1)}%`;
    if (label != null && caption) caption.textContent = label;
  }

  function remove() {
    root.remove(); // detaching twice is a harmless no-op
  }
  // Fill to 100%, fade out (CSS `.loaded` opacity transition), then detach so the
  // overlay never intercepts pointer events. A timeout (not transitionend) does
  // the removal: the bar's own width transition bubbles a transitionend up to the
  // root, which would otherwise tear it down early.
  function done() {
    setProgress(1);
    root.classList.add("loaded");
    setTimeout(remove, 500); // matches the #loading.loaded fade duration
  }
  // On a load failure an error banner takes over, so drop the overlay outright
  // rather than leave a half-filled bar stuck on screen.
  function fail() {
    remove();
  }

  return { setProgress, done, fail };
}
