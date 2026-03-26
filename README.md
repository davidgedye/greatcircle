# Wettest and Driest Great Circles on Earth
A "great circle" is any full circumference of the Earth. If the center of a circle is the center of the Earth,  you have a great circle. The equator is a great circle, and so is any circle that goes through both poles, but the circle can be tilted at any angle, and cross the equator at any two opposite points.

This project checks all possible great circles and finds the one that maximizes the ocean coverage (the "wettest") and the one that minimizes it (the "driest").

An interactive visualisation is hosted at **https://davidgedye.github.io/greatcircle/**.

## Background

Chabukswar & Mukherjee (2018) found the longest *uninterrupted* great-circle path over water (32,090 km, Pakistan → Kamchatka). That is a different objective: longest single segment, not maximum total fraction. This project addresses the total-fraction version, which does not appear to have been published.

## Data

**ETOPO 2022** — 1 arc-minute (~1.85 km) global relief model, ice-surface elevation. Water defined as elevation ≤ 0 m.

| | |
|---|---|
| Source | NOAA |
| Resolution | 1 arc-minute (~1.85 km) |
| Ice treatment | Ice-surface elevation |
| File | `ETOPO_2022_v1_60s_N90W180_surface.nc` |
| Size | ~457 MB |
| Download | [ncei.noaa.gov](https://www.ncei.noaa.gov/products/etopo-global-relief-model) |

Place the data file under `data/` at the repo root (not committed — too large).

## Approach

### Parameterisation

A great circle is uniquely identified by its plane's normal vector **n**, expressed in spherical coordinates as (θ, φ):

- **θ** (colatitude): 0°–180° — measured from the North Pole, so θ = 90° − latitude
- **φ** (longitude): 0°–180° — antipodal symmetry halves the search space

The grid must be sampled **uniformly in cos(θ)**, not uniformly in θ, to give equal solid-angle coverage. A naive linear grid in θ would oversample near the poles of normal-vector space.

### Two-stage search

**Stage 1 — Coarse grid** (~32,400 circles at default grid=180)
- 180×180 grid in (cos θ, φ)
- 21,600 sample points per circle (matches ETOPO 1 arc-minute resolution)
- Nearest-neighbour lookup via `scipy.ndimage.map_coordinates`
- Parallelised across CPU cores with `ProcessPoolExecutor`

**Stage 2 — Fine zoom**
- Top 10 coarse candidates are each refined
- ±2° window around each seed at 0.05° step size (80×80 grid per candidate)
- Full search surface saved to `etopo.json` for visualisation

## Results

| Dataset | | Pole location | Score |
|---|---|---|---|
| **ETOPO 2022** | Wettest | 24.14°N 79.58°E | **91.56% ocean** |
| **ETOPO 2022** | Driest | 6.57°S 25.22°E | **57.69% land** |

*Results as of 2026-03-24 (commit a29c472)*

The wettest circle tilts through the Indian Ocean, western Pacific and Arctic — almost entirely open water. The driest circle threads through central Africa, Europe, central Asia and North America, crossing the major continental land masses.

## Repository structure

```
index.html                          Web visualisation (GitHub Pages root)
experiments/
  wettest_driest/
    great_circles.py                Search algorithm — writes results JSON
    add_boundaries.py               Augments results with land/water boundary points
    visualize.py                    Converts results JSON → web-ready JSON
    Makefile                        Full pipeline
    etopo.json                      Search results (gitignored, regenerated locally)
    etopo_visuals.json              Map data (initial load)
    etopo_details.json              Detail data (lazy-loaded)
data/
  ETOPO_2022_v1_60s_N90W180_surface.nc  Not in repo (~457 MB)
```

## Usage

All commands run from `experiments/wettest_driest/`.

```bash
pip install netCDF4 scipy numpy

# Full pipeline (search → boundaries → web JSON)
make

# Or step by step:
python3 great_circles.py ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc --workers 8
python3 add_boundaries.py ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc
python3 visualize.py

# Serve locally
python3 -m http.server 8000  # from repo root
# Open http://localhost:8000/
```

### Key options for `great_circles.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--workers N` | 1 | Parallel worker processes |
| `--grid N` | 180 | Coarse grid size (N×N) |
| `--pts N` | 3600 | Sample points per circle |
| `--no-fine` | off | Skip fine zoom stage |

## Visualisation

The web page (`index.html`) loads map data immediately and lazily loads detail data (heatmaps, boundary arrows) only when the Details panel is opened.

**Map features:**
- Globe projection with atmosphere and fog
- Switchable basemap (Satellite, Dark, Outdoors, Light, etc.)
- Fine best great circles shown by default; coarse top-10 toggleable in Details
- Lines grow in width with zoom; fine best lines represent the ~10 km positional uncertainty band
- Scale indicator (bottom left)

**Land/water boundary arrows** (Details panel):
- Triangular arrows at every land/water transition along the top-10 coarse and best fine circles, pointing toward land
- Computed at full dataset resolution using chunked streaming to avoid loading the full elevation file into memory

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
2. **Coastline accuracy** — ETOPO 1 arc-minute cells (~1.85 km) → ~1–2 km
3. **Elevation threshold** — tidal flats can shift the effective coastline by 2–10 km

Combined (RSS): ~7 km, rounded to 10 km for display.

## Known issues

**Line rendering artefacts near the poles (Mapbox GL JS bug).** When the globe is oriented to show either pole, lines passing near a pole may render with banded fuzziness at certain zoom levels, or as a large partial arc rather than a tight curve. This is a known, unresolved bug in Mapbox GL JS globe projection ([issue #12026](https://github.com/mapbox/mapbox-gl-js/issues/12026), open since June 2022). The root cause is that the renderer draws line segments as straight lines in projected tile space, which breaks down at extreme latitudes. No workaround is available within the current Mapbox API; the code passes correct densely-sampled GeoJSON and will render properly if/when Mapbox fixes the underlying issue.
