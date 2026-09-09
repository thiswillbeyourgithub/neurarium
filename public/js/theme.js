/**
 * Light / dark theme: which one is on, and who decided.
 *
 * The palette itself is CSS (the token block in `index.html`, redefined under
 * `:root[data-theme="light"]`). This module owns only the *decision*, which is
 * deliberately a short one: the visitor's own click, persisted in localStorage, and
 * failing that **dark**.
 *
 * Dark is the fallback because it is the ground the data colours (projection kinds,
 * effect dots, the additive glow of every animation) were chosen against, so a visitor
 * we know nothing about gets the palette that was actually art-directed.
 *
 * `prefers-color-scheme` is read by neither branch, and that is the non-obvious part.
 * The media feature dropped its `no-preference` value, so every browser answers `light`
 * to a light query whether the visitor asked for light or never touched the setting at
 * all. Following it would hand the un-art-directed palette to everyone who expressed
 * nothing, which is exactly the case the fallback exists for. A dark query IS
 * unambiguous, but it can only ever confirm the answer we already give. So the light
 * theme is opt-in, one click away in the panel header, and it sticks once taken.
 *
 * The 3D scene is not CSS, so it cannot read the tokens: `onChange` hands the resolved
 * page background to `js/main.js`, which repaints `scene.background`.
 *
 * Built with the help of Claude Code.
 */

const KEY = "neurarium.theme";
/** The themes the token block defines. Dark is the fallback; see the module note. */
export const THEMES = ["dark", "light"];

const readStored = () => {
  try {
    const raw = localStorage.getItem(KEY);
    return THEMES.includes(raw) ? raw : null;
  } catch {
    /* private mode / storage disabled: the visitor simply has no stored choice. */
    return null;
  }
};

/**
 * Wire the theme up.
 *
 * @param {(theme: string, pageBg: string) => void} [onChange] called on every applied
 *   theme, including the first, with the resolved `--page-bg` so a non-CSS surface
 *   (the WebGL canvas) can follow.
 * @returns {{get: () => string, set: (theme: string) => void, toggle: () => string}}
 */
export function createTheme(onChange) {
  let current = readStored() || "dark";

  const apply = () => {
    // The attribute is what the CSS keys on. Dark is written too, rather than left
    // implicit: the bare :root block is dark, but stamping it keeps the two states
    // symmetrical for anything reading the attribute (the button's own icons).
    document.documentElement.setAttribute("data-theme", current);
    // Keep the <meta> in step so the browser's own chrome (form controls, scrollbars,
    // and any "force dark" pass) reads the same scheme the page just switched to.
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.setAttribute("content", current);
    const bg = getComputedStyle(document.documentElement)
      .getPropertyValue("--page-bg").trim();
    if (onChange) onChange(current, bg);
  };

  apply();

  const set = (theme) => {
    if (!THEMES.includes(theme) || theme === current) return;
    current = theme;
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* best-effort, like every other preference: the choice holds for this visit. */
    }
    apply();
  };

  return {
    get: () => current,
    set,
    toggle: () => {
      set(current === "dark" ? "light" : "dark");
      return current;
    },
  };
}
