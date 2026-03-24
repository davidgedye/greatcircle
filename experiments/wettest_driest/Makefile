ETOPO      = ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc
GEBCO      = ../../data/GEBCO/GEBCO_2025_sub_ice.nc
LAKES_SHP  = ../../data/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp
LAKES_MASK       = ../../data/lakes_mask.npy
ETOPO_LAKES_MASK = ../../data/etopo_lakes_mask.npy
WORKERS    = 8
PTS        = 86400
all: gebco_visuals.json etopo_visuals.json

# ── Preprocessing ────────────────────────────────────────────────────────────

$(LAKES_MASK): $(GEBCO) $(LAKES_SHP) make_lakes_mask.py
	python3 make_lakes_mask.py $(GEBCO) $(LAKES_SHP) $(LAKES_MASK)

$(ETOPO_LAKES_MASK): $(ETOPO) $(LAKES_SHP) make_lakes_mask.py
	python3 make_lakes_mask.py $(ETOPO) $(LAKES_SHP) $(ETOPO_LAKES_MASK)

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

gebco.json: wettest-driest.json wettest-driest-including-lakes.json
	python3 -c "\
import json; \
a = json.load(open('wettest-driest.json')); \
b = json.load(open('wettest-driest-including-lakes.json')); \
a.update(b); \
json.dump(a, open('gebco.json', 'w'))"

# ── Boundaries ───────────────────────────────────────────────────────────────

gebco-with-boundaries.json: gebco.json add_boundaries.py
	python3 add_boundaries.py $(GEBCO) --lakes-mask $(LAKES_MASK) --pts $(PTS)
	cp gebco.json gebco-with-boundaries.json

etopo-with-boundaries.json: etopo.json $(ETOPO_LAKES_MASK) add_boundaries.py
	python3 add_boundaries.py $(ETOPO) --results etopo.json --lakes-mask $(ETOPO_LAKES_MASK)
	cp etopo.json etopo-with-boundaries.json

# ── Visualisation ────────────────────────────────────────────────────────────

gebco_visuals.json gebco_details.json: gebco-with-boundaries.json visualize.py
	python3 visualize.py

etopo_visuals.json etopo_details.json: etopo-with-boundaries.json visualize.py
	python3 visualize.py --input etopo.json \
	    --output etopo_visuals.json \
	    --details-output etopo_details.json

# ── Helpers ──────────────────────────────────────────────────────────────────

# ETOPO search (for cross-dataset comparison and side-by-side visualisation)
etopo.json: $(ETOPO) great_circles.py
	python3 great_circles.py $(ETOPO) \
	    --workers $(WORKERS) \
	    --output $@

# Cross-dataset comparison table
compare: etopo.json gebco.json compare_datasets.py
	python3 compare_datasets.py $(ETOPO) $(GEBCO) \
	    --label-a ETOPO --label-b GEBCO \
	    --results-a etopo.json --results-b gebco.json \
	    --workers $(WORKERS)

# Print the README results table from current JSON outputs
results-table:
	@python3 print_results_table.py

.PHONY: all compare results-table clean

clean:
	rm -f gebco.json gebco-with-boundaries.json etopo-with-boundaries.json \
	      gebco_visuals.json gebco_details.json \
	      etopo_visuals.json etopo_details.json
