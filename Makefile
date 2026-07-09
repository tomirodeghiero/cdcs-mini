# cdcs — developer workflow.
# Every target runs through `uv run`, so the locked dev env is the source of
# truth. Use `make install` once after cloning; everything else is on demand.

UV ?= uv
SRC := src tests web api
YAML_PATHS := .yamllint .github

.DEFAULT_GOAL := help

TS_RUNTIME_DIR := ts-runtime

# Branch-coverage floor. Current baseline is ~81%; bumped to 85% after
# the cli refactor moves untestable rich-rendering code behind a Protocol.
COVERAGE_MIN ?= 80

.PHONY: help install lock sync lint format format-check typecheck test test-fast \
        coverage coverage-html yaml complexity maintainability quality clean \
        ts-install ts-test ts-lint ts-typecheck ts-quality

help:  ## List available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: sync  ## Alias for `sync` — first-time setup after clone

lock:  ## Regenerate uv.lock from pyproject.toml
	$(UV) lock

sync:  ## Install/refresh the locked dev environment
	$(UV) sync

lint:  ## Ruff lint (no autofix)
	$(UV) run ruff check $(SRC)

format:  ## Ruff format (writes changes)
	$(UV) run ruff format $(SRC)

format-check:  ## Ruff format in check mode (CI)
	$(UV) run ruff format --check $(SRC)

typecheck:  ## mypy --strict
	$(UV) run mypy --strict $(SRC)

test:  ## Full pytest suite
	$(UV) run pytest

test-fast:  ## pytest stopping on first failure
	$(UV) run pytest -x --ff

coverage:  ## pytest with coverage, enforcing COVERAGE_MIN (default $(COVERAGE_MIN)%)
	$(UV) run pytest \
	    --cov=src/cdcs \
	    --cov-report=term-missing \
	    --cov-fail-under=$(COVERAGE_MIN)

coverage-html:  ## pytest with coverage and HTML report under out/coverage-html/
	$(UV) run pytest \
	    --cov=src/cdcs \
	    --cov-report=term-missing \
	    --cov-report=html \
	    --cov-fail-under=$(COVERAGE_MIN)

yaml:  ## yamllint over project YAML
	@if find $(YAML_PATHS) -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null | grep -q .; then \
		$(UV) run yamllint -s $(YAML_PATHS); \
	else \
		echo "yaml: no YAML files found under $(YAML_PATHS) — skipping"; \
	fi

complexity:  ## Cyclomatic complexity report (radon cc)
	$(UV) run radon cc -a -s src web api

maintainability:  ## Maintainability index (radon mi)
	$(UV) run radon mi -s src web api

quality: lint format-check typecheck yaml coverage  ## Everything CI runs (Python side)

# --- ts-runtime (Node workspace) -----------------------------------
ts-install:  ## Install the ts-runtime Node workspace
	cd $(TS_RUNTIME_DIR) && npm install

ts-test:  ## Run vitest in ts-runtime
	cd $(TS_RUNTIME_DIR) && npm run test

ts-lint:  ## eslint over ts-runtime
	cd $(TS_RUNTIME_DIR) && npm run lint

ts-typecheck:  ## tsc --noEmit over ts-runtime
	cd $(TS_RUNTIME_DIR) && npm run typecheck

ts-quality:  ## typecheck + lint + format:check + vitest in ts-runtime
	cd $(TS_RUNTIME_DIR) && npm run quality

clean:  ## Remove tooling caches and build artefacts
	rm -rf .mypy_cache .pytest_cache .ruff_cache build dist *.egg-info
	rm -rf $(TS_RUNTIME_DIR)/dist $(TS_RUNTIME_DIR)/dist-test
