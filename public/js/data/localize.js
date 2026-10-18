// Data-string localization (the emitted data is English-only; see i18n.js `pick`).

/**
 * Resolve a data string to the chosen language. The emitted data is English-only
 * (see generate_data.py's `externalize`); `window.__I18N__.pick` swaps in the
 * French side-table translation when the visitor reads French. js/i18n.js is a
 * classic script that runs before every module, so `__I18N__` is always there.
 * @param {string} field
 * @returns {string}
 */
export function localize(field) {
  return window.__I18N__.pick(field);
}

// Localize every value of an `{id: {en,fr}}` presentation map to a plain string.
export const localizeMap = (m) =>
  Object.fromEntries(Object.entries(m || {}).map(([k, v]) => [k, localize(v)]));
