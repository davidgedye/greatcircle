# Interactive Great Circle Explorer — Implementation Plan

## Overview

A new standalone `explorer.html` page — separate UX, separate identity from `index.html`.

Two modes:
- **Query mode**: Click two points on the globe → draw great circle → show land/water transitions + ocean fraction
- **Heatmap mode**: Browse a precomputed pole-space heatmap as a Mapbox raster layer

No live server. Everything is static files on GitHub Pages (tiles on CDN if zoom 8 needed later).

---

## Architecture

```
[ETOPO 2022 NetCDF]
       │
       ├──► make_binary_mask.py ──► explorer/mask_60s.bin.gz       (~6 MB, one-time download)
       │
       └──► make_explorer_heatmap.py ──► explorer/heatmap_5m.png   (2160×1080 uint8)
                                                │
                                         make_explorer_tiles.py
                                                │
                                         explorer/tiles/{z}/{x}/{y}.png  (zoom 0–7)
```

Client-side at query time:
1. Decompress mask in browser (DecompressionStream API)
2. Compute great circle normal from two clicked points (cross product)
3. Sample 21,600 points along circle (60 arc-second spacing)
4. Look up each point in mask (bit array lookup)
5. Find sign changes → transition coordinates + bearings
6. Render on map

---

## New Files

### Python scripts (in `experiments/wettest_driest/`)

| Script | Input | Output | Notes |
|--------|-------|--------|-------|
| `make_binary_mask.py` | ETOPO NetCDF + lakes mask | `explorer/mask_60s.bin.gz` | 21600×10800 packed bits, gzipped |
| `make_explorer_heatmap.py` | ETOPO NetCDF | `explorer/heatmap_5m.png` | 2160×1080 uint8 raster |
| `make_explorer_tiles.py` | `heatmap_5m.png` | `explorer/tiles/` | Zoom 0–7, coloured PNG tiles |

### Web files

| File | Purpose |
|------|---------|
| `explorer.html` | Standalone page — own UI, no relation to index.html |
| `explorer/mask_60s.bin.gz` | Binary land/ocean mask |
| `explorer/tiles/{z}/{x}/{y}.png` | Heatmap tile pyramid |

---

## Step 1: Binary Mask (`make_binary_mask.py`)

**Logic:**
- Load ETOPO 2022 NetCDF (same loader as existing pipeline)
- Apply HydroLAKES suppress-mode mask (same logic as `add_boundaries.py`) to remove lake-bed artefacts
- Threshold: `land = elevation > 0`
- Pack as bits: `numpy.packbits` on boolean array, row-major
- Row order: north-to-south (row 0 = 90°N), columns west-to-east (col 0 = −180°)
- Gzip output

**Output:** `explorer/mask_60s.bin.gz` — expected ~6 MB

**Bit layout:**
```
pixel(lat, lon):
  row = floor((90 - lat) * 60)        # 0..10799
  col = floor((lon + 180) * 60) % 21600
  bit_index = row * 21600 + col
  byte = mask[bit_index >> 3]
  bit  = (byte >> (7 - (bit_index & 7))) & 1
```

---

## Step 2: Heatmap Raster (`make_explorer_heatmap.py`)

**Pole grid:** 5 arc-minute resolution → 2160 columns × 1080 rows

**For each pole (theta, phi):**
- Generate great circle using same Gram-Schmidt method as `great_circles.py`
- Sample 360 points (1° path spacing) — sufficient for fraction accuracy at this pole resolution
- Look up each in binary mask (faster than ETOPO float lookup)
- Store ocean fraction as uint8 (0 = 0% ocean, 255 = 100% ocean)

**Compute time estimate:** 2.3M circles × 360 lookups ≈ 828M ops — a few minutes parallelised

**Antipodal symmetry:** pole at (θ, φ) and (π−θ, φ+π) give the same great circle — compute
one hemisphere, mirror the other to halve work.

**Output:** `explorer/heatmap_5m.npy` (intermediate) + `explorer/heatmap_5m.png` (uint8 grayscale)

---

## Step 3: Tile Generation (`make_explorer_tiles.py`)

**Input:** `heatmap_5m.png` (2160×1080 grayscale uint8)

**Process:**
- Apply colormap (to decide: red = driest → blue = wettest, or a new scheme)
- Generate XYZ tile pyramid — gdal2tiles or pure Python
- Zoom levels 0–7
- Output as PNG tiles with consistent colormap across all zoom levels

**Storage estimate:**
- Zoom 0–7: ~21,000 tiles × ~10 KB avg = ~200 MB — fits on GitHub Pages
- Zoom 8 if needed later (~65K more tiles): Cloudflare R2 free tier (10 GB)

**Output:** `explorer/tiles/{z}/{x}/{y}.png`

---

## Step 4: `explorer.html`

### Map setup
- Mapbox GL JS v3.3.0
- Globe projection
- Mode toggle: **Query** / **Heatmap**

### Layers

| Layer ID | Type | Purpose |
|----------|------|---------|
| `heatmap` | raster | Tile pyramid overlay (heatmap mode only) |
| `gc-line` | line | Great circle between two clicked points |
| `gc-points` | symbol | Point A and point B markers |
| `gc-transitions` | symbol | Land/water transition arrows |

### Query mode — interaction

**Click behaviour:** click N replaces click N−2 (rolling window of 2).
- `points = [A, B]`; click N sets `points[N % 2]`
- After first click: show point A only, no line yet
- After second click (and every subsequent pair): compute and render immediately

**On each update:**
1. Ensure mask is loaded (fetch + decompress on first use; show spinner if not ready)
2. Compute great circle, sample 21,600 points, find transitions
3. Update `gc-line`, `gc-points`, `gc-transitions` sources
4. Display fraction + transition count in HUD

**Result HUD:**
- Ocean fraction: `XX.X% ocean`
- Transition count
- Positioned to not obscure the globe

### Heatmap mode

- Show raster tile layer at ~60% opacity
- Hide query layers
- Show colour scale legend
- Pan/zoom to explore freely

### Mask loading (JS)

```javascript
async function loadMask() {
    const resp = await fetch('explorer/mask_60s.bin.gz');
    const ds = new DecompressionStream('gzip');
    const piped = resp.body.pipeThrough(ds);
    const buf = await new Response(piped).arrayBuffer();
    return new Uint8Array(buf);  // ~29 MB in RAM
}

function isLand(lat, lon, mask) {
    let col = Math.floor((lon + 180) * 60) % 21600;
    let row = Math.floor((90 - lat) * 60);
    row = Math.max(0, Math.min(10799, row));
    if (col < 0) col += 21600;
    const i = row * 21600 + col;
    return (mask[i >> 3] >> (7 - (i & 7))) & 1;
}
```

### Great circle math (JS)

```javascript
function toXYZ(lat, lon) {
    const φ = lat * Math.PI / 180, λ = lon * Math.PI / 180;
    return [Math.cos(φ)*Math.cos(λ), Math.cos(φ)*Math.sin(λ), Math.sin(φ)];
}

function cross(a, b) {
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
}

function norm(v) { const m = Math.hypot(...v); return v.map(x => x/m); }

function sampleGC(latA, lonA, latB, lonB, nPts = 21600) {
    const n = norm(cross(toXYZ(latA, lonA), toXYZ(latB, lonB)));
    const arb = Math.abs(n[0]) < 0.9 ? [1,0,0] : [0,1,0];
    const u = norm(cross(n, arb));
    const v = cross(n, u);  // already unit (n and u are perpendicular unit vectors)
    return Array.from({length: nPts}, (_, i) => {
        const t = 2 * Math.PI * i / nPts;
        const p = u.map((ui, j) => Math.cos(t)*ui + Math.sin(t)*v[j]);
        return {
            lat: Math.asin(Math.max(-1, Math.min(1, p[2]))) * 180/Math.PI,
            lon: Math.atan2(p[1], p[0]) * 180/Math.PI
        };
    });
}
```

### Transition detection (JS)

```javascript
function findTransitions(pts, mask) {
    const out = [];
    let prev = isLand(pts[0].lat, pts[0].lon, mask);
    for (let i = 1; i < pts.length; i++) {
        const curr = isLand(pts[i].lat, pts[i].lon, mask);
        if (curr !== prev) {
            const mid = {
                lat: (pts[i-1].lat + pts[i].lat) / 2,
                lon: (pts[i-1].lon + pts[i].lon) / 2
            };
            const bearing = bearingTo(pts[i-1], pts[i]);
            out.push({ ...mid, toLand: !!curr,
                       bearing: curr ? bearing : (bearing + 180) % 360 });
        }
        prev = curr;
    }
    return out;
}
```

---

## Step 5: Service Worker Update

- Add `explorer.html` and `explorer/mask_60s.bin.gz` to cache list
- Tiles cached lazily (network-first, same as existing SW strategy)
- Bump `CACHE_NAME` version

---

## Build Order

1. `make_binary_mask.py` — generate and verify mask (spot-check known coastlines)
2. `make_explorer_heatmap.py` — generate pole-space heatmap raster
3. `make_explorer_tiles.py` — generate tile pyramid
4. `explorer.html` — query mode first (mask load + GC math + transitions + HUD)
5. Add heatmap layer mode to `explorer.html`
6. Update `sw.js`

---

## Decisions

1. **Heatmap colormap**: same red→blue scheme as existing app.
2. **Transition markers**: bearing-rotated arrows pointing toward land, same style as existing app.
3. **Mask loading**: fetch immediately on page load in background; show "Loading..." in HUD until ready.
4. **Antipodal edge case**: silently pick an arbitrary perpendicular — no error message.
5. **GC line**: solid dark colour, zoom-dependent width interpolation matching `index.html`.
6. **Zoom 8 tiles**: defer — generate zoom 0–7 only for now.
