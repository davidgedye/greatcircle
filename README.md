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

| | Pole location | Equatorial crossings | Score |
|---|---|---|---|
| **Wettest (fine)** | 24.14°N 79.13°E | 169°E / 11°W | **91.61% ocean** |
| **Driest (fine)** | 6.54°S 25.27°E | 115°E / 65°W | **57.72% land** |

The wettest circle tilts through the western Pacific, Arctic Ocean and southern Indian Ocean — almost entirely open water. The driest circle passes through central Asia, Europe, North America and sub-Saharan Africa, threading the major continental land masses.

## Usage

```bash
# Install dependencies
pip install netCDF4 scipy numpy

# Copy config and add your Mapbox token
cp config.py.example config.py
# edit config.py

# Run full search (coarse + fine) using all cores
python3 great_circles.py data/ETOPO1_Ice_c_gdal.grd --workers 8

# Generate interactive visualisation
python3 visualize.py

# Serve locally (fetch() requires HTTP — file:// won't work)
python3 -m http.server 8000
# Open http://localhost:8000/results.html
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

`visualize.py` generates two files: `results.html` (the page) and `data.json` (all GeoJSON and fine-grid data, ~277 KB). The page fetches `data.json` at load time, so it must be served over HTTP.

**Map features:**
- Satellite + roads basemap (switchable via dropdown to Satellite, Dark, Outdoors, Light)
- Globe projection with atmosphere fog
- All six layers grow in width as you zoom in; fine best lines represent the ~10 km positional uncertainty band
- Layer toggles — only the two fine best results are shown by default
- Collapsible legend panel; globe centres itself in the area to the left of the panel
- North-up / no-tilt reset button (bottom right)
- Map style switcher dropdown

**Great circle pole markers:**
- `+` symbols mark both poles of each winning great circle's axis (cyan for wettest, red for driest)
- Clicking a pole marker shows an explanation in the HUD

**Hover tooltips:**
- Hovering any line shows its label, coverage percentage, and pole location in lat/lon

**Fine search heatmaps** (in the legend panel):
- Show the optimisation landscape (ocean/land fraction) across the ±2° fine search window
- White crosshair = best found point; coloured crosshair = currently selected point
- Hover to read the coverage value and pole location at any cell

**Bidirectional map ↔ heatmap interaction:**
- *Click on the map* near a winning line: draws a dashed great circle through that point, shows the coverage for both the best known result (solid swatch) and the perturbed circle (dashed swatch) in the HUD, and highlights the corresponding position in the fine-search heatmap
- *Click on a heatmap cell*: draws the great circle for that (θ, φ) on the map and highlights the clicked cell
- Press **Escape** to clear

**Uncertainty bands:** All lines grow with zoom. The fine best lines reach ~130 px width at zoom 10, representing the estimated ~10 km positional uncertainty from:

1. **Search grid resolution** — fine step size of 0.05°, results cluster within ~0.03° → ~3–5 km lateral displacement
2. **ETOPO1 coastline accuracy** — 1 arc-minute cells, coastal positions uncertain by ~2–4 km
3. **Elevation threshold** — tidal flats can shift the effective coastline by 2–10 km

Combined (RSS): ~7 km, rounded to 10 km for display.

**Antimeridian handling:** Line coordinates are unwrapped (allowed to exceed ±180°) rather than split, keeping great circles continuous across the antimeridian on a globe projection.

## Files

| File | Purpose |
|------|---------|
| `great_circles.py` | Data loading, search algorithm, console output |
| `visualize.py` | Reads results and generates `results.html` + `data.json` |
| `config.py` | Mapbox token — gitignored, copy from `config.py.example` |
| `config.py.example` | Token placeholder for new users |
| `data.json` | GeoJSON layers + fine search grids (committed) |
| `results.html` | Generated interactive visualisation (gitignored) |
| `fine_grids.json` | Full fine search surfaces, written by `great_circles.py` |
| `data/ETOPO1_Ice_c_gdal.grd` | Elevation data — not in repo (~900 MB) |
| `great_circles_project.md` | Original design notes and problem definition |
