"""
visualize.py — Read results.json and write visuals.json for the interactive globe.

Usage:
    python3 visualize.py
"""

import json
import numpy as np


# Metadata for each experiment key: display label, whether to invert (show as % land),
# and default colours for coarse layers.  Extend when new experiments are added.
EXPERIMENT_META = {
    "wettest":       dict(label="Wettest (oceans only)",    invert=False,
                          color_fine="#00e5ff", color_best="#29b6f6", color_coarse="#1565c0"),
    "driest":        dict(label="Driest (oceans only)",     invert=True,
                          color_fine="#ff1744", color_best="#ff6d00", color_coarse="#7f0000"),
    "wettest-lakes": dict(label="Wettest (oceans & lakes)", invert=False,
                          color_fine="#00e5ff", color_best="#29b6f6", color_coarse="#1565c0"),
    "driest-lakes":  dict(label="Driest (oceans & lakes)",  invert=True,
                          color_fine="#ff1744", color_best="#ff6d00", color_coarse="#7f0000"),
}

zoom_fine   = ['interpolate', ['exponential', 2], ['zoom'], 0, 4,   5, 4,   10, 130]
zoom_best   = ['interpolate', ['exponential', 2], ['zoom'], 0, 2.5, 5, 2.5, 10, 80]
zoom_others = ['interpolate', ['exponential', 2], ['zoom'], 0, 1,   5, 1,   10, 30]


# ---------- Load results ----------

def load_results():
    import os, sys
    if not os.path.exists('results.json'):
        print('ERROR: results.json not found — run great_circles.py first.')
        sys.exit(1)
    with open('results.json') as f:
        return json.load(f)


def best_fine_result(grid_info):
    """Extract (theta_deg, phi_deg, frac) for the best point in a fine grid entry."""
    g = grid_info
    theta = g['theta_center_deg'] + g['offsets_deg'][g['best_i']]
    phi   = g['phi_center_deg']   + g['offsets_deg'][g['best_j']]
    return (round(theta, 4), round(phi, 4), g['best_frac'])


# ---------- Geometry ----------

def great_circle_coords(theta_deg, phi_deg, n_pts=360):
    theta = np.radians(theta_deg)
    phi   = np.radians(phi_deg)
    n = np.array([np.sin(theta)*np.cos(phi), np.sin(theta)*np.sin(phi), np.cos(theta)])
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref); u /= np.linalg.norm(u)
    v = np.cross(n, u)

    t   = np.linspace(0, 2*np.pi, n_pts, endpoint=False)
    pts = np.outer(np.cos(t), u) + np.outer(np.sin(t), v)
    lat = np.degrees(np.arcsin(np.clip(pts[:, 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(pts[:, 1], pts[:, 0]))

    coords = [[round(float(lon[i]), 4), round(float(lat[i]), 4)] for i in range(n_pts)]
    coords.append(coords[0])
    return coords


def unwrap_coords(coords):
    """Unwrap longitudes so consecutive values never jump by more than 180°."""
    result = [coords[0]]
    for c in coords[1:]:
        prev_lon = result[-1][0]
        lon = c[0]
        diff = lon - prev_lon
        if diff > 180:   lon -= 360
        elif diff < -180: lon += 360
        result.append([lon, c[1]])
    return result


def make_geojson(circles, rank_label, invert=False):
    features = []
    for i, (theta, phi, frac) in enumerate(circles):
        coords = unwrap_coords(great_circle_coords(theta, phi))
        geom   = {'type': 'LineString', 'coordinates': coords}
        display_val = (1 - frac) if invert else frac
        display_lbl = f'{display_val*100:.2f}% {"land" if invert else "ocean"}'
        features.append({
            'type': 'Feature',
            'properties': {
                'label':     rank_label(i),
                'ocean_pct': display_lbl,
                'theta':     round(theta, 3),
                'phi':       round(phi, 3),
            },
            'geometry': geom,
        })
    return {'type': 'FeatureCollection', 'features': features}


# ---------- Build layers for one experiment ----------

def layers_for_experiment(key, exp_results):
    meta = EXPERIMENT_META.get(key, {
        'label': key, 'invert': False,
        'color_fine': '#00e5ff', 'color_best': '#aaaaaa', 'color_coarse': '#444444',
    })
    invert = meta['invert']

    coarse = [tuple(r) for r in exp_results['coarse']]
    has_fine = 'fine' in exp_results
    if has_fine:
        fine = [best_fine_result(g) for g in exp_results['fine']]
    else:
        fine = coarse[:1]

    def pct(frac):
        v = (1 - frac) if invert else frac
        return f'{v*100:.2f}% {"land" if invert else "ocean"}'

    return [
        dict(id=f'{key}-coarse',
             label=f'{meta["label"]} top 10 (coarse)',
             color=meta['color_coarse'], width=zoom_others, opacity=0.40, dashed=False, visible=False,
             geojson=make_geojson(coarse, lambda i: f'{meta["label"]} #{i+1} (coarse)', invert=invert)),
        dict(id=f'{key}-coarse-best',
             label=f'{meta["label"]} best (coarse) — {pct(coarse[0][2])}',
             color=meta['color_best'], width=zoom_best, opacity=0.75, dashed=False, visible=False,
             geojson=make_geojson(coarse[:1], lambda i: f'{meta["label"]} best (coarse)', invert=invert)),
        dict(id=f'{key}-fine',
             label=f'{meta["label"]} best (fine) — {pct(fine[0][2])}',
             color=meta['color_fine'], width=zoom_fine, opacity=0.85, dashed=False, visible=True,
             geojson=make_geojson(fine[:1], lambda i: f'{meta["label"]} best (fine)', invert=invert)),
    ]


# ---------- Output ----------

def write_visuals_json(layers, fine_grids):
    payload = {
        'layers':     {l['id']: l['geojson'] for l in layers},
        'layer_meta': [{k: v for k, v in l.items() if k != 'geojson'} for l in layers],
        'fine_grids': fine_grids,
    }
    with open('visuals.json', 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f'Written to visuals.json ({len(json.dumps(payload, separators=(",", ":"))) // 1024} KB)')


if __name__ == '__main__':
    results = load_results()

    layers = []
    fine_grids = {}

    for key, exp_results in results.items():
        layers.extend(layers_for_experiment(key, exp_results))
        if 'fine' in exp_results:
            fine_grids[key] = exp_results['fine'][0]

    if not fine_grids:
        print('No fine results in results.json — heatmaps will be hidden')
        fine_grids = None

    write_visuals_json(layers, fine_grids)
