.PHONY: fmt lint test typecheck all release

PYTHON := $(if $(wildcard .ubuntu-venv/bin/python),.ubuntu-venv/bin/python,python)

fmt:
	$(PYTHON) -m ruff format .

lint:
	$(PYTHON) -m ruff check .


typecheck:
	$(PYTHON) -m mypy src


test:
	$(PYTHON) -m pytest

all: lint typecheck test

release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make release VERSION=0.5.2"; exit 1; fi
	$(PYTHON) tools/release.py $(VERSION)
