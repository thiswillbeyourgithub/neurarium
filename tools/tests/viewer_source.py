"""The viewer's source as one text, for the structural lints that read it.

The viewer is split across `public/js/**/*.js` (main.js is wiring, the panel, legends,
scene and search live in their own modules), so a lint that asserts "this call / this
landmark exists" reads every module rather than pinning one file a refactor can move it
out of. Files are joined in a stable order, each separated by a newline, so a landmark
pair (`section(opening, closing)`) still resolves within the file that holds it.

The stylesheet is split the same way (`public/css/*.css`, linked from index.html in
cascade order), so the CSS lints read `viewer_css()` rather than one file.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "public" / "js"
INDEX = ROOT / "public" / "index.html"
# Every HTML page the site serves: the viewer, and the drugs map page that reuses its
# stylesheets (public/drugs-map.html).
PAGES = (INDEX, ROOT / "public" / "drugs-map.html")


def viewer_js() -> str:
    """Every viewer module's source, concatenated (sorted path order)."""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(JS_DIR.rglob("*.js")))


def stylesheet_hrefs(page: Path = INDEX) -> list[str]:
    """The `<link rel="stylesheet">` hrefs of `page` (default index.html), in cascade order."""
    html = page.read_text(encoding="utf-8")
    return re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)


def viewer_css() -> str:
    """Every linked stylesheet, concatenated in cascade (link) order: index.html's, then
    any other page's (drugs-map.html) that index.html does not link, so a theme check
    also sees a sheet only the drugs map loads."""
    hrefs = stylesheet_hrefs()
    for page in PAGES[1:]:
        hrefs += [h for h in stylesheet_hrefs(page) if h not in hrefs]
    return "\n".join((INDEX.parent / href).read_text(encoding="utf-8") for href in hrefs)
