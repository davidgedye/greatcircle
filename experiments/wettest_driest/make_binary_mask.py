"""
make_binary_mask.py — Build a packed binary land/ocean mask from ETOPO 2022.

Output layout (south-to-north, west-to-east):
  row 0 = 90°S,   row 10799 ≈ 90°N
  col 0 = -180°W, col 21599 ≈ 180°E
  bit = 1 → land, 0 → ocean

HydroLAKES mask applied in suppress mode: sub-sea-level lake beds
(e.g. Great Lakes, Lake Baikal) are treated as land, not ocean.

Unpacked: ~29 MB.  Gzipped: ~6 MB.

Usage:
    cd experiments/wettest_driest
    python3 make_binary_mask.py ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc \\
        --lakes-mask ../../data/etopo_lakes_mask.npy \\
        --output ../../explorer/mask_60s.bin.gz
"""

import argparse
import gzip
import os

import netCDF4 as nc
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.normpath(
    os.path.join(SCRIPT_DIR, '..', '..', 'explorer', 'mask_60s.bin.gz')
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('etopo', help='Path to ETOPO 2022 NetCDF')
    parser.add_argument('--lakes-mask', metavar='PATH',
                        help='etopo_lakes_mask.npy — suppresses sub-sea-level lake beds')
    parser.add_argument('--output', default=DEFAULT_OUT)
    args = parser.parse_args()

    print(f'Loading {args.etopo} ...')
    ds = nc.Dataset(args.etopo, 'r')

    if 'x_range' in ds.variables:
        # GMT grid format: flat z stored top-to-bottom
        nlon    = int(ds.variables['dimension'][0])
        nlat    = int(ds.variables['dimension'][1])
        lat_min = float(ds.variables['y_range'][0])
        lat_max = float(ds.variables['y_range'][1])
        print(f'  GMT format — {nlat} rows × {nlon} cols')
        print('  Reading elevation ...')
        z = ds.variables['z'][:].reshape(nlat, nlon)
        ds.close()
        # GMT: row 0 = northernmost → flip to ascending (row 0 = 90°S)
        land = (z > 0)[::-1].copy()
        del z
    else:
        # Standard NetCDF (ETOPO 2022): z is 2D, lat may be ascending or descending
        lat_var = next(n for n in ds.variables if n.lower() in ('lat', 'latitude'))
        lats    = ds.variables[lat_var][:]
        nlat    = len(lats)
        nlon    = ds.variables['z'].shape[1]
        lat_min = float(lats[0])
        print(f'  Standard NetCDF — {nlat} rows × {nlon} cols  lat[0]={lat_min:.3f}')
        print('  Reading elevation ...')
        z = ds.variables['z'][:]
        ds.close()
        land = (z > 0).copy()
        del z
        if lats[0] > lats[-1]:
            # Descending → flip to ascending (row 0 = 90°S)
            land = land[::-1].copy()

    print(f'  Grid: {nlat} rows × {nlon} cols')
    print(f'  Pre-suppress land: {land.sum():,} / {nlat * nlon:,}  ({land.mean() * 100:.2f}%)')

    if args.lakes_mask:
        print(f'  Applying lakes mask {args.lakes_mask} ...')
        lakes = np.load(args.lakes_mask, mmap_mode='r')  # ascending, row 0 = south
        land |= lakes.astype(bool)   # lake beds → land (suppress spurious water)
        print(f'  Lake cells suppressed: {int(lakes.sum()):,}')

    print(f'  Final land cells: {int(land.sum()):,}  ({land.mean() * 100:.2f}%)')

    packed = np.packbits(land)   # MSB first; ~29 MB

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    print(f'Writing {args.output} ...')
    with gzip.open(args.output, 'wb', compresslevel=9) as f:
        f.write(packed.tobytes())

    mb = os.path.getsize(args.output) / 1e6
    print(f'Done — {mb:.1f} MB')
    print()
    print('JS bit layout:')
    print('  row = Math.round((lat + 90) * 60)    // 0..10799, row 0 = 90°S')
    print('  col = Math.round((lon + 180) * 60) % 21600')
    print('  i   = row * 21600 + col')
    print('  bit = (mask[i >> 3] >> (7 - (i & 7))) & 1   // 1 = land')


if __name__ == '__main__':
    main()
