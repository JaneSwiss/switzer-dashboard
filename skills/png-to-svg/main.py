#!/usr/bin/env python3
"""
png-to-svg — trace a flat-color PNG (icons, line art, ChatGPT/DALL-E exports)
into a clean, Canva-ready SVG.

Fixes the two failure modes of naive raster tracing:
  1. Faceted/rough curves -> vtracer's proper bezier spline fitting
     (colormode=binary, hierarchical=cutout on a hard-thresholded mask;
     "stacked" mode and RGBA-direct binary mode both produce broken/solid
     blobs for anything with real holes, so don't use them).
  2. Uneven stroke width -> shapes classified as true strokes (rings,
     ticks, thin lines) are skeletonized, smoothed, measured, and rebuilt
     as a mathematically constant-width ribbon (skeleton offset by a fixed
     half-width via shapely.buffer). Solid/hybrid shapes (filled circles,
     part-filled shapes) are left to vtracer's direct trace, since they
     aren't strokes and skeletonizing them would collapse the fill.

Output SVG: cropped to the artwork's true bounds, scaled so the longer
side is --target-size units (matching Canva's SVG artboard spec), single
flat fill color, no live strokes (already expanded to fills). Writes only
the .svg by default -- pass --preview if a PNG render is wanted too.

Usage:
    python3 main.py path/to/icon.png
    python3 main.py path/to/icon.png --output path/to/icon.svg
    python3 main.py path/to/icon.png --fill "#361a11"
    python3 main.py path/to/icon.png --preview

Requires (pip3 install): vtracer scikit-image shapely scipy svgpathtools
svglib reportlab pymupdf Pillow numpy
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.morphology import skeletonize
from shapely.geometry import LineString
from shapely.ops import unary_union
import vtracer


# ---------- stroke reconstruction (skeletonize -> smooth -> constant-width buffer) ----------

def order_skeleton(skel):
    """Walk an 8-connected 1px skeleton into ordered (row,col) paths.

    Branch points (degree >= 3) used to abort the whole component back to
    vtracer's direct trace -- but vtracer's bezier fit bulges into a fat
    blob right at a T/Y junction (two thin strokes meeting at an angle),
    since it's smoothing a contour that has to wrap around the branch.
    Instead: split the skeleton into edges between "nodes" (endpoints and
    branch points) and walk each edge separately. Each segment then gets
    reconstructed as its own constant-width ribbon and they naturally meet
    cleanly at the shared node point, instead of one blobby fill."""
    ys, xs = np.where(skel)
    pts = set(zip(ys.tolist(), xs.tolist()))
    if not pts:
        return []

    def neighbors(p):
        y, x = p
        return [(y + dy, x + dx)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dy or dx) and (y + dy, x + dx) in pts]

    deg = {p: len(neighbors(p)) for p in pts}
    nodes = {p for p, d in deg.items() if d != 2}

    if not nodes:
        # pure simple closed loop -- no endpoints or branch points
        start = next(iter(pts))
        nbrs = neighbors(start)
        if len(nbrs) != 2:
            return None
        path = [start, nbrs[0]]
        prev, cur = start, nbrs[0]
        while cur != start:
            nxts = [q for q in neighbors(cur) if q != prev]
            if not nxts:
                break
            nxt = nxts[0]
            path.append(nxt)
            prev, cur = cur, nxt
        return [path]

    visited_steps = set()
    paths = []
    for node in nodes:
        for nb in neighbors(node):
            step = frozenset((node, nb))
            if step in visited_steps:
                continue
            visited_steps.add(step)
            path = [node, nb]
            prev, cur = node, nb
            while cur not in nodes:
                nxts = [q for q in neighbors(cur) if q != prev]
                if not nxts:
                    break
                nxt = nxts[0]
                s2 = frozenset((cur, nxt))
                if s2 in visited_steps:
                    break
                visited_steps.add(s2)
                path.append(nxt)
                prev, cur = cur, nxt
            if len(path) >= 2:
                paths.append(path)

    return paths


def smooth_polyline(pts, smooth_px=4.0, n_out=200, closed=False):
    from scipy.interpolate import splprep, splev
    pts = np.array(pts, dtype=float)
    if closed and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    x, y = pts[:, 1], pts[:, 0]  # (row,col) -> (x,y)
    try:
        tck, _ = splprep([x, y], s=smooth_px * len(pts),
                          per=1 if closed else 0, k=3 if len(pts) > 3 else 1)
        uu = np.linspace(0, 1, n_out)
        xs, ys = splev(uu, tck)
        return np.stack([xs, ys], axis=1)
    except Exception:
        return np.stack([x, y], axis=1)


def endpoint_taper_ratio(skel, dist):
    """Ratio of the thinnest skeleton endpoint's width to the shape's
    median width; 1.0 if the skeleton has no free endpoints (a closed loop).

    A genuine constant-width stroke (a ring, a tick, a bracket) stays
    roughly the same width along its whole length, including at any free
    ends. An organic tapering shape (a pine needle, a ribbon tail, a leaf
    point) necessarily narrows to near-zero at its tip -- but that tip is
    a tiny fraction of the skeleton's total pixel count, so the width-CV
    gate (aggregated over every skeleton pixel) can stay well under
    threshold even when a shape tapers sharply at its ends: the bulk
    "body" width dominates the statistic and the tip barely moves it.
    Checking width specifically at the endpoints catches what the
    aggregate CV misses."""
    ys, xs = np.where(skel)
    pts = set(zip(ys.tolist(), xs.tolist()))
    if not pts:
        return 1.0

    def neighbors(p):
        y, x = p
        return [(y + dy, x + dx)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dy or dx) and (y + dy, x + dx) in pts]

    deg = {p: len(neighbors(p)) for p in pts}
    endpoints = [p for p, d in deg.items() if d == 1]
    if not endpoints:
        return 1.0
    widths = dist[skel] * 2
    median_w = np.median(widths)
    if median_w <= 0:
        return 1.0
    ep_widths = [dist[p] * 2 for p in endpoints]
    return float(min(ep_widths) / median_w)


def reconstruct_stroke(comp_mask, smooth_px=4.0, width_percentile=50):
    """comp_mask: boolean 2D array, one connected ink component.
    Returns (shapely geometry in absolute x,y pixel coords, width) or None."""
    skel = skeletonize(comp_mask)
    paths = order_skeleton(skel)
    if not paths:
        return None

    dist = ndimage.distance_transform_edt(comp_mask)
    widths = dist[skel] * 2.0
    if len(widths) == 0:
        return None
    width = float(np.percentile(widths, width_percentile))

    polys = []
    try:
        for path in paths:
            if len(path) < 4:
                continue
            closed = path[0] == path[-1]
            sm = smooth_polyline(path, smooth_px=smooth_px,
                                  n_out=max(80, min(len(path), 400)), closed=closed)
            if closed:
                line = LineString(np.vstack([sm, sm[0]]))
            else:
                line = LineString(sm)
            polys.append(line.buffer(width / 2.0, cap_style='round', join_style='round'))
    except Exception:
        return None

    if not polys:
        return None
    return unary_union(polys), width


def polygon_to_path_d(poly):
    parts = []
    def ring_d(coords):
        pts = list(coords)
        return (f"M {pts[0][0]:.3f} {pts[0][1]:.3f} " +
                " ".join(f"L {x:.3f} {y:.3f}" for x, y in pts[1:]) + " Z")
    geoms = [poly] if poly.geom_type == 'Polygon' else list(poly.geoms)
    for p in geoms:
        parts.append(ring_d(p.exterior.coords))
        for interior in p.interiors:
            parts.append(ring_d(interior.coords))
    return " ".join(parts)


# ---------- SVG path transform helpers ----------

def apply_transform(d, dx, dy, s=1.0):
    tokens = re.findall(r'[A-Za-z]|-?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r'^[A-Za-z]$', t):
            out.append(t)
            i += 1
        else:
            x, y = float(t), float(tokens[i + 1])
            out.append(f"{(x + dx) * s:.3f} {(y + dy) * s:.3f}")
            i += 2
    return " ".join(out)


# ---------- main pipeline ----------

def detect_ink_color(rgba, alpha_thresh=128):
    arr = np.array(rgba)
    mask = arr[..., 3] >= alpha_thresh
    if not mask.any():
        return (0, 0, 0)
    pixels = arr[mask][:, :3]
    sample = pixels[::max(1, len(pixels) // 20000)]

    # bucket by /8 to merge anti-aliased near-duplicate shades, so a hard
    # line-art edge doesn't get split into dozens of 1-off colors
    bucketed = Counter(map(tuple, (sample // 8 * 8)))
    total = sum(bucketed.values())
    # keep buckets with a real presence (not stray anti-alias fringe pixels)
    common = [c for c, n in bucketed.items() if n / total >= 0.01]
    if not common:
        common = [bucketed.most_common(1)[0][0]]

    # ink/outline is virtually always the darkest tone in flat line art —
    # a lighter fill color (shading, highlights) can otherwise out-count
    # the actual outline and get picked instead, which then breaks vtracer's
    # trace entirely (near-white ink on a white background has no contrast
    # for it to threshold against)
    def luminance(c):
        r, g, b = c
        return 0.299 * r + 0.587 * g + 0.114 * b

    darkest_bucket = tuple(int(v) for v in min(common, key=luminance))
    # return the precise (unbucketed) most common exact color within that bucket
    exact = Counter(
        tuple(int(v) for v in p) for p in sample
        if all(abs(int(p[i]) - darkest_bucket[i]) < 8 for i in range(3))
    )
    return exact.most_common(1)[0][0] if exact else darkest_bucket


def ink_mask(arr, alpha_thresh=128, white_cutoff=235):
    """Boolean mask of true ink pixels: opaque AND not near-white.

    Some source PNGs carry a very light (near-white) fill or shading color
    alongside the actual dark outline -- e.g. a cream bowl-body fill only a
    few luminance units off pure white. Treating that as "ink" (which a
    plain alpha>=thresh test would) collapses it into a solid block once
    flattened to one fill color, turning hollow line art into a heavy
    silhouette. Excluding near-white pixels here keeps only the real
    outline, matching the flat hollow-line-art convention this pipeline
    targets. Harmless for genuinely single-tone icons -- they have no
    near-white content to begin with.
    """
    alpha = arr[..., 3]
    lum = 0.299 * arr[..., 0].astype(int) + 0.587 * arr[..., 1].astype(int) + 0.114 * arr[..., 2].astype(int)
    return (alpha >= alpha_thresh) & (lum < white_cutoff)


def trace_png_to_svg(input_path, output_path=None, fill_hex=None,
                      target_size=500.0, stroke_fill_ratio=0.45,
                      alpha_thresh=128, white_cutoff=235, filter_speckle=4,
                      thick_fill_diameter=50.0, stroke_width_cv=0.2,
                      endpoint_taper_min=0.4, verbose=True):
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_suffix(".svg")
    output_path = Path(output_path)

    im = Image.open(input_path).convert("RGBA")
    ink_rgb = detect_ink_color(im, alpha_thresh)
    fill_hex = fill_hex or "#{:02x}{:02x}{:02x}".format(*ink_rgb)
    if verbose:
        print(f"detected ink color: {fill_hex}")

    arr = np.array(im)
    mask = ink_mask(arr, alpha_thresh, white_cutoff)

    labeled, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if verbose:
        print(f"{n} connected ink shape(s)")

    # classify each component: low fill-ratio (relative to its own bbox) = stroke,
    # UNLESS the component also contains a genuinely thick solid sub-region
    # (a filled area sharing the exact same ink color as the outline it's
    # bordered by -- e.g. packed coffee grounds, a solid handle -- so it's
    # 8-connected into the same component as the surrounding thin outline).
    # Skeletonizing a component like that collapses the solid part down to
    # a thin ribbon at the reconstructed stroke width, which is wrong -- so
    # any component with a thick core goes to the direct vtracer fill trace
    # instead, even if its overall bbox fill-ratio reads as "thin." Direct
    # trace has proven to faithfully reproduce mixed thin-outline + solid-
    # fill content (it traces the actual silhouette, no skeleton collapse);
    # the only cost is losing the constant-width guarantee on that
    # component's thin parts.
    # A third check, alongside the two above: bbox fill-ratio alone also
    # misfires on small solid icon glyphs (a leaf, a heart, a star, a house
    # pictogram) -- any shape with sharp pointed extremities wastes a lot of
    # its own bounding box, so it can read as "thin" by fill-ratio even
    # though it's a genuine 2D blob, not a ribbon. Skeletonizing a blob like
    # that produces a branching skeleton with wildly uneven local width
    # (wide through the belly, tapering to nothing at each point), and
    # reinflating it at one uniform width mangles the shape completely --
    # unlike a true stroke (a ring, a tick mark), whose skeleton has a
    # consistent width along its whole length. Measured on this project's
    # icons: a real ring/stroke has width coefficient-of-variation (std/mean
    # of the distance-transform width sampled along the skeleton) around
    # 0.05; a solid glyph misclassified as a stroke measured 0.42. Gate on
    # this directly instead of guessing more diameter thresholds.
    # A fourth check, alongside the three above: width-CV is an average over
    # every skeleton pixel, so it can stay low even when a shape tapers
    # sharply at its own free ends (a pine needle, a ribbon tail, a leaf
    # point fused into a larger connected illustration) -- the tapering tip
    # is a tiny fraction of total skeleton pixels and barely moves the
    # aggregate statistic. Found on `advent-calendar.png`: the pine
    # needles + bow + roofline were all one 8,407-pixel connected
    # component with a CV of just 0.15 (comfortably under the 0.2 gate)
    # even though several endpoints tapered to 2-8px against a 17.9px
    # median -- reconstructing it at one constant (median) width blunted
    # every pointed tip into a rounded blob and fattened every thin
    # segment, which read as "worse, less elegant than the source" even
    # though nothing was mangled outright. See endpoint_taper_ratio().
    fill_ratios = {}
    max_thickness = {}
    width_cv = {}
    taper_ratio = {}
    for lbl in range(1, n + 1):
        comp = labeled == lbl
        ys, xs = np.where(comp)
        h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        fill_ratios[lbl] = comp.sum() / (h * w)
        max_thickness[lbl] = ndimage.distance_transform_edt(comp).max() * 2
        if fill_ratios[lbl] < stroke_fill_ratio and max_thickness[lbl] < thick_fill_diameter:
            skel = skeletonize(comp)
            dist = ndimage.distance_transform_edt(comp)
            widths = dist[skel] * 2
            width_cv[lbl] = widths.std() / widths.mean() if widths.mean() > 0 else 0.0
            taper_ratio[lbl] = endpoint_taper_ratio(skel, dist)
    targets = {lbl for lbl, fr in fill_ratios.items()
               if fr < stroke_fill_ratio and max_thickness[lbl] < thick_fill_diameter
               and width_cv.get(lbl, 0.0) < stroke_width_cv
               and taper_ratio.get(lbl, 1.0) >= endpoint_taper_min}
    if verbose:
        print(f"reconstructing as constant-width strokes: {sorted(targets) or 'none'}")

    from svgpathtools import parse_path
    import xml.etree.ElementTree as ET
    tmp_files = []

    def vtrace_mask_to_paths(mask_bool, tag):
        """Run vtracer on just this sub-mask and return every resulting path
        verbatim (transform baked in), with no attempt to attribute paths
        back to individual scipy labels.

        Matching each vtracer <path> to "the" scipy label that produced it
        (via representative_point -> nearest labeled pixel) used to be how
        this worked, tracing the *whole* mask once. That silently drops
        content whenever vtracer's own contour count for a region doesn't
        match scipy's connected-component count 1:1 -- e.g. corner-touching
        marks (dotted/stippled texture, hatching) that scipy's 8-connected
        labeling treats as one component but vtracer traces as several
        separate paths: only the last path checked for that label survived,
        the rest vanished with a "no traced shape found" warning. Tracing
        exactly the sub-mask we care about and keeping every path it
        produces sidesteps the whole attribution problem.
        """
        binary = np.full((*mask_bool.shape, 3), 255, dtype=np.uint8)
        binary[mask_bool] = ink_rgb
        binary_png = output_path.with_name(f"{output_path.stem}_{tag}_tmp.png")
        Image.fromarray(binary, "RGB").save(binary_png)
        vt_svg = output_path.with_name(f"{output_path.stem}_{tag}_vtrace_tmp.svg")
        tmp_files.extend([binary_png, vt_svg])
        vtracer.convert_image_to_svg_py(
            str(binary_png), str(vt_svg),
            colormode="binary", hierarchical="cutout", mode="spline",
            filter_speckle=filter_speckle, corner_threshold=55, length_threshold=3.5,
            splice_threshold=45, path_precision=3,
        )
        tree = ET.parse(vt_svg)
        root = tree.getroot()
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        paths = []
        for p in root.findall('.//svg:path', ns):
            d = p.get('d')
            tf = p.get('transform', '')
            m = re.match(r'translate\(([-\d.]+),\s*([-\d.]+)\)', tf)
            tx, ty = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
            paths.append(apply_transform(d, tx, ty, 1.0))
        return paths

    final_ds = []

    fill_labels = [lbl for lbl in range(1, n + 1) if lbl not in targets]
    if fill_labels:
        fill_mask = np.isin(labeled, fill_labels)
        final_ds.extend(vtrace_mask_to_paths(fill_mask, "fill"))

    for lbl in sorted(targets):
        comp = labeled == lbl
        result = reconstruct_stroke(comp)
        if result is None:
            paths = vtrace_mask_to_paths(comp, f"s{lbl}")
            if paths:
                if verbose:
                    print(f"  shape {lbl}: not a simple stroke, using direct trace")
                final_ds.extend(paths)
            elif verbose:
                print(f"  shape {lbl}: not a simple stroke and no traced fallback found — skipped")
        else:
            poly, width = result
            if verbose:
                print(f"  shape {lbl}: reconstructed at constant width {width:.2f}px")
            final_ds.append(polygon_to_path_d(poly))

    allp = parse_path(" ".join(final_ds))
    xmin, xmax, ymin, ymax = allp.bbox()
    w, h = xmax - xmin, ymax - ymin
    scale = target_size / max(w, h)
    new_w, new_h = w * scale, h * scale

    final_shapes = [apply_transform(d, -xmin, -ymin, scale) for d in final_ds]
    paths_xml = [f'  <path d="{d}" fill="{fill_hex}"/>' for d in final_shapes]
    svg_out = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{new_w:.2f}" height="{new_h:.2f}" '
        f'viewBox="0 0 {new_w:.2f} {new_h:.2f}">\n' +
        "\n".join(paths_xml) + "\n</svg>\n"
    )
    output_path.write_text(svg_out)

    for f in tmp_files:
        f.unlink(missing_ok=True)

    if verbose:
        print(f"written: {output_path}  ({new_w:.0f}x{new_h:.0f})")
    return output_path


def render_preview(svg_path, png_path=None, target_px=1200):
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    import fitz

    svg_path = Path(svg_path)
    png_path = Path(png_path) if png_path else svg_path.with_name(svg_path.stem + "_preview.png")
    pdf_path = svg_path.with_suffix(".pdf")

    drawing = svg2rlg(str(svg_path))
    renderPDF.drawToFile(drawing, str(pdf_path))
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    scale = target_px / max(page.rect.width, page.rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
    pix.save(str(png_path))
    doc.close()
    pdf_path.unlink(missing_ok=True)
    return png_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="path to the source PNG")
    ap.add_argument("--output", "-o", help="output SVG path (default: same name, .svg)")
    ap.add_argument("--fill", help="hex fill color, e.g. #361a11 (default: auto-detected from the PNG)")
    ap.add_argument("--target-size", type=float, default=500.0,
                     help="scale so the longer side is this many units (default 500, matches Canva's SVG spec)")
    ap.add_argument("--stroke-fill-ratio", type=float, default=0.45,
                     help="shapes with (ink area / bbox area) below this are treated as strokes and reconstructed at constant width (default 0.45)")
    ap.add_argument("--white-cutoff", type=int, default=235,
                     help="pixels with luminance >= this are treated as background, not ink, even if opaque -- excludes near-white shading/fill so it doesn't collapse into a solid block (default 235, 0-255 scale)")
    ap.add_argument("--filter-speckle", type=int, default=4,
                     help="vtracer's minimum shape size in pixels; small legitimate details (fine texture lines, tiny accent marks) can get dropped as noise -- lower this (e.g. 1-2) if the traced SVG is missing fine detail present in the PNG (default 4)")
    ap.add_argument("--thick-fill-diameter", type=float, default=50.0,
                     help="a connected ink component containing any point at least this many px thick (in the source PNG's native resolution) is traced directly instead of skeletonized, even if it also has thin outline parts -- catches solid fill/shading drawn in the same color as its outline (packed texture, a solid handle) so it doesn't get collapsed into a thin ribbon (default 50)")
    ap.add_argument("--stroke-width-cv", type=float, default=0.2,
                     help="a component only reconstructs as a stroke if its skeleton width is this uniform (std/mean of the distance-transform width along the skeleton) -- a real ring/tick mark measures ~0.05, a solid icon glyph (leaf, heart, star) misclassified by fill-ratio alone measures ~0.4+ since it has 2D bulk, not a constant width. Raise this if a legitimately wobbly hand-drawn stroke gets wrongly excluded (default 0.2)")
    ap.add_argument("--endpoint-taper-min", type=float, default=0.4,
                     help="a component only reconstructs as a stroke if every skeleton endpoint's width is at least this fraction of the shape's median width -- catches a pointed taper (a pine needle, a ribbon tail, a leaf point) that the aggregate width-CV check misses because the tapering tip is a tiny fraction of total skeleton pixels. Lower this if a legitimately blunt-ended stroke gets wrongly excluded (default 0.4)")
    ap.add_argument("--preview", action="store_true",
                     help="also render a PNG preview alongside the SVG (off by default)")
    args = ap.parse_args()

    out = trace_png_to_svg(
        args.input, args.output, fill_hex=args.fill,
        target_size=args.target_size, stroke_fill_ratio=args.stroke_fill_ratio,
        white_cutoff=args.white_cutoff, filter_speckle=args.filter_speckle,
        thick_fill_diameter=args.thick_fill_diameter, stroke_width_cv=args.stroke_width_cv,
        endpoint_taper_min=args.endpoint_taper_min,
    )
    if args.preview:
        preview = render_preview(out)
        print(f"preview: {preview}")


if __name__ == "__main__":
    main()
