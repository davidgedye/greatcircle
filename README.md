# Wettest and Driest Great Circles on Earth
A “great circle” is any full circumference of the Earth. If the center of a circle is the center of the Earth,  you have a great circle. The equator is a great circle, and so is any circle that goes through both poles, but the circle can be tilted at any angle, and cross the equator at any two opposite points.

This project checks all possible great circles and finds the one that maximizes the ocean coverage (the "wettest") and the one that minimizes it (the "driest"). 

An interactive visualisation is hosted at **https://davidgedye.github.io/greatcircle/**.

## Background

Chabukswar & Mukherjee (2018) found the longest *uninterrupted* great-circle path over water (32,090 km, Pakistan → Kamchatka). That is a different objective: longest single segment, not maximum total fraction. This project addresses the total-fraction version, which does not appear to have been published.

## Data

Two elevation datasets are supported and can be switched in the visualiser. Both use elevation ≤ 0 m as the water definition.

| | ETOPO 2022 (default) | GEBCO 2025 Sub-Ice |
|---|---|---|
| Source | NOAA | General Bathymetric Chart of the Oceans |
| Resolution | 1 arc-minute (~1.85 km) | 15 arc-second (~450 m) |
| Ice treatment | Ice-surface elevation | Sub-ice bed topography |
| File | `ETOPO_2022_v1_60s_N90W180_surface.nc` | `GEBCO_2025_sub_ice.nc` |
| Size | ~457 MB | ~3.7 GB |
| Download | [ncei.noaa.gov](https://www.ncei.noaa.gov/products/etopo-global-relief-model) | [gebco.net](https://www.gebco.net/data_and_products/gridded_bathymetry_data/) |

The ice treatment difference matters: GEBCO classifies the sub-ice beds of Greenland and Antarctica (largely below sea level) as water, while ETOPO 2022 classifies the ice surface as land. This accounts for the ~5 percentage point difference in wettest scores between the two datasets.

**HydroLAKES** (optional, GEBCO only) — polygon dataset of lakes and reservoirs ≥ 10 ha worldwide (~1.4 M features, [hydrosheds.org](https://www.hydrosheds.org/products/hydrolakes)). When enabled, lake surfaces above sea level are also counted as water. This variant is available as a toggle in the visualiser alongside the GEBCO dataset.

**Sub-sea-level lake beds (GEBCO artefact).** GEBCO records the actual bed topography of freshwater lakes. Several large lakes have beds that dip below sea level — Lake Superior's bed reaches −223 m (surface 183 m, max depth 406 m), Lake Michigan's reaches −105 m (surface 176 m, max depth 281 m). Because the water/land threshold is elevation ≤ 0 m, the deep central portions of these lakes are classified as water while the shallower margins are classified as land, producing spurious land/water transitions scattered across the lake interior. To suppress this artefact, `add_boundaries.py` applies the HydroLAKES mask in *reverse* for non-lakes experiments: any cell that falls within a lake polygon is forced to land, removing the false transitions. Toggling the lakes checkbox in the visualiser switches to the fully correct treatment where the entire lake surface is counted as water.

Place data files under `data/` at the repo root (not committed — too large).

## Approach

### Parameterisation

A great circle is uniquely identified by its plane's normal vector **n**, expressed in spherical coordinates as (θ, φ):

- **θ** (colatitude): 0°–180°
- **φ** (longitude): 0°–180° — antipodal symmetry halves the search space

The grid must be sampled **uniformly in cos(θ)**, not uniformly in θ, to give equal solid-angle coverage. A naive linear grid in θ would oversample near the poles of normal-vector space.

### Two-stage search

**Stage 1 — Coarse grid** (~32,400 circles at default grid=180)
- 180×180 grid in (cos θ, φ)
- 86,400 sample points per circle (matches GEBCO 15 arc-second resolution); ETOPO1 uses 21,600
- Nearest-neighbour lookup via `scipy.ndimage.map_coordinates`
- Parallelised across CPU cores with `ProcessPoolExecutor`

**Stage 2 — Fine zoom**
- Top 10 coarse candidates are each refined
- ±2° window around each seed at 0.05° step size (80×80 grid per candidate)
- Full search surface saved to `results.json` for visualisation

## Results

| Dataset | | Pole location | Score |
|---|---|---|---|
| **ETOPO 2022** | Wettest | 24.1°N 79.6°E | **91.56% ocean** |
| **ETOPO 2022** | Driest | 6.6°S 25.2°E | **57.69% land** |
| **GEBCO** | Wettest | 6.3°S 63.4°E | **96.32% ocean** |
| **GEBCO** | Driest | 13.0°N 15.3°E | **53.11% land** |
| **GEBCO + lakes** | Wettest | 6.3°S 63.4°E | **96.32% ocean** |
| **GEBCO + lakes** | Driest | 13.0°N 15.3°E | **51.55% land** |

The two datasets find different wettest circles (ETOPO 2022: Indian subcontinent axis; GEBCO: Indian Ocean axis) but similar driest circles (both cross central Africa and Asia). The ~5 pp wettest score difference is explained by ice sheet treatment — see the Data section.

The wettest circle tilts through the Indian Ocean, western Pacific and Arctic — almost entirely open water. The driest circle threads through central Africa, Europe, central Asia and North America, crossing the major continental land masses.

## Repository structure

```
index.html                          Web visualisation (GitHub Pages root)
experiments/
  wettest_driest/
    great_circles.py                Search algorithm — writes results JSON
    add_boundaries.py               Augments results with land/water boundary points
    make_lakes_mask.py              Rasterises HydroLAKES onto the GEBCO grid
    visualize.py                    Converts results JSON → web-ready JSON
    compare_datasets.py             Cross-dataset comparison table
    Makefile                        Full pipeline
    etopo1.json                     ETOPO1 search results
    results.json                    GEBCO search results (oceans + lakes variants)
    etopo1_visuals.json             ETOPO1 map data (initial load)
    etopo1_details.json             ETOPO1 detail data (lazy-loaded)
    gebco_visuals.json              GEBCO map data (initial load)
    gebco_details.json              GEBCO detail data (lazy-loaded)
data/
  ETOPO_2022_v1_60s_N90W180_surface.nc  Not in repo (~457 MB)
  GEBCO/GEBCO_2025_sub_ice.nc       Not in repo (~3.7 GB)
  lakes_mask.npy                    Rasterised HydroLAKES (~500 MB, generated)
  HydroLAKES_polys_v10_shp/         Not in repo
```

## Usage

All commands run from `experiments/wettest_driest/`.

```bash
pip install netCDF4 scipy numpy shapely fiona

# Full pipeline (search → boundaries → web JSON)
make

# Or step by step:
python3 great_circles.py ../../data/GEBCO/GEBCO_2025_sub_ice.nc --workers 8 --pts 86400
python3 add_boundaries.py ../../data/GEBCO/GEBCO_2025_sub_ice.nc --lakes-mask ../../data/lakes_mask.npy
python3 visualize.py

# ETOPO1
python3 great_circles.py ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc --workers 8
python3 add_boundaries.py ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc --results etopo1.json
python3 visualize.py --input etopo1.json --output etopo1_visuals.json --details-output etopo1_details.json

# Cross-dataset comparison
make compare

# Serve locally
python3 -m http.server 8000  # from repo root
# Open http://localhost:8000/
```

### Key options for `great_circles.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--workers N` | 1 | Parallel worker processes |
| `--grid N` | 180 | Coarse grid size (N×N) |
| `--pts N` | auto | Sample points per circle (defaults to dataset native resolution) |
| `--no-fine` | off | Skip fine zoom stage |
| `--lakes-mask PATH` | — | Include lakes above sea level |

## Visualisation

The web page (`index.html`) loads map data immediately and lazily loads detail data (heatmaps, boundary arrows) only when the Details panel is opened.

**Two datasets** are selectable via buttons in the Details panel. ETOPO1 loads on startup (~700 KB); GEBCO loads on demand (~1.4 MB). Hovering the buttons shows a tooltip explaining each dataset and its resolution.

**Map features:**
- Globe projection with atmosphere and fog
- Switchable basemap (Satellite, Dark, Outdoors, Light, etc.)
- Fine best great circles shown by default; coarse top-10 toggleable in Details
- Lines grow in width with zoom; fine best lines represent the ~10 km positional uncertainty band
- Scale indicator (bottom left)

**Land/water boundary arrows** (Details panel):
- Triangular arrows at every land/water transition along the top-10 coarse and best fine circles, pointing toward land
- Computed at full dataset resolution (86,400 pts for GEBCO, 21,600 for ETOPO1) using chunked streaming to avoid loading the full elevation file into memory

**Fine search heatmaps** (Details panel):
- Show the optimisation landscape across the ±2° fine search window
- Click a cell to draw that great circle on the map
- Click on the map near a winning line to highlight the corresponding heatmap cell

**Great circle pole markers:**
- `+` symbols mark both poles of each winning circle's axis
- Clicking a pole shows an explanation in the HUD

**Mobile layout:**
- At ≤640 px width, the panel collapses to a compact bottom bar showing the wettest/driest percentages and a map style selector
- Details and heatmaps require a larger screen

## Uncertainty

The fine best result has an estimated positional uncertainty of ~10 km from:

1. **Search grid resolution** — fine step 0.05°, results cluster within ~0.03° → ~3–5 km
2. **Coastline accuracy** — ETOPO1 ~1.85 km cells; GEBCO ~450 m cells → ~0.5–2 km
3. **Elevation threshold** — tidal flats can shift the effective coastline by 2–10 km

Combined (RSS): ~7 km, rounded to 10 km for display.
