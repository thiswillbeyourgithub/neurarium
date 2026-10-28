// The plot as a PNG, for the kebab menu's "Copy image". What the reader sees is an <svg>
// styled by the stylesheet plus two HTML overlays (the plot title and the watermark), so a
// bare XMLSerializer copy would lose every colour and both texts. Instead:
//   1. clone the svg and inline, element by element, the computed styles that paint it
//      (an svg drawn as an <img> sees no page stylesheet);
//   2. draw it on a canvas at the device pixel ratio (at least 2x, so a pasted image stays
//      crisp), over the plot background;
//   3. draw the title and the watermark on top with canvas text, at the boxes they occupy
//      on screen, in their computed font and colour.
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

/**
 * Render the plot to a PNG blob.
 * @param {SVGSVGElement} svg
 * @param {{overlays: {node: HTMLElement, align: CanvasTextAlign}[]}} opts
 * @returns {Promise<Blob>}
 */
export async function plotPng(svg, { overlays = [] } = {}) {
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
  canvas.width = Math.round(box.width * scale);
  canvas.height = Math.round(box.height * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  ctx.fillStyle = getComputedStyle(svg).backgroundColor;
  ctx.fillRect(0, 0, box.width, box.height);
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
