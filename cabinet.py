"""Cabinet Builder engine: plywood drawer cabinet -> 3D pieces + cut list.

Pure Python without imports, so the same file runs under CPython (command line)
and under Brython in the browser (GitHub Pages).

Conventions (all sizes in mm)
-----------------------------
Coordinates: x = left -> right, y = floor -> top, z = back -> front (front face at z = depth).

Carcass
  * The two outer side panels run the full height.
  * Top, bottom and the row shelves run between the side panels (full inner width,
    continuous across the whole row, whatever the column layout above/below).
  * Column dividers sit between two horizontal panels and are sunk `sink` mm into
    a dado (groove) in the panel above and the panel below, so their length is
    opening height + 2 * sink. Columns of different rows do not need to line up.
  * Optional back panel is screwed on the back and covers the full width x height;
    the carcass depth is then depth - back thickness, so the outer depth is kept.

Drawers (plain boxes, front flush with the cabinet front), built like the carcass
  * Drawer box = opening minus `clearance` on every side (left, right, top, bottom)
    and minus `clearance` at the back.
  * The drawer sides run the full drawer height and depth.
  * The bottom fits between the sides (full depth); front and back fit between the
    sides and stand on the bottom.

Materials
  * Plywood you already have (`stock`) is filled first; the rest goes on new sheets
    of sheet_length x sheet_width, which are what you still need to buy.
  * Nails: every joint is glued and nailed through the face of one panel into the
    edge of the other, one nail every `nail_spacing` mm (at least 2 per joint).
"""

try:
    from browser import window
    IN_BROWSER = True
except ImportError:
    window = None
    IN_BROWSER = False


DEFAULT_CONFIG = {
    "width": 600, "height": 900, "depth": 400,
    "thickness": 18, "drawer_thickness": 18,
    "back_panel": True, "back_thickness": 18,
    "clearance": 2, "sink": 6,
    "sheet_length": 2440, "sheet_width": 1220, "kerf": 3,
    "nail_spacing": 100,
    "stock": [],   # e.g. [{"thickness": 12, "length": 1220, "width": 1220, "count": 1}]
    "rows": [
        {"drawers": 2, "height": "auto", "widths": "auto"},
        {"drawers": 3, "height": "auto", "widths": "auto"},
        {"drawers": 1, "height": 360, "widths": "auto"},
    ],
}

PART_ORDER = ["Side", "Top", "Bottom", "Shelf", "Divider", "Back panel",
              "Drawer side", "Drawer bottom", "Drawer front", "Drawer back"]


class CabinetError(Exception):
    pass


def r1(x):
    """Round to 0.1 mm and drop the trailing .0."""
    v = round(float(x) * 10) / 10
    if v == int(v):
        return int(v)
    return v


def num(cfg, key, minimum=None, allow_zero=True):
    val = cfg.get(key, DEFAULT_CONFIG.get(key))
    try:
        v = float(val)
    except (TypeError, ValueError):
        raise CabinetError("'%s' must be a number (got %r)." % (key, val))
    if minimum is not None and v < minimum:
        raise CabinetError("'%s' must be at least %s mm." % (key, minimum))
    if not allow_zero and v <= 0:
        raise CabinetError("'%s' must be larger than 0." % key)
    return v


def parse_spec(spec, n, what):
    """'auto' / '' / None -> [None]*n ; '300, auto, 200' -> [300, None, 200]."""
    if spec is None:
        return [None] * n
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        items = [str(spec)]
    else:
        items = [p.strip() for p in str(spec).replace(";", ",").split(",")]
        items = [p for p in items if p != ""]
    if len(items) == 1 and items[0].lower() in ("auto", "a", "*"):
        return [None] * n
    if len(items) > n:
        raise CabinetError("%s: %d values given for %d drawer(s)." % (what, len(items), n))
    out = []
    for p in items:
        if p.lower() in ("auto", "a", "*"):
            out.append(None)
        else:
            try:
                v = float(p)
            except ValueError:
                raise CabinetError("%s: '%s' is not a number or 'auto'." % (what, p))
            if v <= 0:
                raise CabinetError("%s: sizes must be larger than 0." % what)
            out.append(v)
    while len(out) < n:
        out.append(None)
    return out


def distribute(total, specs, what):
    fixed = sum(v for v in specs if v is not None)
    n_auto = len([v for v in specs if v is None])
    if n_auto == 0:
        if abs(fixed - total) > 0.05:
            raise CabinetError("%s: fixed sizes add up to %s mm but %s mm is available. "
                               "Set one of them to 'auto'." % (what, r1(fixed), r1(total)))
        return list(specs)
    rest = total - fixed
    if rest <= 0:
        raise CabinetError("%s: fixed sizes (%s mm) leave no room for the 'auto' ones "
                           "(%s mm available)." % (what, r1(fixed), r1(total)))
    each = rest / n_auto
    return [each if v is None else v for v in specs]


def box(x0, y0, z0, x1, y1, z1):
    return [r1(x0), r1(y0), r1(z0), r1(x1), r1(y1), r1(z1)]


def compute(cfg):
    """Return a result dict. Raises CabinetError on impossible input."""
    W = num(cfg, "width", allow_zero=False)
    H = num(cfg, "height", allow_zero=False)
    D = num(cfg, "depth", allow_zero=False)
    t = num(cfg, "thickness", allow_zero=False)
    td = num(cfg, "drawer_thickness", allow_zero=False)
    has_back = bool(cfg.get("back_panel", True))
    tb = num(cfg, "back_thickness", allow_zero=False) if has_back else 0.0
    c = num(cfg, "clearance", minimum=0)
    s = num(cfg, "sink", minimum=0)
    sheet_l = num(cfg, "sheet_length", allow_zero=False)
    sheet_w = num(cfg, "sheet_width", allow_zero=False)
    kerf = num(cfg, "kerf", minimum=0)
    nail_spacing = num(cfg, "nail_spacing", allow_zero=False)
    stock = parse_stock(cfg.get("stock") or [])
    rows_cfg = cfg.get("rows") or []
    if len(rows_cfg) == 0:
        raise CabinetError("Add at least one row.")

    warnings = []
    if s >= t:
        raise CabinetError("Column sink (%s mm) must be less than the plywood thickness (%s mm)." % (r1(s), r1(t)))

    Dc = D - tb          # carcass depth (sides, top, bottom, shelves, dividers)
    z0 = tb              # carcass starts in front of the back panel
    if Dc <= 0:
        raise CabinetError("Depth is too small for the back panel.")
    Wi = W - 2 * t       # inner width
    Hi = H - 2 * t       # inner height
    R = len(rows_cfg)
    avail_h = Hi - (R - 1) * t
    if Wi <= 0 or avail_h <= 0:
        raise CabinetError("The cabinet is too small for this plywood thickness and number of rows.")

    row_specs = []
    counts = []
    for i in range(R):
        row = rows_cfg[i]
        try:
            n = int(float(row.get("drawers", 1)))
        except (TypeError, ValueError):
            raise CabinetError("Row %d: number of drawers must be a whole number." % (i + 1))
        if n < 1:
            raise CabinetError("Row %d: needs at least 1 drawer." % (i + 1))
        counts.append(n)
        row_specs.append(parse_spec(row.get("height", "auto"), 1, "Row %d height" % (i + 1))[0])
    heights = distribute(avail_h, row_specs, "Row heights")

    pieces = []

    def add(part, label, L, Wd, T, bx, drawer=None, notes=None):
        a, b = (L, Wd) if L >= Wd else (Wd, L)
        if a <= 0 or b <= 0:
            raise CabinetError("%s (%s) gets a size of %s x %s mm. Make the cabinet or opening larger."
                               % (part, label, r1(L), r1(Wd)))
        p = {"id": len(pieces), "part": part, "label": label,
             "length": r1(a), "width": r1(b), "thickness": r1(T),
             "box": bx, "drawer": drawer, "notes": notes or []}
        pieces.append(p)
        return p

    # --- carcass -------------------------------------------------------------
    add("Side", "left", H, Dc, t, box(0, 0, z0, t, H, D))
    add("Side", "right", H, Dc, t, box(W - t, 0, z0, W, H, D))
    top = add("Top", "top", Wi, Dc, t, box(t, H - t, z0, W - t, H, D))
    horizontals = [top]  # panel above row i is horizontals[i]

    openings = []
    drawers = []
    ytop = H - t
    for i in range(R):
        h = heights[i]
        n = counts[i]
        ybot = ytop - h
        if h <= 0:
            raise CabinetError("Row %d has no height left." % (i + 1))
        wspecs = parse_spec(rows_cfg[i].get("widths", "auto"), n, "Row %d widths" % (i + 1))
        avail_w = Wi - (n - 1) * t
        if avail_w <= 0:
            raise CabinetError("Row %d: too many drawers for this width." % (i + 1))
        widths = distribute(avail_w, wspecs, "Row %d widths" % (i + 1))
        # panel below this row
        if i < R - 1:
            below = add("Shelf", "between row %d and %d" % (i + 1, i + 2), Wi, Dc, t,
                        box(t, ybot - t, z0, W - t, ybot, D))
        else:
            below = add("Bottom", "bottom", Wi, Dc, t, box(t, 0, z0, W - t, t, D))
        above = horizontals[i]
        horizontals.append(below)

        x = t
        for j in range(n):
            w = widths[j]
            if w <= 0:
                raise CabinetError("Row %d, drawer %d has no width left." % (i + 1, j + 1))
            did = "%d.%d" % (i + 1, j + 1)
            openings.append({"id": did, "row": i + 1, "col": j + 1,
                             "x0": r1(x), "x1": r1(x + w), "y0": r1(ybot), "y1": r1(ytop),
                             "width": r1(w), "height": r1(h)})
            drawers.append(make_drawer(add, did, x, ybot, w, h, D, Dc, c, td))
            if j < n - 1:
                xd = x + w
                add("Divider", "row %d, between drawer %d and %d" % (i + 1, j + 1, j + 2),
                    h + 2 * s, Dc, t, box(xd, ybot - s, z0, xd + t, ytop + s, D),
                    notes=["length includes %s mm sink at both ends" % r1(s)] if s > 0 else [])
                if s > 0:
                    rel = xd - t  # position measured from the left end of the horizontal panel
                    above["notes"].append(("dado underside %s-%s mm from left end, %s deep"
                                           % (r1(rel), r1(rel + t), r1(s))))
                    above.setdefault("dados", []).append({"face": "under", "from": r1(rel), "to": r1(rel + t)})
                    below["notes"].append(("dado top face %s-%s mm from left end, %s deep"
                                           % (r1(rel), r1(rel + t), r1(s))))
                    below.setdefault("dados", []).append({"face": "top", "from": r1(rel), "to": r1(rel + t)})
                x = xd + t
        ytop = ybot - t

    # shelves with dados on both faces at the same spot
    for p in horizontals:
        d = p.get("dados", [])
        ups = [q for q in d if q["face"] == "top"]
        downs = [q for q in d if q["face"] == "under"]
        for u in ups:
            for v in downs:
                if u["from"] < v["to"] and v["from"] < u["to"] and 2 * s >= t:
                    raise CabinetError("The %s gets dados on both faces at %s mm; with %s mm sink "
                                       "they cut through. Reduce the sink or shift a column."
                                       % (p["part"].lower(), u["from"], r1(s)))
                if u["from"] < v["to"] and v["from"] < u["to"] and t - 2 * s < t / 2:
                    warnings.append("The %s (%s) has dados on both faces at %s mm: only %s of %s mm of wood "
                                    "remains there, less than half the board." % (p["part"].lower(), p["label"], u["from"],
                                                                                 r1(t - 2 * s), r1(t)))

    if has_back:
        add("Back panel", "back", H, W, tb, box(0, 0, 0, W, H, tb))

    cutlist = build_cutlist(pieces)
    sheets, shopping = pack_sheets(pieces, stock, sheet_l, sheet_w, kerf, warnings)
    nails = count_nails(W, H, Dc, t, tb, heights, counts, drawers, td, nail_spacing)

    area = 0.0
    for p in pieces:
        area += p["length"] * p["width"]
    summary = {
        "outer": [r1(W), r1(H), r1(D)],
        "inner_width": r1(Wi), "carcass_depth": r1(Dc),
        "row_heights": [r1(h) for h in heights],
        "piece_count": len(pieces), "drawer_count": len(drawers),
        "area_m2": round(area / 1e6 * 100) / 100,
        "sheet_count": len(sheets),
        "buy": shopping,
        "nail_total": nails["total"],
    }
    return {"ok": True, "errors": [], "warnings": warnings, "summary": summary,
            "openings": openings, "drawers": drawers, "pieces": pieces,
            "cutlist": cutlist, "sheets": sheets, "nails": nails}


def make_drawer(add, did, x, y, w, h, D, Dc, c, td):
    dw = w - 2 * c
    dh = h - 2 * c
    dd = Dc - c
    if dw <= 2 * td + 1 or dh <= td + 1 or dd <= 2 * td + 1:
        raise CabinetError("Drawer %s is too small (%s x %s x %s mm) for %s mm drawer plywood."
                           % (did, r1(dw), r1(dh), r1(dd), r1(td)))
    bx0 = x + c
    by0 = y + c
    bz0 = D - dd
    tag = "drawer " + did
    add("Drawer side", tag + " left", dd, dh, td, box(bx0, by0, bz0, bx0 + td, by0 + dh, D), drawer=did)
    add("Drawer side", tag + " right", dd, dh, td, box(bx0 + dw - td, by0, bz0, bx0 + dw, by0 + dh, D), drawer=did)
    add("Drawer bottom", tag, dw - 2 * td, dd, td, box(bx0 + td, by0, bz0, bx0 + dw - td, by0 + td, D), drawer=did)
    add("Drawer front", tag, dw - 2 * td, dh - td, td,
        box(bx0 + td, by0 + td, D - td, bx0 + dw - td, by0 + dh, D), drawer=did)
    add("Drawer back", tag, dw - 2 * td, dh - td, td,
        box(bx0 + td, by0 + td, bz0, bx0 + dw - td, by0 + dh, bz0 + td), drawer=did)
    return {"id": did, "opening": [r1(w), r1(h)],
            "outer": [r1(dw), r1(dh), r1(dd)],
            "inner": [r1(dw - 2 * td), r1(dh - td), r1(dd - 2 * td)],
            "box": box(bx0, by0, bz0, bx0 + dw, by0 + dh, D)}


def letter(i):
    s = ""
    i += 1
    while i > 0:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


def build_cutlist(pieces):
    groups = {}
    order = []
    for p in pieces:
        key = (p["part"], p["length"], p["width"], p["thickness"], " / ".join(p["notes"]))
        if key not in groups:
            groups[key] = {"part": p["part"], "length": p["length"], "width": p["width"],
                           "thickness": p["thickness"], "qty": 0, "where": [], "notes": list(p["notes"]),
                           "piece_ids": []}
            order.append(key)
        g = groups[key]
        g["qty"] += 1
        g["where"].append(p["label"])
        g["piece_ids"].append(p["id"])

    def sort_key(k):
        g = groups[k]
        idx = PART_ORDER.index(g["part"]) if g["part"] in PART_ORDER else 99
        return (-g["thickness"], idx, -g["length"], -g["width"])

    order.sort(key=sort_key)
    out = []
    for n, k in enumerate(order):
        g = groups[k]
        g["mark"] = letter(n)
        out.append(g)
    mark_of = {}
    for g in out:
        for pid in g["piece_ids"]:
            mark_of[pid] = g["mark"]
    for p in pieces:
        p["mark"] = mark_of[p["id"]]
    return out


def ceil_div(a, b):
    return int(-(-a // b))


def parse_stock(rows):
    """Plywood you already own: list of {thickness, length, width, count}."""
    out = []
    for i in range(len(rows)):
        row = rows[i]
        vals = []
        for key in ("thickness", "length", "width", "count"):
            raw = row.get(key, 1 if key == "count" else None)
            if raw is None or str(raw).strip() == "":
                raise CabinetError("Plywood in stock, line %d: fill in the %s." % (i + 1, key))
            try:
                vals.append(float(raw))
            except (TypeError, ValueError):
                raise CabinetError("Plywood in stock, line %d: %s must be a number." % (i + 1, key))
        T, L, Wd, n = vals
        if T <= 0 or L <= 0 or Wd <= 0 or n < 0:
            raise CabinetError("Plywood in stock, line %d: sizes must be larger than 0." % (i + 1))
        if Wd > L:
            L, Wd = Wd, L
        for k in range(int(n)):
            out.append({"thickness": r1(T), "length": r1(L), "width": r1(Wd), "line": i + 1})
    return out


def _new_bin(L, Wd, T, source, line=None):
    return {"length": L, "width": Wd, "thickness": T, "source": source, "line": line,
            "free": [[0.0, 0.0, L, Wd]], "parts": []}


def _fits(bn, l, w):
    return (l <= bn["length"] and w <= bn["width"]) or (w <= bn["length"] and l <= bn["width"])


def _place(bn, l, w, p, kerf):
    """Guillotine packing: put the piece in the free rectangle it fits most snugly
    (long side along the sheet length preferred), then split the leftover in two."""
    options = [(l, w, 0)] if l == w else [(l, w, 0), (w, l, 1)]
    best = None
    for pl, pw, rot in options:
        for i in range(len(bn["free"])):
            fx, fy, fw, fh = bn["free"][i]
            if pl <= fw and pw <= fh:
                score = (min(fw - pl, fh - pw), rot)
                if best is None or score < best[0]:
                    best = (score, i, pl, pw)
    if best is None:
        return False
    score, i, pl, pw = best
    fx, fy, fw, fh = bn["free"].pop(i)
    bn["parts"].append([r1(fx), r1(fy), pl, pw, p["mark"], p["id"]])
    rw = fw - pl - kerf   # leftover to the right
    bh = fh - pw - kerf   # leftover below
    if rw < bh:           # split so the larger leftover stays in one piece
        new = [[fx + pl + kerf, fy, rw, pw], [fx, fy + pw + kerf, fw, bh]]
    else:
        new = [[fx + pl + kerf, fy, rw, fh], [fx, fy + pw + kerf, pl, bh]]
    for r in new:
        if r[2] > 1 and r[3] > 1:
            bn["free"].append(r)
    return True


def pack_sheets(pieces, stock, SL, SW, kerf, warnings):
    """Fill your own plywood first, then new sheets (to buy). Guillotine packing per thickness:
    a realistic estimate, not an optimal nesting."""
    by_t = {}
    for p in pieces:
        by_t.setdefault(p["thickness"], []).append(p)
    thicknesses = list(by_t.keys())
    for st in stock:
        if st["thickness"] not in thicknesses:
            thicknesses.append(st["thickness"])
    sheets = []
    shopping = []
    for T in sorted(thicknesses, reverse=True):
        own = [st for st in stock if st["thickness"] == T]
        own.sort(key=lambda st: st["length"] * st["width"])
        items = sorted(by_t.get(T, []), key=lambda p: (-p["length"] * p["width"], -p["length"]))
        bins = []
        for p in items:
            L, Wd = p["length"], p["width"]
            placed = False
            for bn in bins:          # stock bins are opened first, so they fill first
                if _place(bn, L, Wd, p, kerf):
                    placed = True
                    break
            if placed:
                continue
            for k in range(len(own)):
                st = own[k]
                if _fits(st, L, Wd):
                    bn = _new_bin(st["length"], st["width"], T, "stock", st["line"])
                    own.pop(k)
                    _place(bn, L, Wd, p, kerf)
                    bins.append(bn)
                    placed = True
                    break
            if placed:
                continue
            bn = _new_bin(SL, SW, T, "buy")
            if _fits(bn, L, Wd):
                _place(bn, L, Wd, p, kerf)
                bins.append(bn)
            else:
                warnings.append("%s (%s, %s x %s mm) does not fit on a %s x %s sheet."
                                % (p["part"], p["label"], L, Wd, r1(SL), r1(SW)))
        bins.sort(key=lambda bn: 0 if bn["source"] == "stock" else 1)
        n_stock = len([st for st in stock if st["thickness"] == T])
        n_used = len([bn for bn in bins if bn["source"] == "stock"])
        n_buy = len(bins) - n_used
        shopping.append({"thickness": T, "buy": n_buy, "stock_used": n_used, "stock_total": n_stock,
                         "needed": len(by_t.get(T, [])) > 0})
        for bn in bins:
            used = 0.0
            for q in bn["parts"]:
                used += q[2] * q[3]
            sheets.append({"thickness": T, "length": bn["length"], "width": bn["width"],
                           "source": bn["source"], "line": bn["line"], "parts": bn["parts"],
                           "fill": round(used / (bn["length"] * bn["width"]) * 100)})
    return sheets, shopping


NAIL_SIZES = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100]


def nail_length(through):
    """Through the panel plus about 1.5x that (min 20 mm) into the edge of the other panel."""
    want = through + max(20.0, 1.5 * through)
    for size in NAIL_SIZES:
        if size >= want:
            return size
    return NAIL_SIZES[-1]


def count_nails(W, H, Dc, t, tb, heights, counts, drawers, td, spacing):
    """Glue + nails every `spacing` mm along each joint, starting 25 mm from the ends."""
    def per_joint(L):
        return max(2, ceil_div(L - 50, spacing) + 1)

    groups = []

    def add(joint, n_joints, L, through):
        if n_joints <= 0:
            return
        groups.append({"joint": joint, "joints": n_joints, "joint_length": r1(L),
                       "nails": n_joints * per_joint(L), "through": r1(through),
                       "nail_length": nail_length(through)})

    R = len(heights)
    n_div = sum(n - 1 for n in counts)
    add("Sides into top and bottom", 4, Dc, t)
    add("Sides into shelves", 2 * (R - 1), Dc, t)
    divider_nails = 0
    for i in range(R):
        divider_nails += 2 * (counts[i] - 1) * per_joint(Dc)
    if n_div:
        groups.append({"joint": "Top, bottom and shelves into dividers", "joints": 2 * n_div,
                       "joint_length": r1(Dc), "nails": divider_nails, "through": r1(t),
                       "nail_length": nail_length(t)})
    if tb > 0:
        add("Back panel into sides", 2, H, tb)
        add("Back panel into top and bottom", 2, W - 2 * t, tb)
        add("Back panel into shelves", R - 1, W - 2 * t, tb)
        for i in range(R):
            add("Back panel into dividers, row %d" % (i + 1), counts[i] - 1, heights[i], tb)
    # drawers: sides into front/back and bottom, bottom into front/back
    side_fb = side_bottom = bottom_fb = 0
    for d in drawers:
        dw, dh, dd = d["outer"]
        side_fb += 4 * per_joint(dh - td)
        side_bottom += 2 * per_joint(dd)
        bottom_fb += 2 * per_joint(dw - 2 * td)
    nd = len(drawers)
    for joint, k, n in (("Drawer sides into front and back", 4 * nd, side_fb),
                        ("Drawer sides into bottom", 2 * nd, side_bottom),
                        ("Drawer bottom into front and back", 2 * nd, bottom_fb)):
        if nd:
            groups.append({"joint": joint, "joints": k, "joint_length": None, "nails": n,
                           "through": r1(td), "nail_length": nail_length(td)})
    by_len = {}
    for g in groups:
        by_len[g["nail_length"]] = by_len.get(g["nail_length"], 0) + g["nails"]
    lengths = []
    total = 0
    for L in sorted(by_len.keys()):
        n = by_len[L]
        total += n
        lengths.append({"length": L, "count": n, "with_spare": ceil_div(n * 11, 10)})
    return {"spacing": r1(spacing), "groups": groups, "by_length": lengths, "total": total}


# --- serialisation (no json module needed, so Brython runs without its stdlib) --

def to_json(o):
    if o is None:
        return "null"
    if o is True:
        return "true"
    if o is False:
        return "false"
    if isinstance(o, (int, float)):
        if isinstance(o, float) and o == int(o) and abs(o) < 1e15:
            return str(int(o))
        return repr(o)
    if isinstance(o, str):
        out = ['"']
        for ch in o:
            if ch == '"':
                out.append('\\"')
            elif ch == "\\":
                out.append("\\\\")
            elif ord(ch) < 32:
                out.append("\\u%04x" % ord(ch))
            else:
                out.append(ch)
        out.append('"')
        return "".join(out)
    if isinstance(o, dict):
        return "{" + ",".join(to_json(str(k)) + ":" + to_json(v) for k, v in o.items()) + "}"
    if isinstance(o, (list, tuple)):
        return "[" + ",".join(to_json(v) for v in o) + "]"
    return to_json(str(o))


def from_json(text):
    # JSON is a valid Python expression once true/false/null are defined.
    return eval(text, {"__builtins__": {}}, {"true": True, "false": False, "null": None})


def compute_json(text):
    """Browser entry point: JSON config string in, JSON result string out."""
    try:
        return to_json(compute(from_json(text)))
    except CabinetError as e:
        return to_json({"ok": False, "errors": [str(e)], "warnings": []})
    except Exception as e:
        return to_json({"ok": False, "errors": ["Unexpected error: %s" % e], "warnings": []})


def print_cutlist(res):
    if not res.get("ok", True):
        print("ERROR:", "; ".join(res["errors"]))
        return
    print("%-4s %-14s %4s %8s %8s %5s  %s" % ("Mark", "Part", "Qty", "Length", "Width", "T", "Where / notes"))
    for g in res["cutlist"]:
        print("%-4s %-14s %4d %8s %8s %5s  %s" % (g["mark"], g["part"], g["qty"], g["length"], g["width"],
                                                 g["thickness"], "; ".join(g["where"] + g["notes"])))
    print()
    for d in res["drawers"]:
        print("Drawer %-5s opening %s x %s | box %s x %s x %s | inside %s x %s x %s" %
              tuple([d["id"]] + d["opening"] + d["outer"] + d["inner"]))
    s = res["summary"]
    print("\n%d pieces, %.2f m2 plywood." % (s["piece_count"], s["area_m2"]))
    for b in s["buy"]:
        print("%s mm: buy %d new sheet(s), using %d of %d stock piece(s)." % (b["thickness"], b["buy"],
                                                                          b["stock_used"], b["stock_total"]))
    for n in res["nails"]["by_length"]:
        print("Nails %d mm: %d (+10%% spare: %d)" % (n["length"], n["count"], n["with_spare"]))
    for w in res["warnings"]:
        print("Warning:", w)


if IN_BROWSER:
    window.cabinet_compute = compute_json
    if hasattr(window, "onPythonReady") and window.onPythonReady:
        window.onPythonReady()
elif __name__ == "__main__":
    import sys
    import json
    cfg = DEFAULT_CONFIG
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as fh:
            cfg = json.load(fh)
    try:
        print_cutlist(compute(cfg))
    except CabinetError as e:
        print("ERROR:", e)
        sys.exit(1)
