# Wettest and Driest Great Circles on Earth

Find the great circle around Earth that maximises ocean/water surface coverage ("wettest") and the one that minimises it ("driest"). "Wet" and "dry" refer purely to binary land/water coverage — not precipitation.

## Background

Chabukswar & Mukherjee (2018) found the longest *uninterrupted* great-circle path over water (32,090 km, Pakistan → Kamchatka). That is a different objective: longest single segment, not maximum total fraction. This project addresses the total-fraction version, which does not appear to have been published.

## Data

**ETOPO1 Ice Surface** (NOAA NCEI), 1 arc-minute resolution (~1.85 km at the equator).

- Download: `ETOPO1_Ice_c_gdal.grd.gz` from `ngdc.noaa.gov/mgg/global/`
- Water definition: elevation ≤ 0 m
- GEBCO is also supported (auto-detected on load)
- Lakes above sea level (Great Lakes, Caspian Sea, etc.) are not counted as water under this definition

Place the unzipped file at `data/ETOPO1_Ice_c_gdal.grd`.

## Approach

### Parameterisation

A great circle is uniquely identified by its plane's normal vector **n**, expressed in spherical coordinates as (θ, φ):

- **θ** (colatitude): 0° – 180°
- **φ** (longitude): 0° – 180° — antipodal symmetry halves the search space

The grid must be sampled **uniformly in cos(θ)**, not uniformly in θ, to give equal solid-angle coverage. A naive linear grid in θ would oversample near the poles of normal-vector space.

### Two-stage search

**Stage 1 — Coarse grid** (~32,400 circles, ~30 s on 8 cores)
- 180×180 grid in (cos θ, φ)
- 21,600 sample points per circle (one per arc-minute, matching ETOPO1 resolution)
- Nearest-neighbour lookup via `scipy.ndimage.map_coordinates`
- Parallelised across CPU cores with `ProcessPoolExecutor`

**Stage 2 — Fine zoom** (~90 s on 8 cores)
- Top 10 wettest and bottom 10 driest coarse candidates are each refined
- ±2° window around each seed at 0.05° step size (80×80 grid per candidate)
- Maximised for wettest, minimised for driest
- Full search surface saved to `fine_grids.json` for visualisation

### Results

| | θ (°) | φ (°) | Equatorial crossings | Ocean fraction |
|---|---|---|---|---|
| **Wettest (fine)** | 65.86 | 79.13 | 169°E / 11°W | **91.61%** |
| **Driest (fine)** | 96.57 | 25.35 | 115°E / 65°W | **42.25%** |

The wettest circle tilts through the western Pacific, Arctic Ocean and southern Indian Ocean — almost entirely open water. The driest circle passes through central Asia, Europe, North America and sub-Saharan Africa, threading the major continental land masses.

## Usage

```bash
# Install dependencies
pip install netCDF4 scipy numpy

# Run full search (coarse + fine) using all cores
python3 great_circles.py data/ETOPO1_Ice_c_gdal.grd --workers 8

# Generate interactive visualisation
python3 visualize.py
# Open results.html in a browser
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--workers N` | 1 | Parallel worker processes |
| `--grid N` | 180 | Coarse grid size (N×N) |
| `--pts N` | 21600 | Sample points per circle |
| `--no-fine` | off | Skip fine zoom stage |
| `--top N` | 10 | Results to print per category |

## Visualisation

`visualize.py` generates `results.html`: a self-contained interactive 3D globe using Mapbox GL JS.

**Features:**
- Satellite basemap with globe projection
- Layer toggles for coarse and fine results (only fine results shown by default)
- Hover tooltips showing ocean % and (θ, φ) for any circle
- Fine search heatmaps showing the optimisation landscape around each best candidate — hover to read values at any cell
- Collapsible legend panel
- North-up reset button (resets both bearing and pitch)

**Uncertainty bands:** The two fine result lines grow in width as you zoom in, scaled to represent the estimated ~10 km positional uncertainty in the great circle location. This uncertainty arises from:

1. **Search grid resolution** — fine step size of 0.05°, results cluster within ~0.03° → ~3–5 km lateral displacement
2. **ETOPO1 coastline accuracy** — 1 arc-minute cells, coastal positions uncertain by ~2–4 km
3. **Elevation threshold** — tidal flats can shift the effective coastline by 2–10 km

Combined (RSS): ~7 km, rounded to 10 km for display. The line width in pixels at zoom level z is approximately `2^z / 8`, giving 2 px at zoom 4 and ~130 px at zoom 10.

## Files

| File | Purpose |
|------|---------|
| `great_circles.py` | Data loading, search algorithm, console output |
| `visualize.py` | Reads results and generates `results.html` |
| `data/ETOPO1_Ice_c_gdal.grd` | Elevation data (not in repo) |
| `fine_grids.json` | Full fine search surfaces, written by `great_circles.py` |
| `results.html` | Generated interactive visualisation |
| `great_circles_project.md` | Original design notes and problem definition |
