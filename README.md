# Wettest and Driest Great Circles on Earth
A great circle is any full circumference of the Earth. If the center of a circle is the center of the Earth,  you have a great circle. The equator is a great circle, and so is any circle that goes through both poles, but the circle can be tilted at any angle, and cross the equator at any two opposite points.

This project checks all possible great circles and finds the one that maximizes the ocean coverage (the "wettest") and the one that minimizes it (the "driest").

An interactive visualisation is hosted at **https://davidgedye.github.io/greatcircle/**.

## Background

[Chabukswar & Mukherjee (2018)](https://arxiv.org/abs/1804.07389) found the longest *uninterrupted* great-circle path over water (32,090 km, Pakistan → Kamchatka). That is a different objective: longest single segment, not maximum total fraction. This project addresses the total-fraction version, which does not appear to have been published.

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

The wettest circle tilts through the Indian Ocean, western Pacific and Arctic — almost entirely open water. The driest circle threads through central Africa, Europe, central Asia and North America, before descending the length of South America almost along the spine of the Andes.

## Uncertainty

The fine best result has an estimated positional uncertainty of ~10 km from:

1. **Search grid resolution** — fine step 0.05°, results cluster within ~0.03° → ~3–5 km
2. **Coastline accuracy** — ETOPO 1 arc-minute cells (~1.85 km) → ~1–2 km
3. **Elevation threshold** — tidal flats can shift the effective coastline by 2–10 km

Combined (RSS): ~7 km, rounded to 10 km for display.

## Anomalies
The ETOPO data set cannot perfectly separate land from water. What it can do is show the surface elevation in meters above or below mean sea level. Two problems arise: lakes and dry land below sea level.
1. **Lakes** - it's an open question as to whether you want to count lakes as water or non-ocean land, and for a while I had a more complex data pipeline that took a bathymetric data set (GEBCO) and either subtracted or added the areas of water that had an elevation > 0. Unfortunately some lakes (e.g. Lake Superior, and Lake Baikal) have a surface that is above sea-level but a floor that is below. 
2. **Dry Land Below Sea Level** - The Dead Sea is well below sea level, and so shows as ocean on ETOPO. But so is most of the land around the Jordan river which flows into it. I know of no published data set that classifies the Jordan valley as land and the Dead Sea as water.

In the end I decided to use ETOPO as it was, and so the separation between land and water is simply the elevation level of the surface, whether that surface is a lake bottom or a below-sea-level depression. My experimentation with tricky treatment of bathymetric data never made a change of more that 0.1% of any interesting great circle.

## Repository structure

```
index.html                          Web visualisation (GitHub Pages root)
about.html                          Renders README.md in-browser (linked from map)
mask_60s.bin.gz                     1 arc-minute land/ocean mask (binary, gzip-compressed)
sw.js                               Service worker (offline cache)
manifest.json                       PWA manifest
experiments/
  wettest_driest/
    great_circles.py                Search algorithm — writes results JSON
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

# Full pipeline (search → web JSON)
make

# Or step by step:
python3 great_circles.py ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc --workers 8
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

The web page (`index.html`) is a guided experience with five states:

1. **Intro** — the globe spins and random great circles accumulate, each coloured by land (red) and ocean (blue).
2. **Examine** — click a circle to highlight it and see its land/ocean percentage. A button invites you to try your own.
3. **Explorer** — place two points on the globe to define a great circle; the land/ocean split updates live as you drag the points. After two circles the wettest and driest you have found are tracked. A Reveal button appears once data is ready.
4. **Revealed** — an animation of 100 sampled great circles sweeps the globe, then fades to reveal the computed absolute wettest and driest circles.
5. **Detailed** — a Details panel (desktop only) expands below the results showing fine-search heatmaps and coarse top-10 candidates.

**Map features:**
- Globe projection with atmosphere and fog
- Fine best great circles shown in Revealed/Detailed; coarse top-10 toggleable in Details
- Lines grow in width with zoom; fine best lines represent the ~10 km positional uncertainty band

**Fine search heatmaps** (Details panel, desktop only):
- Show the optimisation landscape across the ±2° fine search window
- Click a cell to draw that great circle on the map
- Click on the map near a winning line to highlight the corresponding heatmap cell

**Great circle pole markers:**
- `+` symbols mark both poles of each winning circle's axis

**Mobile layout:**
- Card appears below the globe showing contextual text for each state
- Details panel and heatmaps require a larger screen

## App state navigation

The app progresses forward through states and can step back with the ←Previous link (top-left, below the logo).

```
loading → intro → examine → explorer → revealed ↔ detailed
```

| From | Forward | Back (←Previous) |
|---|---|---|
| `loading` | → `intro` (automatic, when mask loads) | — |
| `intro` | → `examine` (click or drag on globe) | — |
| `examine` | → `explorer` (Make your own button) | → `intro` |
| `explorer` | → `revealed` (Absolute Wettest and Driest button) | → `intro` |
| `revealed` | → `detailed` (Details button) | → `explorer` |
| `detailed` | → `revealed` (Hide Details button) | → `explorer` |

The logo always returns to `intro` from any state. The `detailed` state is a panel overlay on top of `revealed`; the Details/Hide Details button toggles between them without back-navigation semantics.



## Known issues

**Line rendering artefacts near the poles (Mapbox GL JS bug).** When the globe is oriented to show either pole, lines passing near a pole may render with banded fuzziness at certain zoom levels, or as a large partial arc rather than a tight curve. This is a known, unresolved bug in Mapbox GL JS globe projection ([issue #12026](https://github.com/mapbox/mapbox-gl-js/issues/12026), open since June 2022). The root cause is that the renderer draws line segments as straight lines in projected tile space, which breaks down at extreme latitudes. No workaround is available within the current Mapbox API; the code passes correct densely-sampled GeoJSON and will render properly if/when Mapbox fixes the underlying issue.
