.PHONY: fmt lint test typecheck all release

fmt:
	ruff format .

lint:
	ruff check .


typecheck:
	mypy src


test:
	pytest

all: lint typecheck test

release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make release VERSION=0.5.2"; exit 1; fi
	python tools/release.py $(VERSION)
