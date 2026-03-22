"""
visualize.py — Read results.json and write data.json for the interactive globe.

Usage:
    python3 visualize.py
"""

import json
import numpy as np


# ---------- Load results from results.json ----------

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
    """Unwrap longitudes so consecutive values never jump by more than 180°.
    This keeps the line continuous across the antimeridian on a globe projection."""
    result = [coords[0]]
    for c in coords[1:]:
        prev_lon = result[-1][0]
        lon = c[0]
        diff = lon - prev_lon
        if diff > 180:
            lon -= 360
        elif diff < -180:
            lon += 360
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


# ---------- Data ----------

def fine_grids_from_results(results):
    """Extract the best fine grid for each category, for heatmap rendering."""
    wet = results.get('wettest', {}).get('fine')
    dry = results.get('driest',  {}).get('fine')
    if not wet or not dry:
        return None
    return {'wettest': wet[0], 'driest': dry[0]}


def write_data_json(layers, fine_grids):
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

    wet_coarse = [tuple(r) for r in results['wettest']['coarse']]
    dry_coarse = [tuple(r) for r in results['driest']['coarse']]

    has_fine = 'fine' in results['wettest'] and 'fine' in results['driest']
    if has_fine:
        wet_fine = [best_fine_result(g) for g in results['wettest']['fine']]
        dry_fine = [best_fine_result(g) for g in results['driest']['fine']]
    else:
        wet_fine = wet_coarse[:1]
        dry_fine = dry_coarse[:1]

    def pct(frac, invert=False):
        v = (1 - frac) if invert else frac
        suffix = 'land' if invert else 'ocean'
        return f'{v*100:.2f}% {suffix}'

    zoom_fine   = ['interpolate', ['exponential', 2], ['zoom'], 0, 4,   5, 4,   10, 130]
    zoom_best   = ['interpolate', ['exponential', 2], ['zoom'], 0, 2.5, 5, 2.5, 10, 80]
    zoom_others = ['interpolate', ['exponential', 2], ['zoom'], 0, 1,   5, 1,   10, 30]

    layers = [
        dict(id='wettest-coarse',
             label='Wettest top 10 (coarse)',
             color='#1565c0', width=zoom_others, opacity=0.40, dashed=False, visible=False,
             geojson=make_geojson(wet_coarse, lambda i: f'Wettest #{i+1} (coarse)')),
        dict(id='wettest-coarse-best',
             label=f'Wettest best (coarse) — {pct(wet_coarse[0][2])}',
             color='#29b6f6', width=zoom_best, opacity=0.75, dashed=False, visible=False,
             geojson=make_geojson(wet_coarse[:1], lambda i: 'Wettest best (coarse)')),
        dict(id='wettest-fine',
             label=f'Wettest best (fine) — {pct(wet_fine[0][2])}',
             color='#00e5ff', width=zoom_fine, opacity=0.85, dashed=False, visible=True,
             geojson=make_geojson(wet_fine[:1], lambda i: 'Wettest best (fine)')),
        dict(id='driest-coarse',
             label='Driest top 10 (coarse)',
             color='#7f0000', width=zoom_others, opacity=0.40, dashed=False, visible=False,
             geojson=make_geojson(dry_coarse, lambda i: f'Driest #{i+1} (coarse)', invert=True)),
        dict(id='driest-coarse-best',
             label=f'Driest best (coarse) — {pct(dry_coarse[0][2], invert=True)}',
             color='#ff6d00', width=zoom_best, opacity=0.75, dashed=False, visible=False,
             geojson=make_geojson(dry_coarse[:1], lambda i: 'Driest best (coarse)', invert=True)),
        dict(id='driest-fine',
             label=f'Driest best (fine) — {pct(dry_fine[0][2], invert=True)}',
             color='#ff1744', width=zoom_fine, opacity=0.85, dashed=False, visible=True,
             geojson=make_geojson(dry_fine[:1], lambda i: 'Driest best (fine)', invert=True)),
    ]

    fine_grids = fine_grids_from_results(results)
    if not fine_grids:
        print('No fine results in results.json — heatmaps will be hidden')

    write_data_json(layers, fine_grids)
