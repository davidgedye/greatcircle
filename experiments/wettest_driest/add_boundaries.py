"""
add_boundaries.py — Augment results.json with land/water boundary points.

Streams GEBCO in horizontal strips to avoid loading the full ~3.7 GB mask.
Computes boundaries for the best coarse result and the best fine result only.

Usage:
    python3 add_boundaries.py data/GEBCO/GEBCO_2025_sub_ice.nc
    python3 add_boundaries.py data/GEBCO/GEBCO_2025_sub_ice.nc --lakes-mask data/lakes_mask.npy
"""

import argparse
import json

import netCDF4 as nc_mod
import numpy as np

from great_circles import normal_to_cartesian, great_circle_points


def water_land_boundaries_chunked(theta, phi, nc_path, lakes_path=None,
                                   n_pts=86400, strip_rows=500,
                                   suppress_lakes=False):
    """
    Compute land/water boundary crossings without loading the full mask into RAM.
    Streams the elevation file in horizontal strips (~40 MB each at default settings).

    lakes_path + suppress_lakes=True  → treat lake polygons as land (removes
      spurious transitions from Great-Lakes-style sub-sea-level lake beds).
    lakes_path + suppress_lakes=False → treat lake polygons as water (adds
      freshwater lakes to the water mask).

    Returns [[lon, lat, to_water, bearing_to_land], ...].
    """
    n_vec = normal_to_cartesian(theta, phi)
    pts = great_circle_points(n_vec, n_pts)
    lat = np.degrees(np.arcsin(np.clip(pts[:, 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))

    ds = nc_mod.Dataset(nc_path, 'r')

    if 'x_range' in ds.variables:
        # GMT grid format (ETOPO1): x_range, y_range, spacing, dimension, z
        lon_min_g = float(ds.variables['x_range'][0])
        lat_min_g = float(ds.variables['y_range'][0])
        lat_max_g = float(ds.variables['y_range'][1])
        dlon = float(ds.variables['spacing'][0])
        dlat = float(ds.variables['spacing'][1])
        nlon = int(ds.variables['dimension'][0])
        nlat = int(ds.variables['dimension'][1])
        # GMT grids store z as a flat array, top-to-bottom (lat_max→lat_min)
        # We'll treat it as ascending after flipping on read
        lat0, lon0 = lat_min_g, lon_min_g
        ascending  = False   # stored top-to-bottom; we flip strips on read
        lat_min    = lat_min_g
        dlat_abs   = dlat
        elev_var   = 'z'
        gmt_format = True
    else:
        lat_var  = next(n for n in ds.variables if n.lower() in ('lat', 'latitude'))
        lon_var  = next(n for n in ds.variables if n.lower() in ('lon', 'longitude'))
        elev_var = next(n for n in ('elevation', 'z', 'Band1', 'topo') if n in ds.variables)
        lats_g = ds.variables[lat_var][:]
        lons_g = ds.variables[lon_var][:]
        nlat, nlon = len(lats_g), len(lons_g)
        lat0 = float(lats_g[0])
        lon0 = float(lons_g[0])
        dlat = float(lats_g[1] - lats_g[0])
        dlon = float(lons_g[1] - lons_g[0])
        del lats_g, lons_g
        ascending = dlat > 0
        lat_min   = lat0 if ascending else lat0 + (nlat - 1) * dlat
        dlat_abs  = abs(dlat)
        gmt_format = False

    # Nearest-neighbour row/col for each sample point (matches map_coordinates order=0)
    lon_range = nlon * abs(dlon)
    lon_norm  = (lon - lon0) % lon_range + lon0
    row_i = np.clip(np.round((lat - lat_min) / dlat_abs), 0, nlat - 1).astype(np.int32)
    col_i = np.round((lon_norm - lon0) / abs(dlon)).astype(np.int32) % nlon

    lakes_mmap = np.load(lakes_path, mmap_mode='r') if lakes_path else None
    elev_nc    = ds.variables[elev_var]
    vals       = np.empty(n_pts, dtype=np.int8)

    for s0 in range(0, nlat, strip_rows):
        s1       = min(s0 + strip_rows, nlat)
        in_strip = (row_i >= s0) & (row_i < s1)
        if not in_strip.any():
            continue

        if gmt_format:
            # GMT z is a flat array stored top-to-bottom; ascending strip [s0,s1)
            # maps to file rows [nlat-s1, nlat-s0), reversed
            fs, fe = nlat - s1, nlat - s0
            raw = elev_nc[fs * nlon : fe * nlon].reshape(s1 - s0, nlon)[::-1]
            strip = (raw <= 0).astype(np.int8)
        elif ascending:
            strip = (elev_nc[s0:s1, :] <= 0).astype(np.int8)
            if lakes_mmap is not None:
                lk = lakes_mmap[s0:s1, :].astype(np.int8)
                if suppress_lakes:
                    strip &= ~lk
                else:
                    strip |= lk
        else:
            fs, fe = nlat - s1, nlat - s0
            strip = (elev_nc[fs:fe, :] <= 0).astype(np.int8)[::-1]
            if lakes_mmap is not None:
                lk = lakes_mmap[fs:fe, :].astype(np.int8)[::-1]
                if suppress_lakes:
                    strip &= ~lk
                else:
                    strip |= lk

        idx          = np.where(in_strip)[0]
        vals[idx]    = strip[row_i[idx] - s0, col_i[idx]]

    ds.close()

    boundaries = []
    for i in np.where(np.diff(vals) != 0)[0]:
        lo, hi = float(lon[i]), float(lon[i + 1])
        d = hi - lo
        if d > 180:    hi -= 360
        elif d < -180: hi += 360
        mid_lon  = ((lo + hi) / 2 + 180) % 360 - 180
        mid_lat  = (float(lat[i]) + float(lat[i + 1])) / 2
        to_water = int(vals[i + 1])

        la1, la2 = np.radians(lat[i]), np.radians(lat[i + 1])
        dlo      = np.radians(lon[i + 1] - lon[i])
        x        = np.sin(dlo) * np.cos(la2)
        y        = np.cos(la1) * np.sin(la2) - np.sin(la1) * np.cos(la2) * np.cos(dlo)
        fwd      = float(np.degrees(np.arctan2(x, y))) % 360
        bearing_to_land = fwd if to_water == 0 else (fwd + 180) % 360

        boundaries.append([round(mid_lon, 4), round(mid_lat, 4),
                           to_water, round(bearing_to_land, 1)])
    return boundaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data', help='Path to GEBCO/ETOPO1 NetCDF file')
    parser.add_argument('--lakes-mask', metavar='PATH')
    parser.add_argument('--pts', type=int, default=86400,
                        help='Sample points per circle (default 86400)')
    parser.add_argument('--strip-rows', type=int, default=500,
                        help='GEBCO rows per strip (default 500, ~40 MB each)')
    parser.add_argument('--results', default='results.json')
    args = parser.parse_args()

    with open(args.results) as f:
        results = json.load(f)

    for key, exp in results.items():
        needs_lakes = key.endswith('-lakes')
        if needs_lakes and args.lakes_mask is None:
            print(f'Skipping {key} — no --lakes-mask provided')
            continue
        # For non-lakes experiments with a mask available: suppress sub-sea-level
        # lake beds (e.g. Great Lakes) that GEBCO would otherwise classify as water.
        suppress = (not needs_lakes) and (args.lakes_mask is not None)
        lakes_path = args.lakes_mask  # None if not provided

        coarse = exp['coarse']
        coarse_boundaries = []
        for rank, (theta_deg, phi_deg, _) in enumerate(coarse):
            print(f'\n{key}: coarse #{rank+1} ({theta_deg:.3f}°, {phi_deg:.3f}°) ...', flush=True)
            pts = water_land_boundaries_chunked(
                np.radians(theta_deg), np.radians(phi_deg),
                args.data, lakes_path, args.pts, args.strip_rows,
                suppress_lakes=suppress)
            coarse_boundaries.append(pts)
            print(f'  {len(pts)} boundary points')
        exp['coarse_boundaries'] = coarse_boundaries

        if 'fine' in exp and exp['fine']:
            best = exp['fine'][0]
            t = best['theta_center_deg'] + best['offsets_deg'][best['best_i']]
            p = best['phi_center_deg']   + best['offsets_deg'][best['best_j']]
            print(f'  fine best ({t:.3f}°, {p:.3f}°) ...', flush=True)
            pts = water_land_boundaries_chunked(
                np.radians(t), np.radians(p),
                args.data, lakes_path, args.pts, args.strip_rows,
                suppress_lakes=suppress)
            best['boundaries'] = pts
            print(f'  {len(pts)} boundary points')

    with open(args.results, 'w') as f:
        json.dump(results, f)
    print(f'\nUpdated {args.results}')


if __name__ == '__main__':
    main()
