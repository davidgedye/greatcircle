about.html: README.md build_about.py
	python3 build_about.py

.PHONY: about
about: about.html
