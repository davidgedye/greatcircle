"""
compare_datasets.py — Cross-evaluate top-10 candidates between two elevation datasets.

For each dataset:
  1. Loads its top-10 + fine results (runs the search if no results file is provided).
  2. Re-evaluates every candidate against the *other* mask.
  3. Prints a side-by-side comparison table.

Usage:
    python3 compare_datasets.py \\
        data/ETOPO1_Ice_c_gdal.grd  data/GEBCO/GEBCO_2025_sub_ice.nc \\
        --label-a ETOPO1  --label-b GEBCO \\
        --results-a etopo1.json  --results-b results.json

    # Let the script run both searches from scratch:
    python3 compare_datasets.py A.nc B.nc --workers 8 --pts 3600
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np

from great_circles import (
    load_water_mask,
    normal_to_cartesian,
    great_circle_points,
    sample_ocean_fraction,
    coarse_search,
    fine_search,
    _worker_init,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_search(mask, grid, args, label):
    """Run coarse + fine search and return a results dict matching results.json format."""
    print(f"\n{'='*60}")
    print(f"  Searching {label} ...")
    print(f"{'='*60}")

    results = coarse_search(mask, grid,
                            n_grid=args.grid, n_pts=args.pts, workers=args.workers)

    top_wet = results[:args.top]
    top_dry = list(reversed(results[-args.top:]))

    def _deg(r): return [[round(np.degrees(t), 4), round(np.degrees(p), 4), round(f, 5)]
                          for f, t, p in r]

    out = {
        "wettest": {"coarse": _deg(top_wet)},
        "driest":  {"coarse": _deg(top_dry)},
    }

    if not args.no_fine:
        _worker_init(mask, grid)
        fine_wet, grids_wet = fine_search(mask, grid, top_wet, minimize=False,
                                          n_pts=args.pts, workers=args.workers)
        fine_dry, grids_dry = fine_search(mask, grid, top_dry, minimize=True,
                                          n_pts=args.pts, workers=args.workers)
        out["wettest"]["fine"] = grids_wet
        out["driest"]["fine"]  = grids_dry

    return out


def load_or_run(path, mask, grid, args, label):
    if path and os.path.exists(path):
        print(f"Loading {label} results from {path} ...")
        with open(path) as f:
            return json.load(f)
    print(f"No results file for {label} — running search ...")
    results = run_search(mask, grid, args, label)
    if path:
        with open(path, "w") as f:
            json.dump(results, f)
        print(f"Saved to {path}")
    return results


def candidates_from(exp):
    """Return list of (theta_rad, phi_rad, label) for coarse + fine best."""
    rows = []
    for i, (td, pd, _) in enumerate(exp["coarse"]):
        rows.append((np.radians(td), np.radians(pd), f"coarse #{i+1}"))
    if "fine" in exp and exp["fine"]:
        g = exp["fine"][0]
        td = g["theta_center_deg"] + g["offsets_deg"][g["best_i"]]
        pd = g["phi_center_deg"]   + g["offsets_deg"][g["best_j"]]
        rows.append((np.radians(td), np.radians(pd), "fine best"))
    return rows


def evaluate(theta, phi, mask, grid, n_pts):
    n   = normal_to_cartesian(theta, phi)
    pts = great_circle_points(n, n_pts)
    return sample_ocean_fraction(pts, mask, grid)


# ── Table printing ────────────────────────────────────────────────────────────

def print_table(title, candidates,
                own_label, own_mask, own_grid, own_pts,
                cross_label, cross_mask, cross_grid, cross_pts,
                invert=False):
    """
    Evaluate every candidate in both masks and print a comparison table.
    Uses own_pts when evaluating against the own mask, cross_pts for the cross mask.
    invert=True shows land % (for driest).
    """
    unit = "land" if invert else "ocean"

    def fmt(frac):
        v = (1 - frac) if invert else frac
        return f"{v*100:6.2f}%"

    print(f"\n  {title}")
    print(f"  {'Label':<14} {'Theta°':>8} {'Phi°':>8}  "
          f"{own_label:>8}  {cross_label:>8}  {'Δ (pp)':>8}")
    print("  " + "-" * 66)

    for theta, phi, label in candidates:
        own_frac   = evaluate(theta, phi, own_mask,   own_grid,   own_pts)
        cross_frac = evaluate(theta, phi, cross_mask, cross_grid, cross_pts)
        own_v   = (1 - own_frac)   if invert else own_frac
        cross_v = (1 - cross_frac) if invert else cross_frac
        delta   = (cross_v - own_v) * 100
        sep = " ┄" if label == "fine best" else "  "
        print(f"{sep} {label:<14} {np.degrees(theta):>8.3f} {np.degrees(phi):>8.3f}"
              f"  {fmt(own_frac)}  {fmt(cross_frac)}  {delta:>+7.2f}pp")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("data_a",  help="Elevation file A (e.g. ETOPO1)")
    p.add_argument("data_b",  help="Elevation file B (e.g. GEBCO)")
    p.add_argument("--label-a",    default="A")
    p.add_argument("--label-b",    default="B")
    p.add_argument("--results-a",  metavar="PATH", help="Pre-computed results JSON for A")
    p.add_argument("--results-b",  metavar="PATH", help="Pre-computed results JSON for B")
    p.add_argument("--grid",    type=int, default=180)
    p.add_argument("--pts",     type=int, default=None,
                   help="Sample points per circle (default: derived from each dataset's nlon)")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--top",     type=int, default=10)
    p.add_argument("--no-fine", action="store_true")
    args = p.parse_args()

    print(f"Loading {args.label_a}: {args.data_a}")
    mask_a, grid_a = load_water_mask(args.data_a)
    print(f"Loading {args.label_b}: {args.data_b}")
    mask_b, grid_b = load_water_mask(args.data_b)

    # Default pts: use each dataset's nlon so no cell is skipped.
    # For cross-evaluation we use the target mask's nlon.
    pts_a = args.pts or grid_a["nlon"]
    pts_b = args.pts or grid_b["nlon"]
    print(f"\nSample points: {args.label_a}={pts_a} ({pts_a/grid_a['nlon']:.1f}x), "
          f"{args.label_b}={pts_b} ({pts_b/grid_b['nlon']:.1f}x)")

    # Use pts_a for search on A, pts_b for search on B
    args.pts = pts_a
    res_a = load_or_run(args.results_a, mask_a, grid_a, args, args.label_a)
    args.pts = pts_b
    res_b = load_or_run(args.results_b, mask_b, grid_b, args, args.label_b)

    for key, invert in [("wettest", False), ("driest", True)]:
        exp_a = res_a.get(key) or res_a.get(f"{key}-lakes")
        exp_b = res_b.get(key) or res_b.get(f"{key}-lakes")
        if not exp_a or not exp_b:
            continue

        bar = "═" * 64
        print(f"\n{bar}")
        print(f"  {key.upper()}")
        print(bar)

        # When evaluating A candidates in B mask, use pts_b (don't skip B cells)
        # When evaluating B candidates in A mask, use pts_a
        print_table(
            f"{args.label_a} candidates evaluated in both datasets",
            candidates_from(exp_a),
            args.label_a, mask_a, grid_a, pts_a,
            args.label_b, mask_b, grid_b, pts_b,
            invert=invert,
        )
        print_table(
            f"{args.label_b} candidates evaluated in both datasets",
            candidates_from(exp_b),
            args.label_b, mask_b, grid_b, pts_b,
            args.label_a, mask_a, grid_a, pts_a,
            invert=invert,
        )

    print()


if __name__ == "__main__":
    main()
