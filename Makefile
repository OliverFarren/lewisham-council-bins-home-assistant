UV ?= uv
INTEGRATION := custom_components/lewisham_council_bins

.DEFAULT_GOAL := help

.PHONY: help setup format lint typecheck test check

help:
	@echo "Development commands:"
	@echo "  make setup      Install the locked development dependencies"
	@echo "  make format     Fix lint and formatting issues"
	@echo "  make lint       Check linting and formatting"
	@echo "  make typecheck  Run mypy"
	@echo "  make test       Run tests with the CI coverage threshold"
	@echo "  make check      Run every check performed by Python CI"

setup:
	$(UV) sync --group dev --locked

format:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy $(INTEGRATION)/

test:
	$(UV) run pytest -v \
		--cov=$(INTEGRATION) \
		--cov-branch \
		--cov-report=xml \
		--cov-fail-under=96

check: lint typecheck test
