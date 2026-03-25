"""
make_explorer_tiles.py — Generate XYZ raster tiles from the heatmap.

Reprojects the equirectangular heatmap into Web Mercator (EPSG:3857) tiles
for use as a Mapbox raster tile source.

Usage:
    cd experiments/wettest_driest
    python3 make_explorer_tiles.py --max-zoom 6
"""

import argparse
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from PIL import Image

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'explorer', 'heatmap_5m.npy'))
DEFAULT_OUT  = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'explorer', 'tiles'))
TILE_SIZE    = 256
POLE_RES     = 5 / 60   # degrees per heatmap cell
_heatmap     = None      # loaded in workers
_vmin        = 0.0
_vmax        = 1.0


def _worker_init(npy_path, vmin, vmax):
    global _heatmap, _vmin, _vmax
    _heatmap = np.load(npy_path)   # (nlat, nlon) float32, row 0 = 90°S
    _vmin, _vmax = vmin, vmax


def _colorize(fracs):
    """Map ocean fraction [0,1] → RGBA uint8 — same palette as heatmap script."""
    r = np.zeros_like(fracs)
    g = np.zeros_like(fracs)
    b = np.zeros_like(fracs)
    lo = fracs < 0.5
    hi = ~lo
    t = fracs[lo] * 2.0
    r[lo] = 0.906 * (1 - t) + 0.153 * t
    g[lo] = 0.298 * (1 - t) + 0.682 * t
    b[lo] = 0.235 * (1 - t) + 0.376 * t
    t = (fracs[hi] - 0.5) * 2.0
    r[hi] = 0.153 * (1 - t) + 0.161 * t
    g[hi] = 0.682 * (1 - t) + 0.502 * t
    b[hi] = 0.376 * (1 - t) + 0.725 * t
    return np.stack([
        (r * 255).clip(0, 255).astype(np.uint8),
        (g * 255).clip(0, 255).astype(np.uint8),
        (b * 255).clip(0, 255).astype(np.uint8),
        np.full(fracs.shape, 200, dtype=np.uint8),
    ], axis=-1)


def _render_tile(z, x, y, out_dir):
    n    = 2 ** z
    nlat, nlon = _heatmap.shape

    # Pixel column → longitude
    lon_min = x / n * 360.0 - 180.0
    lons = lon_min + (np.arange(TILE_SIZE) + 0.5) / TILE_SIZE * (360.0 / n)  # (W,)

    # Pixel row → latitude via inverse Mercator
    def merc_to_lat(py):
        merc = math.pi * (1.0 - 2.0 * (y + (py + 0.5) / TILE_SIZE) / n)
        return math.degrees(math.atan(math.sinh(merc)))

    lats = np.array([merc_to_lat(py) for py in range(TILE_SIZE)])  # (H,)

    # Sample heatmap (nearest-neighbour; row 0 = 90°S)
    rows = np.round((lats + 90.0) / POLE_RES - 0.5).astype(np.int32).clip(0, nlat - 1)
    cols = (np.round((lons + 180.0) / POLE_RES - 0.5).astype(np.int32)) % nlon
    raw   = _heatmap[rows[:, None], cols[None, :]]   # (H, W)
    fracs = np.clip((raw - _vmin) / (_vmax - _vmin), 0.0, 1.0)

    rgba = _colorize(fracs)
    img  = Image.fromarray(rgba, mode='RGBA')

    path = os.path.join(out_dir, str(z), str(x), f'{y}.png')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, optimize=True)
    return path


def _task(args):
    return _render_tile(*args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',    default=DEFAULT_IN)
    parser.add_argument('--output',   default=DEFAULT_OUT)
    parser.add_argument('--max-zoom', type=int, default=6)
    parser.add_argument('--workers',  type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()

    tasks = []
    for z in range(args.max_zoom + 1):
        n = 2 ** z
        for x in range(n):
            for y in range(n):
                tasks.append((z, x, y, args.output))

    heatmap = np.load(args.input)
    vmin, vmax = float(heatmap.min()), float(heatmap.max())
    print(f'Ocean fraction range: {vmin:.3f} – {vmax:.3f}  (normalising to full colour range)')
    print(f'Generating {len(tasks)} tiles (zoom 0–{args.max_zoom}) with {args.workers} workers ...')
    os.makedirs(args.output, exist_ok=True)

    done = 0
    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_worker_init,
        initargs=(args.input, vmin, vmax),
    ) as pool:
        for _ in pool.map(_task, tasks, chunksize=20):
            done += 1
            if done % 500 == 0 or done == len(tasks):
                print(f'  {done}/{len(tasks)}', flush=True)

    print(f'Done. Tiles in {args.output}')


if __name__ == '__main__':
    main()
