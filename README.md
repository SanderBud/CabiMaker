# Cabinet Builder

Design a plywood drawer cabinet, look at it in 3D, and get the cut list.

- `cabinet.py` – the engine (pure Python, no dependencies). Works on the command line and in the browser.
- `src/template.html` – the page: inputs, three.js 3D view, tables.
- `build.py` – pastes `cabinet.py` into the template and writes `index.html`.
- `index.html` – the built site. This is what GitHub Pages serves.

In the browser the Python code runs with [Brython](https://brython.info) (loaded from jsDelivr), so no server is needed.

## Run locally

```bash
python cabinet.py                      # example cabinet
python cabinet.py example-config.json  # your own config
python build.py                        # rebuild index.html after editing cabinet.py or the template
python -m http.server                  # then open http://localhost:8000
```

## Host on GitHub Pages

1. Create a repository and push these files (at least `index.html`).
2. Repository → Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
3. The site appears at `https://<user>.github.io/<repo>/` after a minute.

Always run `python build.py` and commit `index.html` after changing `cabinet.py`.

## Construction rules

- Outer side panels run the full height; top, bottom and shelves fit between them.
- A shelf between rows is one continuous piece across the inner width.
- Column dividers sit between two horizontal panels, sunk `sink` mm into a dado in both (length = opening height + 2 × sink). Columns in different rows need not line up.
- Optional back panel covers the full back; carcass depth = depth − back thickness.
- Drawers are built like the carcass: opening minus the margin on every side and at the back; the sides run the full height and depth, the bottom fits between the sides, and front and back fit between the sides on top of the bottom.
- Materials: plywood you already have is filled first; the rest goes on new sheets (what you need to buy). Packing is a simple guillotine layout, so treat it as an estimate.
- Nails: glue plus one nail every `nail_spacing` mm (default 100) along each joint, at least 2 per joint; +10 % spare in the shopping total.

## Config

Sizes in mm. `stock` is a list of `{"thickness", "length", "width", "count"}` for plywood you already own. Row `height` and `widths` accept `auto` or numbers; `widths` is a comma-separated list per drawer (`"300, auto"`).
