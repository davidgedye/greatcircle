ETOPO1     = ../../data/ETOPO1_Ice_c_gdal.grd
GEBCO      = ../../data/GEBCO/GEBCO_2025_sub_ice.nc
LAKES_SHP  = ../../data/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp
LAKES_MASK = ../../data/lakes_mask.npy
WORKERS    = 8
PTS        = 86400
WEBROOT    = ../..

all: $(WEBROOT)/gebco_visuals.json $(WEBROOT)/etopo1_visuals.json

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

# ── Boundaries ───────────────────────────────────────────────────────────────

results-with-boundaries.json: results.json add_boundaries.py
	python3 add_boundaries.py $(GEBCO) --lakes-mask $(LAKES_MASK) --pts $(PTS)
	cp results.json results-with-boundaries.json

etopo1-with-boundaries.json: etopo1.json add_boundaries.py
	python3 add_boundaries.py $(ETOPO1) --results etopo1.json
	cp etopo1.json etopo1-with-boundaries.json

# ── Visualisation ────────────────────────────────────────────────────────────

$(WEBROOT)/gebco_visuals.json $(WEBROOT)/gebco_details.json: results-with-boundaries.json visualize.py
	python3 visualize.py \
	    --output $(WEBROOT)/gebco_visuals.json \
	    --details-output $(WEBROOT)/gebco_details.json

$(WEBROOT)/etopo1_visuals.json $(WEBROOT)/etopo1_details.json: etopo1-with-boundaries.json visualize.py
	python3 visualize.py --input etopo1.json \
	    --output $(WEBROOT)/etopo1_visuals.json \
	    --details-output $(WEBROOT)/etopo1_details.json

# ── Helpers ──────────────────────────────────────────────────────────────────

# ETOPO1 search (for cross-dataset comparison and side-by-side visualisation)
etopo1.json: $(ETOPO1) great_circles.py
	python3 great_circles.py $(ETOPO1) \
	    --workers $(WORKERS) \
	    --output $@

# Cross-dataset comparison table
compare: etopo1.json results.json compare_datasets.py
	python3 compare_datasets.py $(ETOPO1) $(GEBCO) \
	    --label-a ETOPO1 --label-b GEBCO \
	    --results-a etopo1.json --results-b results.json \
	    --workers $(WORKERS)

.PHONY: all compare clean

clean:
	rm -f results.json results-with-boundaries.json etopo1-with-boundaries.json \
	      $(WEBROOT)/gebco_visuals.json $(WEBROOT)/gebco_details.json \
	      $(WEBROOT)/etopo1_visuals.json $(WEBROOT)/etopo1_details.json
