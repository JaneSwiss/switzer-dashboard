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
    Returns None if the skeleton has a branch point (not a simple path/loop)."""
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
    if any(d >= 3 for d in deg.values()):
        return None  # branch point -> not a simple stroke, caller falls back

    endpoints = [p for p, d in deg.items() if d == 1]
    visited = set()
    paths = []

    def walk(start, first_next):
        path = [start, first_next]
        visited.add(start)
        visited.add(first_next)
        prev, cur = start, first_next
        while True:
            nbrs = [q for q in neighbors(cur) if q != prev]
            nbrs = [q for q in nbrs if q not in visited or q == path[0]]
            if not nbrs:
                break
            nxt = nbrs[0]
            path.append(nxt)
            if nxt == path[0]:
                break
            visited.add(nxt)
            prev, cur = cur, nxt
        return path

    if endpoints:
        for e in endpoints:
            if e in visited:
                continue
            nbrs = [q for q in neighbors(e) if q not in visited]
            if nbrs:
                paths.append(walk(e, nbrs[0]))
    else:
        start = next(iter(pts))
        nbrs = neighbors(start)
        if len(nbrs) != 2:
            return None
        paths.append(walk(start, nbrs[0]))

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
                      verbose=True):
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
    binary = np.full((*mask.shape, 3), 255, dtype=np.uint8)
    binary[mask] = ink_rgb
    binary_png = output_path.with_name(output_path.stem + "_binary_tmp.png")
    Image.fromarray(binary, "RGB").save(binary_png)

    labeled, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if verbose:
        print(f"{n} connected ink shape(s)")

    # classify each component: low fill-ratio (relative to its own bbox) = stroke
    fill_ratios = {}
    for lbl in range(1, n + 1):
        comp = labeled == lbl
        ys, xs = np.where(comp)
        h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        fill_ratios[lbl] = comp.sum() / (h * w)
    targets = {lbl for lbl, fr in fill_ratios.items() if fr < stroke_fill_ratio}
    if verbose:
        print(f"reconstructing as constant-width strokes: {sorted(targets) or 'none'}")

    # vtracer direct trace (true binary hole handling) for the fallback/fill shapes
    vt_svg = output_path.with_name(output_path.stem + "_vtrace_tmp.svg")
    vtracer.convert_image_to_svg_py(
        str(binary_png), str(vt_svg),
        colormode="binary", hierarchical="cutout", mode="spline",
        filter_speckle=filter_speckle, corner_threshold=55, length_threshold=3.5,
        splice_threshold=45, path_precision=3,
    )

    import xml.etree.ElementTree as ET
    tree = ET.parse(vt_svg)
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    from svgpathtools import parse_path
    from shapely.geometry import Polygon as ShapelyPolygon

    def path_to_shapely(abs_d):
        """Sample a (possibly multi-subpath) bezier path into a shapely
        polygon, exterior + holes, for a reliable interior point."""
        try:
            p = parse_path(abs_d)
        except Exception:
            return None
        rings = []
        for sub in p.continuous_subpaths():
            pts = []
            for seg in sub:
                pts.append((seg.start.real, seg.start.imag))
                n_samples = 1 if type(seg).__name__ == 'Line' else 8
                for i in range(1, n_samples):
                    c = seg.point(i / n_samples)
                    pts.append((c.real, c.imag))
            if len(pts) >= 3:
                rings.append(pts)
        if not rings:
            return None
        areas = [abs(ShapelyPolygon(r).area) for r in rings]
        ext = rings[areas.index(max(areas))]
        holes = [r for r, a in zip(rings, areas) if r is not ext]
        try:
            return ShapelyPolygon(ext, holes)
        except Exception:
            return ShapelyPolygon(ext)

    def label_at(cx, cy, search_radius=25):
        yi, xi = int(round(cy)), int(round(cx))
        h, w = labeled.shape
        for r in range(search_radius):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    y, x = yi + dy, xi + dx
                    if 0 <= y < h and 0 <= x < w and labeled[y, x] != 0:
                        return int(labeled[y, x])
        return None

    shape_by_label = {}
    unmatched = []
    for p in root.findall('.//svg:path', ns):
        d = p.get('d')
        tf = p.get('transform', '')
        m = re.match(r'translate\(([-\d.]+),\s*([-\d.]+)\)', tf)
        tx, ty = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
        abs_d = apply_transform(d, tx, ty, 1.0)

        poly = path_to_shapely(abs_d)
        lbl = None
        if poly is not None and not poly.is_empty:
            try:
                rp = poly.representative_point()
                lbl = label_at(rp.x, rp.y)
            except Exception:
                lbl = None
        if lbl is None:
            unmatched.append(abs_d)
        else:
            shape_by_label[lbl] = abs_d

    missing = [lbl for lbl in range(1, n + 1) if lbl not in shape_by_label]
    if missing and unmatched:
        # last resort: pair any remaining unmatched shapes with any remaining
        # unfilled labels by nearest centroid, so nothing silently vanishes
        centroids = ndimage.center_of_mass(mask, labeled, missing)
        for abs_d in unmatched:
            try:
                bx = parse_path(abs_d).bbox()
            except Exception:
                continue  # degenerate/empty path (can happen at very low filter_speckle) -- skip it
            cx, cy = (bx[0] + bx[1]) / 2, (bx[2] + bx[3]) / 2
            best, bestd = None, 1e18
            for lbl, (ry, rx) in zip(missing, centroids):
                if lbl in shape_by_label:
                    continue
                d2 = (rx - cx) ** 2 + (ry - cy) ** 2
                if d2 < bestd:
                    bestd, best = d2, lbl
            if best is not None:
                shape_by_label[best] = abs_d
    if verbose:
        still_missing = [lbl for lbl in range(1, n + 1) if lbl not in shape_by_label]
        if still_missing:
            print(f"  warning: no traced shape found for label(s) {still_missing}")

    final_ds = []
    for lbl in range(1, n + 1):
        if lbl in targets:
            comp = labeled == lbl
            result = reconstruct_stroke(comp)
            if result is None:
                if lbl in shape_by_label:
                    if verbose:
                        print(f"  shape {lbl}: not a simple stroke, using direct trace")
                    final_ds.append(shape_by_label[lbl])
                else:
                    if verbose:
                        print(f"  shape {lbl}: not a simple stroke and no traced fallback found — skipped")
            else:
                poly, width = result
                if verbose:
                    print(f"  shape {lbl}: reconstructed at constant width {width:.2f}px")
                final_ds.append(polygon_to_path_d(poly))
        elif lbl in shape_by_label:
            final_ds.append(shape_by_label[lbl])
        elif verbose:
            print(f"  shape {lbl}: no traced shape found — skipped")

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

    binary_png.unlink(missing_ok=True)
    vt_svg.unlink(missing_ok=True)
    pdf_tmp = vt_svg.with_suffix(".pdf")
    pdf_tmp.unlink(missing_ok=True)

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
    ap.add_argument("--preview", action="store_true",
                     help="also render a PNG preview alongside the SVG (off by default)")
    args = ap.parse_args()

    out = trace_png_to_svg(
        args.input, args.output, fill_hex=args.fill,
        target_size=args.target_size, stroke_fill_ratio=args.stroke_fill_ratio,
        white_cutoff=args.white_cutoff, filter_speckle=args.filter_speckle,
    )
    if args.preview:
        preview = render_preview(out)
        print(f"preview: {preview}")


if __name__ == "__main__":
    main()
