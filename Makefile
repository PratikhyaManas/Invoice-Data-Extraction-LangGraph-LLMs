.PHONY: install install-dev test lint format sast sca security security-ci sbom clean

PYTHON ?= python3
REPORTS_DIR ?= reports

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

test:
	pytest

lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/
	ruff check --fix src/ tests/

sast:
	bandit -c security/bandit.yaml -r src/
	semgrep scan --config security/semgrep.yml src/

sca:
	pip-audit -r requirements.txt
	safety check -r requirements.txt

security: sast sca

security-ci:
	REPORTS_DIR=$(REPORTS_DIR) ./security/run_security_scans.sh

sbom:
	cyclonedx-py requirements -o sbom.json requirements.txt

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info $(REPORTS_DIR) sbom.json
