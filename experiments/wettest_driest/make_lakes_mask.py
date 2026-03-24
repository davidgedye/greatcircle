"""
make_lakes_mask.py — Rasterize HydroLAKES polygons onto an elevation grid.

Produces a lakes mask .npy file: int8 array, same shape as the source grid,
with 1 where a lake polygon covers the cell and 0 elsewhere.  Works with both
GEBCO (standard NetCDF lat/lon) and ETOPO (GMT grid format).

Usage:
    python3 make_lakes_mask.py data/GEBCO_2025_sub_ice.nc \
                               data/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp \
                               data/lakes_mask.npy

    python3 make_lakes_mask.py data/ETOPO_2022_v1_60s_N90W180_surface.nc \
                               data/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp \
                               data/etopo_lakes_mask.npy
"""

import argparse
import time

import fiona
import netCDF4 as nc
import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.geometry import shape, box


def load_grid_dims(path):
    """Return (nlat, nlon, lat_min, lat_max, lon_min, lon_max) from GEBCO or ETOPO NetCDF."""
    ds = nc.Dataset(path, "r")
    if "x_range" in ds.variables:
        # GMT grid format (ETOPO)
        lon_min = float(ds.variables["x_range"][0])
        lon_max = float(ds.variables["x_range"][1])
        lat_min = float(ds.variables["y_range"][0])
        lat_max = float(ds.variables["y_range"][1])
        dlat    = float(ds.variables["spacing"][1])
        dlon    = float(ds.variables["spacing"][0])
        nlon    = int(ds.variables["dimension"][0])
        nlat    = int(ds.variables["dimension"][1])
        ds.close()
    else:
        lat_var = next(n for n in ds.variables if n.lower() in ("lat", "latitude"))
        lon_var = next(n for n in ds.variables if n.lower() in ("lon", "longitude"))
        lats = ds.variables[lat_var][:]
        lons = ds.variables[lon_var][:]
        ds.close()
        nlat, nlon = len(lats), len(lons)
        lat_min, lat_max = float(lats.min()), float(lats.max())
        lon_min, lon_max = float(lons.min()), float(lons.max())
        dlat = abs(float(lats[1] - lats[0]))
        dlon = abs(float(lons[1] - lons[0]))
    print(f"Grid: {nlat} x {nlon}  ({dlat*60:.2f} arc-min resolution)")
    return nlat, nlon, lat_min, lat_max, lon_min, lon_max


def rasterize_lakes(shp_path, nlat, nlon, lat_min, lat_max, lon_min, lon_max, out_path):
    """Rasterize HydroLAKES polygons onto the GEBCO grid, processing in lat bands."""
    # rasterio transform: (west, south, east, north)
    # GEBCO lats are cell centres; expand by half-cell to get cell edges
    dlat = (lat_max - lat_min) / (nlat - 1)
    dlon = (lon_max - lon_min) / (nlon - 1)
    west  = lon_min - dlon / 2
    east  = lon_max + dlon / 2
    south = lat_min - dlat / 2
    north = lat_max + dlat / 2
    transform = from_bounds(west, south, east, north, nlon, nlat)

    mask = np.zeros((nlat, nlon), dtype=np.int8)

    # Process in latitude bands to limit peak RAM
    band_deg = 10.0
    band_rows = max(1, int(band_deg / dlat))

    print(f"Rasterizing HydroLAKES in {band_deg}° latitude bands ...")
    t0 = time.time()

    with fiona.open(shp_path) as src:
        total_features = len(src)
        print(f"  {total_features:,} lake polygons")

        for band_start_row in range(0, nlat, band_rows):
            band_end_row = min(band_start_row + band_rows, nlat)

            # Latitude extent of this band (cell centres + half-cell margin)
            band_lat_min = lat_min + band_start_row * dlat - dlat / 2
            band_lat_max = lat_min + (band_end_row - 1) * dlat + dlat / 2
            band_box = box(west, band_lat_min, east, band_lat_max)

            # Collect polygons that intersect this band using spatial index
            geoms = []
            for feat in src.filter(bbox=(west, band_lat_min, east, band_lat_max)):
                geom = shape(feat["geometry"])
                clipped = geom.intersection(band_box)
                if not clipped.is_empty:
                    geoms.append(clipped)

            if geoms:
                # Sub-transform for this band
                band_height = band_end_row - band_start_row
                band_south = lat_min + band_start_row * dlat - dlat / 2
                band_north = lat_min + (band_end_row - 1) * dlat + dlat / 2
                band_transform = from_bounds(west, band_south, east, band_north, nlon, band_height)
                band_mask = rasterize(
                    ((g, 1) for g in geoms),
                    out_shape=(band_height, nlon),
                    transform=band_transform,
                    dtype=np.int8,
                    fill=0,
                )
                # rasterize() returns row 0 = northernmost (rasterio convention).
                # Flip so the band is stored south-to-north, matching the
                # ascending-lat row indexing used in add_boundaries.py.
                mask[band_start_row:band_end_row, :] |= band_mask[::-1]

            if band_start_row % (band_rows * 5) == 0:
                pct = band_start_row / nlat * 100
                print(f"  {pct:.0f}% ({time.time()-t0:.0f}s elapsed)", flush=True)

    # rasterio rasterizes north-to-south (row 0 = north); each band_mask is
    # flipped on write so the final mask is ascending (row 0 = southernmost).
    print(f"  Done in {time.time()-t0:.1f}s")
    print(f"  Lake cells: {mask.sum():,} / {nlat*nlon:,}  ({mask.mean()*100:.3f}%)")
    np.save(out_path, mask)
    print(f"Saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Build lakes mask from HydroLAKES shapefile.")
    parser.add_argument("grid",    help="Path to elevation NetCDF (GEBCO or ETOPO, for grid dimensions)")
    parser.add_argument("shp",     help="Path to HydroLAKES .shp file")
    parser.add_argument("output",  help="Output path for lakes mask (.npy)")
    args = parser.parse_args()

    nlat, nlon, lat_min, lat_max, lon_min, lon_max = load_grid_dims(args.grid)
    rasterize_lakes(args.shp, nlat, nlon, lat_min, lat_max, lon_min, lon_max, args.output)


if __name__ == "__main__":
    main()
