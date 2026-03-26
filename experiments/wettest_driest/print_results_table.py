"""Print the README results table from etopo.json."""
import json
import subprocess
from datetime import date


def best(exp):
    b = exp['fine'][0]
    off = b['offsets_deg']
    t = b['theta_center_deg'] + off[b['best_i']]
    p = b['phi_center_deg']   + off[b['best_j']]
    return b['best_frac'], t, p


def row(dataset, kind, frac, t, p):
    lat = 90 - t
    lon = p
    lat_s = f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}"
    lon_s = f"{abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"
    score = f"**{frac*100:.2f}% ocean**" if kind == 'Wettest' else f"**{(1-frac)*100:.2f}% land**"
    print(f"| **{dataset}** | {kind} | {lat_s} {lon_s} | {score} |")


e = json.load(open('etopo.json'))

commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
today  = date.today().isoformat()

print("| Dataset | | Pole location | Score |")
print("|---|---|---|---|")
row('ETOPO 2022', 'Wettest', *best(e['wettest']))
row('ETOPO 2022', 'Driest',  *best(e['driest']))
print()
print(f"*Results as of {today} (commit {commit})*")
