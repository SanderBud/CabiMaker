"""Build index.html (for GitHub Pages) from src/template.html + cabinet.py.

The Python engine is pasted into the page, so the site is one static file plus
the Brython and three.js scripts from the jsDelivr CDN.

    python build.py            -> index.html
    python build.py --fragment -> dist/fragment.html (body-only version, for embedding)
"""
import pathlib
import sys

here = pathlib.Path(__file__).parent
template = (here / "src" / "template.html").read_text(encoding="utf-8")
engine = (here / "cabinet.py").read_text(encoding="utf-8")
if "</script" in engine:
    raise SystemExit("cabinet.py may not contain '</script'")
page = template.replace("/*__CABINET_PY__*/", engine)

if "--fragment" in sys.argv:
    out = here / "dist" / "fragment.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page.replace("<!-- BODY -->\n", ""), encoding="utf-8")
else:
    head, body = page.split("<!-- BODY -->", 1)
    html = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + head + "</head>\n<body>" + body + "</body>\n</html>\n")
    out = here / "index.html"
    out.write_text(html, encoding="utf-8")
print("wrote", out)
