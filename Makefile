GEBCO      = data/GEBCO_2025_sub_ice.nc
LAKES_SHP  = data/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp
LAKES_MASK = data/lakes_mask.npy
WORKERS    = 8
PTS        = 86400

all: visuals.json

# ── Preprocessing ────────────────────────────────────────────────────────────

$(LAKES_MASK): $(GEBCO) $(LAKES_SHP) make_lakes_mask.py
	python3 make_lakes_mask.py $(GEBCO) $(LAKES_SHP) $(LAKES_MASK)

# ── Search ───────────────────────────────────────────────────────────────────

wettest-driest.json: $(GEBCO) great_circles.py
	python3 great_circles.py $(GEBCO) \
	    --workers $(WORKERS) --pts $(PTS) \
	    --output $@

wettest-driest-including-lakes.json: $(GEBCO) $(LAKES_MASK) great_circles.py
	python3 great_circles.py $(GEBCO) \
	    --lakes-mask $(LAKES_MASK) \
	    --workers $(WORKERS) --pts $(PTS) \
	    --output $@

# ── Merge ────────────────────────────────────────────────────────────────────

results.json: wettest-driest.json wettest-driest-including-lakes.json
	python3 -c "\
import json; \
a = json.load(open('wettest-driest.json')); \
b = json.load(open('wettest-driest-including-lakes.json')); \
a.update(b); \
json.dump(a, open('results.json', 'w'))"

# ── Visualisation ────────────────────────────────────────────────────────────

visuals.json: results.json visualize.py
	python3 visualize.py

# ── Helpers ──────────────────────────────────────────────────────────────────

# Rebuild only the oceans-only results and regenerate visuals (skips lakes)
oceans-only: wettest-driest.json
	python3 visualize.py

.PHONY: all oceans-only clean

clean:
	rm -f results.json visuals.json
