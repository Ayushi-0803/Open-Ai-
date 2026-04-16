PYTHON ?= python3
VENV ?= .venv

.PHONY: install-dev test test-unit test-integration lint compile clean

$(VENV)/bin/activate: requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -U pip
	$(VENV)/bin/pip install -r requirements-dev.txt

install-dev: $(VENV)/bin/activate

test: install-dev
	$(VENV)/bin/pytest --cov=.codex/scripts --cov-report=term-missing

test-unit: install-dev
	$(VENV)/bin/pytest -m "not integration" --cov=.codex/scripts --cov-report=term-missing

test-integration: install-dev
	$(VENV)/bin/pytest -m integration

lint: install-dev
	$(VENV)/bin/bandit -q -r .codex/scripts

coverage: install-dev
	$(VENV)/bin/pytest --cov=.codex/scripts --cov-branch --cov-report=term-missing --cov-report=html
	@echo "HTML coverage report: htmlcov/index.html"

compile:
	$(PYTHON) -m compileall .codex/scripts

clean:
	rm -rf .venv .pytest_cache .coverage
