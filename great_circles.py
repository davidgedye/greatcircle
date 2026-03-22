"""
great_circles.py — Find the wettest and driest great circles on Earth.

A great circle is parameterised by its plane normal vector n, represented as
(theta, phi) in spherical coordinates:
  theta  (colatitude) in [0, pi]
  phi    (longitude)  in [0, pi)   — antipodal symmetry halves the range

Usage:
  python great_circles.py ETOPO1_Ice_c_gdal.grd
  python great_circles.py ETOPO1_Ice_c_gdal.grd --workers 8
  python great_circles.py ETOPO1_Ice_c_gdal.grd --no-fine
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import netCDF4 as nc
import numpy as np
from scipy.ndimage import map_coordinates


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_water_mask(path: str) -> tuple[np.ndarray, dict]:
    """Load ETOPO1/GEBCO NetCDF and return a boolean water mask + grid metadata."""
    print(f"Loading {path} ...")
    t0 = time.time()

    ds = nc.Dataset(path, "r")

    # Support both standard lat/lon NetCDF (GEBCO) and GMT grid format (ETOPO1 GDAL)
    if "x_range" in ds.variables:
        # GMT grid format: x_range, y_range, spacing, dimension, z (flat array)
        lon_min, lon_max = float(ds.variables["x_range"][0]), float(ds.variables["x_range"][1])
        lat_min, lat_max = float(ds.variables["y_range"][0]), float(ds.variables["y_range"][1])
        dlon, dlat = float(ds.variables["spacing"][0]), float(ds.variables["spacing"][1])
        nlon, nlat = int(ds.variables["dimension"][0]), int(ds.variables["dimension"][1])

        print(f"  GMT grid format detected")
        print(f"  Lat range: {lat_min:.2f} to {lat_max:.2f}  (n={nlat})")
        print(f"  Lon range: {lon_min:.2f} to {lon_max:.2f}  (n={nlon})")

        print("  Reading elevation array ...")
        z_flat = ds.variables["z"][:]
        ds.close()

        # GMT grids are stored row-major from top (lat_max) to bottom (lat_min)
        elevation = z_flat.reshape(nlat, nlon)
        del z_flat
        is_water = (elevation <= 0).astype(np.int8)
        del elevation
        # Flip to ascending lat order
        is_water = is_water[::-1, :]

    else:
        # Standard NetCDF (GEBCO): explicit lat/lon coordinate variables
        elev_var = next((n for n in ("elevation", "z", "Band1", "topo") if n in ds.variables), None)
        if elev_var is None:
            raise ValueError(f"Cannot find elevation variable. Available: {list(ds.variables)}")
        lat_var = next((n for n in ds.variables if n.lower() in ("lat", "latitude")), None)
        lon_var = next((n for n in ds.variables if n.lower() in ("lon", "longitude")), None)
        if lat_var is None or lon_var is None:
            raise ValueError(f"Cannot find lat/lon variables. Available: {list(ds.variables)}")

        lats = ds.variables[lat_var][:]
        lons = ds.variables[lon_var][:]
        nlat, nlon = len(lats), len(lons)
        print(f"  Elevation variable: '{elev_var}'")
        print(f"  Lat range: {lats[0]:.2f} to {lats[-1]:.2f}  (n={nlat})")
        print(f"  Lon range: {lons[0]:.2f} to {lons[-1]:.2f}  (n={nlon})")

        # Read elevation in row-chunks to avoid holding the full array in RAM
        # alongside the mask (GEBCO int16 = ~7.5 GB; int8 mask = ~3.7 GB).
        chunk_rows = 1000
        print(f"  Building water mask in chunks of {chunk_rows} rows ...")
        is_water = np.empty((nlat, nlon), dtype=np.int8)
        elev_var_nc = ds.variables[elev_var]
        for i in range(0, nlat, chunk_rows):
            j = min(i + chunk_rows, nlat)
            is_water[i:j, :] = (elev_var_nc[i:j, :] <= 0).astype(np.int8)
            if (i // chunk_rows) % 10 == 0:
                print(f"    {j}/{nlat} rows ...", flush=True)
        ds.close()

        lat_min, lat_max = float(lats[0]), float(lats[-1])
        lon_min, lon_max = float(lons[0]), float(lons[-1])
        dlat = float(lats[1] - lats[0])
        dlon = float(lons[1] - lons[0])
        if lat_min > lat_max:
            is_water = is_water[::-1, :]
            lat_min, lat_max = lat_max, lat_min
            dlat = -dlat

    grid = dict(
        nlat=nlat,
        nlon=nlon,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        dlat=dlat,
        dlon=dlon,
    )

    water_frac = float(is_water.mean())
    print(f"  Grid: {nlat} x {nlon}, global water fraction = {water_frac:.3f}")
    print(f"  Loaded in {time.time()-t0:.1f}s")
    return is_water, grid


# ---------------------------------------------------------------------------
# Great circle geometry
# ---------------------------------------------------------------------------

def normal_to_cartesian(theta: float, phi: float) -> np.ndarray:
    """Convert (theta, phi) in radians to unit normal vector."""
    return np.array([
        np.sin(theta) * np.cos(phi),
        np.sin(theta) * np.sin(phi),
        np.cos(theta),
    ])


def great_circle_points(n: np.ndarray, n_pts: int = 3600) -> np.ndarray:
    """
    Return n_pts unit vectors evenly spaced along the great circle
    whose plane has normal vector n.  Shape: (n_pts, 3).
    """
    # Find a vector not nearly parallel to n
    if abs(n[0]) < 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    else:
        ref = np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)  # already unit length

    t = np.linspace(0.0, 2.0 * np.pi, n_pts, endpoint=False)
    # (n_pts, 3)
    return np.outer(np.cos(t), u) + np.outer(np.sin(t), v)


def sample_ocean_fraction(pts: np.ndarray, mask: np.ndarray, grid: dict) -> float:
    """
    Given (n_pts, 3) Cartesian unit vectors, look up each point in the
    water mask and return the fraction that are ocean/water.
    """
    # Convert to lat/lon degrees
    lat = np.degrees(np.arcsin(np.clip(pts[:, 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))

    # Normalise lon to [lon_min, lon_max)
    lon_range = grid["lon_max"] - grid["lon_min"]
    lon = (lon - grid["lon_min"]) % lon_range + grid["lon_min"]

    # Fractional row/col indices
    row = (lat - grid["lat_min"]) / grid["dlat"]
    col = (lon - grid["lon_min"]) / grid["dlon"]

    # Clamp rows to valid range (poles don't wrap)
    row = np.clip(row, 0, grid["nlat"] - 1)

    # Nearest-neighbour lookup (order=0) — correct for a binary mask
    # mode='wrap' handles longitude wraparound
    vals = map_coordinates(mask, [row, col], order=0, mode="wrap")
    return float(vals.mean())


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

# Global variables used by worker processes (set via initializer)
_worker_mask = None
_worker_grid = None


def _worker_init(mask: np.ndarray, grid: dict):
    """Initializer: store mask and grid as globals in each worker process."""
    global _worker_mask, _worker_grid
    _worker_mask = mask
    _worker_grid = grid


def _eval_row(args):
    """Worker function: evaluate all phi values for a given theta."""
    theta, phi_vals, n_pts = args
    mask = _worker_mask
    grid = _worker_grid
    results = []
    for phi in phi_vals:
        n = normal_to_cartesian(theta, phi)
        pts = great_circle_points(n, n_pts)
        frac = sample_ocean_fraction(pts, mask, grid)
        results.append((frac, float(theta), float(phi)))
    return results


def coarse_search(
    mask: np.ndarray,
    grid: dict,
    n_grid: int = 180,
    n_pts: int = 3600,
    workers: int = 1,
) -> list[tuple[float, float, float]]:
    """
    Brute-force grid search over (theta, phi).
    Theta sampled uniformly in cos(theta) for equal solid-angle coverage.
    Returns list of (ocean_fraction, theta_rad, phi_rad) sorted descending.
    """
    cos_theta = np.linspace(-1.0, 1.0, n_grid)
    theta_vals = np.arccos(cos_theta)
    phi_vals = np.linspace(0.0, np.pi, n_grid, endpoint=False)

    total = n_grid * n_grid
    print(f"\nCoarse search: {n_grid}x{n_grid} = {total:,} circles, "
          f"{n_pts} pts each, {workers} worker(s) ...")
    t0 = time.time()

    job_args = [(theta, phi_vals, n_pts) for theta in theta_vals]
    all_results = []

    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(mask, grid),
        ) as ex:
            futures = {ex.submit(_eval_row, a): i for i, a in enumerate(job_args)}
            done = 0
            for fut in as_completed(futures):
                all_results.extend(fut.result())
                done += 1
                if done % 20 == 0 or done == n_grid:
                    elapsed = time.time() - t0
                    eta = elapsed / done * (n_grid - done)
                    print(f"  {done}/{n_grid} rows done  "
                          f"({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)")
    else:
        # Single-threaded: set globals directly
        _worker_init(mask, grid)
        for i, args in enumerate(job_args):
            all_results.extend(_eval_row(args))
            if (i + 1) % 20 == 0 or i + 1 == n_grid:
                elapsed = time.time() - t0
                eta = elapsed / (i + 1) * (n_grid - i - 1)
                print(f"  {i+1}/{n_grid} rows done  "
                      f"({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)")

    all_results.sort(key=lambda x: x[0], reverse=True)
    print(f"Coarse search done in {time.time()-t0:.1f}s")
    return all_results


def _eval_fine_candidate(args):
    """Worker: evaluate the full fine grid for one candidate."""
    theta0, phi0, frac0, offsets, n_pts, minimize, offsets_deg = args
    mask = _worker_mask
    grid = _worker_grid
    steps = len(offsets)

    best = (frac0, theta0, phi0)
    best_i, best_j = 0, 0
    surface = np.zeros((steps, steps))
    for i, dt in enumerate(offsets):
        theta = np.clip(theta0 + dt, 0.0, np.pi)
        for j, dp in enumerate(offsets):
            phi = (phi0 + dp) % np.pi
            n = normal_to_cartesian(theta, phi)
            pts = great_circle_points(n, n_pts)
            frac = sample_ocean_fraction(pts, mask, grid)
            surface[i, j] = frac
            if (minimize and frac < best[0]) or (not minimize and frac > best[0]):
                best = (frac, theta, phi)
                best_i, best_j = i, j

    grid_info = {
        "theta_center_deg": round(np.degrees(theta0), 4),
        "phi_center_deg":   round(np.degrees(phi0), 4),
        "offsets_deg":      [round(x, 4) for x in offsets_deg],
        "grid":             [[round(v, 5) for v in row] for row in surface.tolist()],
        "best_frac":        round(best[0], 5),
        "best_i":           best_i,
        "best_j":           best_j,
    }
    return best, grid_info


def fine_search(
    mask: np.ndarray,
    grid: dict,
    candidates: list[tuple[float, float, float]],
    window_deg: float = 2.0,
    step_deg: float = 0.05,
    n_pts: int = 3600,
    minimize: bool = False,
    workers: int = 1,
) -> tuple[list, list]:
    """Fine grid search around each candidate (theta, phi).
    Set minimize=True when refining driest candidates.
    Returns (results, grids) where grids contains the full search surface per candidate."""
    window = np.radians(window_deg)
    step = np.radians(step_deg)
    steps = int(2 * window / step)
    offsets = np.linspace(-window, window, steps)
    offsets_deg = np.degrees(offsets).tolist()

    direction = "min" if minimize else "max"
    print(f"\nFine search ({direction}): {len(candidates)} candidates, "
          f"±{window_deg}° window at {step_deg}° steps ({steps}x{steps} each), "
          f"{workers} worker(s) ...")
    t0 = time.time()

    job_args = [
        (theta0, phi0, frac0, offsets, n_pts, minimize, offsets_deg)
        for frac0, theta0, phi0 in candidates
    ]

    results_and_grids = [None] * len(candidates)
    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(mask, grid),
        ) as ex:
            futures = {ex.submit(_eval_fine_candidate, a): i for i, a in enumerate(job_args)}
            for fut in as_completed(futures):
                i = futures[fut]
                results_and_grids[i] = fut.result()
                print(f"  Candidate {i+1}/{len(candidates)}: {results_and_grids[i][0][0]:.4f}")
    else:
        _worker_init(mask, grid)
        for i, args in enumerate(job_args):
            results_and_grids[i] = _eval_fine_candidate(args)
            print(f"  Candidate {i+1}/{len(candidates)}: {results_and_grids[i][0][0]:.4f}")

    paired = sorted(results_and_grids, key=lambda x: x[0][0], reverse=not minimize)
    all_results = [r for r, _ in paired]
    all_grids   = [g for _, g in paired]
    print(f"Fine search done in {time.time()-t0:.1f}s")
    return all_results, all_grids


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def equatorial_crossings(theta: float, phi: float) -> tuple[tuple, tuple]:
    """
    Return the two antipodal points where the great circle crosses the equator,
    as (lat, lon) pairs in degrees.  These are the points with z=0 on the circle.
    """
    n = normal_to_cartesian(theta, phi)
    if abs(n[0]) < 0.9:
        ref = np.array([1.0, 0.0, 0.0])
    else:
        ref = np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref); u /= np.linalg.norm(u)
    v = np.cross(n, u)

    # z = cos(t)*u[2] + sin(t)*v[2] = 0  =>  t = atan2(-u[2], v[2])
    t0 = np.arctan2(-u[2], v[2])
    def pt(t):
        p = np.cos(t) * u + np.sin(t) * v
        return (np.degrees(np.arcsin(np.clip(p[2], -1, 1))),
                np.degrees(np.arctan2(p[1], p[0])))

    return pt(t0), pt(t0 + np.pi)


def report(results: list[tuple[float, float, float]], label: str, top_n: int = 10):
    print(f"\n{'='*70}")
    print(f"  {label}  (top {top_n})")
    print(f"{'='*70}")
    print(f"{'Rank':>4}  {'Ocean%':>7}  {'Theta°':>8}  {'Phi°':>8}  "
          f"{'Normal (nx,ny,nz)':>28}  Equatorial crossings")
    print("-" * 100)
    for rank, (frac, theta, phi) in enumerate(results[:top_n], 1):
        n = normal_to_cartesian(theta, phi)
        p1, p2 = equatorial_crossings(theta, phi)
        print(f"{rank:>4}  {frac*100:>6.2f}%  "
              f"{np.degrees(theta):>8.3f}  {np.degrees(phi):>8.3f}  "
              f"({n[0]:+.3f},{n[1]:+.3f},{n[2]:+.3f})  "
              f"({p1[0]:+.1f},{p1[1]:+.1f}) / ({p2[0]:+.1f},{p2[1]:+.1f})")


# ---------------------------------------------------------------------------
# Sanity check
# ---------------------------------------------------------------------------

def sanity_check(mask: np.ndarray, grid: dict):
    """Quick check: the equator should be ~71% ocean."""
    n = normal_to_cartesian(np.pi / 2, 0.0)  # theta=90°, phi=0° → equator
    pts = great_circle_points(n)
    frac = sample_ocean_fraction(pts, mask, grid)
    print(f"\nSanity check — equator ocean fraction: {frac:.3f}  (expect ~0.71)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Find wettest/driest great circles.")
    parser.add_argument("data", help="Path to ETOPO1/GEBCO NetCDF file")
    parser.add_argument("--grid", type=int, default=180,
                        help="Grid size N (NxN search, default 180)")
    parser.add_argument("--pts", type=int, default=3600,
                        help="Sample points per circle (default 3600)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers (default 1)")
    parser.add_argument("--no-fine", action="store_true",
                        help="Skip fine zoom search")
    parser.add_argument("--top", type=int, default=10,
                        help="Number of top results to show (default 10)")
    args = parser.parse_args()

    mask, grid = load_water_mask(args.data)
    sanity_check(mask, grid)

    results = coarse_search(mask, grid,
                            n_grid=args.grid,
                            n_pts=args.pts,
                            workers=args.workers)

    report(results, "WETTEST GREAT CIRCLES (coarse)", top_n=args.top)
    report(list(reversed(results)), "DRIEST GREAT CIRCLES (coarse)", top_n=args.top)

    import json as _json

    def _deg(rad_results):
        return [[round(np.degrees(t), 4), round(np.degrees(p), 4), round(f, 5)]
                for f, t, p in rad_results]

    output = {
        "wettest": {"coarse": _deg(results[:10])},
        "driest":  {"coarse": _deg(reversed(results[-10:]))},
    }

    if not args.no_fine:
        top_wet = results[:10]
        top_dry = results[-10:]
        fine_wet, grids_wet = fine_search(mask, grid, top_wet, minimize=False, n_pts=args.pts, workers=args.workers)
        fine_dry, grids_dry = fine_search(mask, grid, top_dry, minimize=True,  n_pts=args.pts, workers=args.workers)
        report(fine_wet, "WETTEST GREAT CIRCLES (fine)", top_n=5)
        report(fine_dry, "DRIEST GREAT CIRCLES (fine)", top_n=5)
        output["wettest"]["fine"] = grids_wet
        output["driest"]["fine"]  = grids_dry

    with open("results.json", "w") as f:
        _json.dump(output, f)
    print("\nResults saved to results.json")


if __name__ == "__main__":
    main()
