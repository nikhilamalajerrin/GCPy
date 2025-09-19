# ---- Basic config ----
PY        := python
PIP       := pip
PACKAGE   := plancosts
ENTRY     := main.py

# Pass: make run ARGS="--tfjson test.json -o table"
ARGS ?=

# Dev tools
DEV_PKGS  := black isort ruff mypy pytest build wheel

.PHONY: deps run build clean test fmt lint typecheck check release help

help:
	@echo "make deps        - install dev dependencies"
	@echo "make run ARGS=…  - run main.py with ARGS (e.g. --tfjson test.json -o table)"
	@echo "make build       - build sdist+wheel into dist/"
	@echo "make release     - package artifacts from dist/ into release/ tarball(s)"
	@echo "make clean       - remove build artifacts"
	@echo "make test        - run pytest"
	@echo "make fmt         - run black + isort"
	@echo "make lint        - run ruff"
	@echo "make typecheck   - run mypy"
	@echo "make check       - fmt + lint + typecheck + tests"

deps:
	$(PIP) install -U pip
	$(PIP) install -U $(DEV_PKGS)

run:
	$(PY) $(ENTRY) $(ARGS)

# Build sdist + wheel (requires pyproject.toml/setup)
build:
	$(PY) -m build

# Make a clean tree
clean:
	find . -name "__pycache__" -type d -exec rm -rf {} +
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	rm -rf release

test:
	pytest -q

fmt:
	black .
	isort .

lint:
	ruff check .

typecheck:
	# Avoid hard failure on missing typing config
	mypy $(PACKAGE) || true

check: fmt lint typecheck test

# -------- Release (Infracost-style packing) --------
# Creates tarballs under release/ from dist/ artifacts.
# Names include detected version (or 'dev' fallback).
release: build
	@mkdir -p release
	@V="`$(PY) - <<'PY'\ntry:\n import importlib\n m=importlib.import_module('$(PACKAGE)'); print(getattr(m,'__version__',''))\nexcept Exception:\n print('')\nPY`"; \
	[ -n "$$V" ] || V=dev; \
	echo "Packaging $(PACKAGE) version: $$V"; \
	for a in dist/*; do \
	  bn=$$(basename "$$a"); \
	  tarname="release/$(PACKAGE)-$${V}-$${bn}.tar.gz"; \
	  echo "  -> $$tarname"; \
	  tar -czf "$$tarname" -C dist "$$bn"; \
	  shasum -a 256 "$$tarname" > "$$tarname.sha256" 2>/dev/null || sha256sum "$$tarname" > "$$tarname.sha256"; \
	done
	@ls -lh release/
