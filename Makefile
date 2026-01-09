.PHONY: fmt lint test typecheck all

fmt:
	ruff format .

lint:
	ruff check .


typecheck:
	mypy src


test:
	pytest

all: lint typecheck test
