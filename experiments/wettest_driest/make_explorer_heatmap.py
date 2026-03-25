"""
make_explorer_heatmap.py — Precompute a global pole-space ocean-fraction heatmap.

For each cell on a 5 arc-minute pole-position grid, computes the ocean fraction
of the corresponding great circle using the precomputed binary land mask.

Output:
  explorer/heatmap_5m.npy  — float32 (2160, 4320), row 0 = 90°S pole lat
  explorer/heatmap_5m.png  — uint8 RGBA, row 0 = 90°N (for Mapbox image overlay)

Prerequisites:
  Run make_binary_mask.py first to produce explorer/mask_60s.bin.gz.

Usage:
    cd experiments/wettest_driest
    python3 make_explorer_heatmap.py \\
        --mask ../../explorer/mask_60s.bin.gz \\
        --workers 8
"""

import argparse
import gzip
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MASK = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'explorer', 'mask_60s.bin.gz'))
DEFAULT_OUT  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'explorer', 'heatmap_5m.npy'))
DEFAULT_PNG  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'explorer', 'heatmap_5m.png'))

POLE_RES   = 5 / 60      # 5 arc-minute in degrees
N_POLE_LAT = 2160        # rows  (180° / POLE_RES)
N_POLE_LON = 4320        # cols  (360° / POLE_RES)
N_SAMPLES  = 360         # great circle sample points (1° path spacing)
MASK_NLAT  = 10800
MASK_NLON  = 21600

# Shared state for worker processes
_mask = None


def _worker_init(mask_path):
    """Load and unpack the binary mask into each worker process."""
    global _mask
    with gzip.open(mask_path, 'rb') as f:
        data = np.frombuffer(f.read(), dtype=np.uint8)
    _mask = np.unpackbits(data).reshape(MASK_NLAT, MASK_NLON)


def _compute_row(row_idx):
    """
    Compute ocean fractions for all N_POLE_LON poles at a fixed pole latitude.
    Returns (row_idx, fracs) where fracs is shape (N_POLE_LON,).
    """
    pole_lat = -90.0 + (row_idx + 0.5) * POLE_RES
    pole_lons = -180.0 + (np.arange(N_POLE_LON) + 0.5) * POLE_RES

    pole_lat_rad  = np.radians(pole_lat)
    pole_lons_rad = np.radians(pole_lons)

    cos_lat = np.cos(pole_lat_rad)
    sin_lat = np.sin(pole_lat_rad)
    nx = cos_lat * np.cos(pole_lons_rad)   # (N,)
    ny = cos_lat * np.sin(pole_lons_rad)   # (N,)
    nz = np.full(N_POLE_LON, sin_lat)      # (N,)
    normals = np.stack([nx, ny, nz], axis=1)  # (N, 3)

    # Gram-Schmidt: choose ref perpendicular to each normal
    use_x = np.abs(normals[:, 0]) < 0.9
    ref = np.zeros((N_POLE_LON, 3))
    ref[use_x,  0] = 1.0   # [1,0,0]
    ref[~use_x, 1] = 1.0   # [0,1,0]

    u = np.cross(normals, ref)                          # (N, 3)
    u /= np.linalg.norm(u, axis=1, keepdims=True)       # normalise
    v = np.cross(normals, u)                            # (N, 3), already unit

    t = np.linspace(0.0, 2.0 * np.pi, N_SAMPLES, endpoint=False)
    cos_t = np.cos(t)   # (S,)
    sin_t = np.sin(t)   # (S,)

    # pts[i, j] = cos_t[j]*u[i] + sin_t[j]*v[i]  → shape (N, S, 3)
    pts = (cos_t[None, :, None] * u[:, None, :] +
           sin_t[None, :, None] * v[:, None, :])

    lats = np.degrees(np.arcsin(np.clip(pts[:, :, 2], -1.0, 1.0)))  # (N, S)
    lons = np.degrees(np.arctan2(pts[:, :, 1], pts[:, :, 0]))        # (N, S)

    rows = np.round((lats + 90.0) * 60.0).astype(np.int32).clip(0, MASK_NLAT - 1)
    cols = np.round((lons + 180.0) * 60.0).astype(np.int32) % MASK_NLON
    # _mask[r,c] = 1 → land; ocean fraction = 1 - mean(land)
    ocean_fracs = 1.0 - _mask[rows, cols].mean(axis=1)

    return row_idx, ocean_fracs.astype(np.float32)


def _apply_colormap(fracs):
    """
    Map ocean fraction [0,1] to RGBA using red → green → blue gradient.
    fracs: (H, W) float32.  Returns (H, W, 4) uint8.
    """
    r = np.zeros_like(fracs)
    g = np.zeros_like(fracs)
    b = np.zeros_like(fracs)

    # Red (#e74c3c) → Green (#27ae60): fraction 0.0 → 0.5
    lo = fracs < 0.5
    t = fracs[lo] * 2.0
    r[lo] = 0.906 * (1 - t) + 0.153 * t
    g[lo] = 0.298 * (1 - t) + 0.682 * t
    b[lo] = 0.235 * (1 - t) + 0.376 * t

    # Green (#27ae60) → Blue (#2980b9): fraction 0.5 → 1.0
    hi = ~lo
    t = (fracs[hi] - 0.5) * 2.0
    r[hi] = 0.153 * (1 - t) + 0.161 * t
    g[hi] = 0.682 * (1 - t) + 0.502 * t
    b[hi] = 0.376 * (1 - t) + 0.725 * t

    rgba = np.stack([
        (r * 255).clip(0, 255).astype(np.uint8),
        (g * 255).clip(0, 255).astype(np.uint8),
        (b * 255).clip(0, 255).astype(np.uint8),
        np.full(fracs.shape, 200, dtype=np.uint8),  # alpha ~78%
    ], axis=-1)
    return rgba


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mask',    default=DEFAULT_MASK)
    parser.add_argument('--output',  default=DEFAULT_OUT)
    parser.add_argument('--png',     default=DEFAULT_PNG)
    parser.add_argument('--workers', type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()

    print(f'Pole grid: {N_POLE_LAT} rows × {N_POLE_LON} cols  ({POLE_RES * 60:.0f} arc-minute)')
    print(f'Samples per great circle: {N_SAMPLES}')
    print(f'Workers: {args.workers}')
    print(f'Mask: {args.mask}')

    heatmap = np.zeros((N_POLE_LAT, N_POLE_LON), dtype=np.float32)
    t0 = time.time()

    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_worker_init,
        initargs=(args.mask,),
    ) as pool:
        futures = {pool.submit(_compute_row, r): r for r in range(N_POLE_LAT)}
        done = 0
        for fut in as_completed(futures):
            row_idx, fracs = fut.result()
            heatmap[row_idx] = fracs
            done += 1
            if done % 100 == 0 or done == N_POLE_LAT:
                pct  = done / N_POLE_LAT * 100
                rate = done / (time.time() - t0)
                eta  = (N_POLE_LAT - done) / rate if rate > 0 else 0
                print(f'  {done}/{N_POLE_LAT}  ({pct:.0f}%)  eta {eta:.0f}s', flush=True)

    print(f'Computed in {time.time() - t0:.1f}s')
    print(f'Ocean fraction range: {heatmap.min():.3f} – {heatmap.max():.3f}')

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    np.save(args.output, heatmap)
    print(f'Saved {args.output}')

    if not HAS_PIL:
        print('Pillow not installed — skipping PNG output.  pip install Pillow')
        return

    # PNG: flip north-to-south for Mapbox image overlay (row 0 = northernmost)
    rgba = _apply_colormap(heatmap[::-1])
    img  = Image.fromarray(rgba, mode='RGBA')
    img.save(args.png, optimize=True)
    mb = os.path.getsize(args.png) / 1e6
    print(f'Saved {args.png}  ({mb:.1f} MB)')


if __name__ == '__main__':
    main()
