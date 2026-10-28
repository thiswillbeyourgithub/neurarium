// The plot as a PNG, for the kebab menu's "Copy image". What the reader sees is an <svg>
// styled by the stylesheet plus two HTML overlays (the plot title and the watermark), so a
// bare XMLSerializer copy would lose every colour and both texts. Instead:
//   1. clone the svg and inline, element by element, the computed styles that paint it
//      (an svg drawn as an <img> sees no page stylesheet);
//   2. draw it on a canvas at the device pixel ratio (at least 2x, so a pasted image stays
//      crisp), over the plot background;
//   3. draw the title and the watermark on top with canvas text, at the boxes they occupy
//      on screen, in their computed font and colour.
//   4. draw the Legend under the plot (colour keys, then the axis meaning, a dropdown caption by its summary line only), read off its
//      DOM whether its fold is open or not, so the picture explains itself. The nested
//      "Extra details" fold is simply never drawn (it is the numbers, not the legend).
// The page font is a system stack (css/base.css), which an svg image can use too, so the
// names land where they are on screen.

// The presentation properties the map's svg relies on (dots, names with their halo,
// leaders, grid).
const PAINT = ["fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-dasharray",
  "stroke-linejoin", "stroke-linecap", "paint-order", "opacity", "visibility", "display",
  "font-family", "font-size", "font-weight", "font-style", "letter-spacing", "text-anchor",
  "dominant-baseline"];

/**
 * Inline the painting styles of `src` (and every descendant) onto its clone.
 * @param {SVGSVGElement} src
 * @returns {SVGSVGElement}
 */
function styledClone(src) {
  const copy = src.cloneNode(true);
  const from = [src, ...src.querySelectorAll("*")];
  const to = [copy, ...copy.querySelectorAll("*")];
  from.forEach((node, i) => {
    const cs = getComputedStyle(node);
    to[i].setAttribute("style", PAINT.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";"));
  });
  // Hover tooltips do not belong in a picture.
  copy.querySelectorAll("title").forEach((n) => n.remove());
  return copy;
}

// Word-wrap `text` into lines no wider than `width` in the canvas' current font.
function wrap(ctx, text, width) {
  const lines = [];
  let cur = "";
  for (const word of text.split(/\s+/)) {
    const next = cur ? `${cur} ${word}` : word;
    if (cur && ctx.measureText(next).width > width) { lines.push(cur); cur = word; } else cur = next;
  }
  if (cur) lines.push(cur);
  return lines;
}

// Draw an HTML overlay's text where it sits over the svg.
function drawOverlay(ctx, node, origin, align) {
  if (!node || !node.textContent || node.offsetParent === null) return;
  const cs = getComputedStyle(node);
  const r = node.getBoundingClientRect();
  ctx.save();
  ctx.globalAlpha = Number(cs.opacity);
  ctx.fillStyle = cs.color;
  ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  ctx.textBaseline = "top";
  ctx.textAlign = align;
  const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.3;
  const x = align === "center" ? r.left + r.width / 2 : align === "right" ? r.right : r.left;
  wrap(ctx, node.textContent, r.width + 1).forEach((l, i) => ctx.fillText(l, x - origin.left, r.top - origin.top + i * lh));
  ctx.restore();
}

const LEGEND_PAD = 12; // px around and between the legend's parts
const fontOf = (cs) => `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;

/**
 * Lay out (and, given `draw`, paint) the legend under the plot; returns its height. Run
 * once to size the canvas, once to draw. Keys flow left to right and wrap like the page's
 * flex row: a `.dm-key` with a `.dm-dot` is a swatch + label, a bare `.dm-key` a label, a
 * `.dm-ramp` the year gradient (its computed colours). Then the axes heading (bold) and
 * each axis caption, word-wrapped.
 * @param {CanvasRenderingContext2D} ctx
 * @param {{keys: HTMLElement, head: HTMLElement, axes: HTMLElement}} legend
 * @param {number} top
 * @param {number} width
 * @param {boolean} draw
 * @returns {number}
 */
function legendBlock(ctx, { keys, head, axes }, top, width, draw) {
  const left = LEGEND_PAD, right = width - LEGEND_PAD;
  let y = top + LEGEND_PAD;
  const kcs = getComputedStyle(keys);
  const size = parseFloat(kcs.fontSize) || 11, lh = Math.round(size * 1.6);
  ctx.save();
  ctx.textBaseline = "middle";
  ctx.font = fontOf(kcs);
  let x = left;
  const place = (w) => {
    if (x > left && x + w > right) { x = left; y += lh; }
    const at = x;
    x += w + 12;
    return at;
  };
  // `mid` is read AFTER `place`, which may wrap to the next line.
  for (const node of keys.children) {
    if (node.classList.contains("dm-ramp")) {
      const at = place(160), mid = y + lh / 2;
      if (draw) {
        const stops = getComputedStyle(node).backgroundImage.match(/rgba?\([^)]*\)/g) || [];
        const g = ctx.createLinearGradient(at, 0, at + 160, 0);
        stops.forEach((c, i) => g.addColorStop(stops.length > 1 ? i / (stops.length - 1) : 0, c));
        ctx.fillStyle = stops.length ? g : kcs.color;
        ctx.fillRect(at, mid - 4, 160, 8);
      }
      continue;
    }
    const dot = node.querySelector(".dm-dot");
    const text = node.textContent;
    const w = (dot ? 13 : 0) + ctx.measureText(text).width;
    const at = place(w), mid = y + lh / 2;
    if (!draw) continue;
    if (dot) {
      ctx.fillStyle = getComputedStyle(dot).backgroundColor;
      ctx.beginPath();
      ctx.arc(at + 4, mid, 4, 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.fillStyle = kcs.color;
    ctx.fillText(text, at + (dot ? 13 : 0), mid);
  }
  if (keys.children.length) y += lh;
  ctx.textBaseline = "top";
  // A PC caption is a <details> dropdown: only its summary line belongs in the picture.
  const lineOf = (n) => n.querySelector(":scope > summary") || n;
  for (const [node, bold] of [[head, true], ...[...axes.children].map((n) => [lineOf(n), false])]) {
    if (!node.textContent) continue;
    const cs = getComputedStyle(node);
    ctx.font = fontOf(cs);
    if (bold) y += LEGEND_PAD / 2;
    const alh = Math.round((parseFloat(cs.fontSize) || 11) * 1.45);
    for (const l of wrap(ctx, node.textContent, right - left)) {
      if (draw) { ctx.fillStyle = cs.color; ctx.fillText(l, left, y); }
      y += alh;
    }
  }
  ctx.restore();
  return y + LEGEND_PAD - top;
}

/**
 * Render the plot to a PNG blob, with the legend under it when given.
 * @param {SVGSVGElement} svg
 * @param {{overlays: {node: HTMLElement, align: CanvasTextAlign}[],
 *   legend?: {keys: HTMLElement, head: HTMLElement, axes: HTMLElement}}} opts
 * @returns {Promise<Blob>}
 */
export async function plotPng(svg, { overlays = [], legend = null } = {}) {
  const box = svg.getBoundingClientRect();
  const scale = Math.max(2, window.devicePixelRatio || 1);
  const clone = styledClone(svg);
  clone.setAttribute("width", box.width);
  clone.setAttribute("height", box.height);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new window.XMLSerializer().serializeToString(clone))}`;
  const img = new Image();
  await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = url; });

  const canvas = document.createElement("canvas");
  const extra = legend ? legendBlock(canvas.getContext("2d"), legend, box.height, box.width, false) : 0;
  canvas.width = Math.round(box.width * scale);
  canvas.height = Math.round((box.height + extra) * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  ctx.fillStyle = getComputedStyle(svg).backgroundColor;
  ctx.fillRect(0, 0, box.width, box.height + extra);
  if (legend) {
    // A hairline between the plot and its legend, in the grid's ink.
    ctx.fillStyle = getComputedStyle(legend.keys).color;
    ctx.globalAlpha = 0.25;
    ctx.fillRect(0, box.height, box.width, 1);
    ctx.globalAlpha = 1;
    legendBlock(ctx, legend, box.height, box.width, true);
  }
  ctx.drawImage(img, 0, 0, box.width, box.height);
  for (const { node, align } of overlays) drawOverlay(ctx, node, box, align);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob"))), "image/png"));
}

/**
 * Put the PNG on the clipboard; where the browser refuses (no ClipboardItem, or an
 * insecure origin), download it instead, so the click always yields the picture.
 * `ClipboardItem` gets the PROMISE of the blob: Safari only allows a clipboard write
 * started synchronously inside the click.
 * @param {() => Promise<Blob>} make
 * @param {string} filename
 * @returns {Promise<"copied"|"downloaded">}
 */
export async function copyPng(make, filename) {
  const blob = make();
  try {
    await navigator.clipboard.write([new window.ClipboardItem({ "image/png": blob })]);
    return "copied";
  } catch {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    return "downloaded";
  }
}
