ETOPO   = ../../data/ETOPO_2022_v1_60s_N90W180_surface.nc
WORKERS = 8

all: etopo_visuals.json

# ── Search ───────────────────────────────────────────────────────────────────

etopo.json: $(ETOPO) great_circles.py
	python3 great_circles.py $(ETOPO) \
	    --workers $(WORKERS) \
	    --output $@

# ── Visualisation ─────────────────────────────────────────────────────────────

etopo_visuals.json etopo_details.json: etopo.json visualize.py
	python3 visualize.py

# ── Helpers ──────────────────────────────────────────────────────────────────

results-table:
	@python3 print_results_table.py

.PHONY: all results-table clean

clean:
	rm -f etopo.json etopo_visuals.json etopo_details.json
