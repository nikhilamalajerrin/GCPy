# ---- Basic config ----
PY := python
PIP := pip
PACKAGE := plancosts
ENTRY := main.py

# You can pass extra args to "make run" like:
#   make run ARGS="--plan test_plan.json --output table"
ARGS ?=

# ---- Dev tools (adjust if you use Poetry/uv/etc.) ----
# Install once: make deps
DEV_PKGS := black isort flake8 mypy pytest

.PHONY: deps run build clean test fmt lint typecheck check help

help:
	@echo "make deps        - install dev dependencies"
	@echo "make run ARGS=…  - run main.py with ARGS (e.g. --plan test_plan.json)"
	@echo "make build       - build a wheel in dist/"
	@echo "make clean       - remove build artifacts"
	@echo "make test        - run pytest"
	@echo "make fmt         - run black + isort"
	@echo "make lint        - run flake8"
	@echo "make typecheck   - run mypy"
	@echo "make check       - fmt + lint + typecheck + tests"

deps:
	$(PIP) install -U pip wheel build
	$(PIP) install -U $(DEV_PKGS)

run:
	$(PY) $(ENTRY) $(ARGS)

# If you have pyproject.toml, this builds a wheel/sdist
build:
	$(PY) -m build

clean:
	find . -name '__pycache__' -type d -exec rm -rf {} +
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache

test:
	pytest -q

fmt:
	black .
	isort .

deps:
	$(PIP) install -U pip wheel build
	$(PIP) install -U black isort ruff mypy pytest

lint:
	ruff check .

typecheck:
	mypy $(PACKAGE) || true

check: fmt lint typecheck test
