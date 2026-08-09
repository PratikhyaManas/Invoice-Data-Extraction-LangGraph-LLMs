#!/usr/bin/env bash
# Run all SAST + SCA scans locally and print a consolidated summary.
#
# Usage:
#   ./security/run_security_scans.sh            # human-readable, exits non-zero on findings
#   REPORTS_DIR=reports ./security/run_security_scans.sh   # also writes machine-readable reports

set -uo pipefail

REPORTS_DIR="${REPORTS_DIR:-}"
STATUS=0

echo "== SAST: bandit =="
if [ -n "$REPORTS_DIR" ]; then
  mkdir -p "$REPORTS_DIR"
  bandit -c security/bandit.yaml -r src/ -f json -o "$REPORTS_DIR/bandit.json" || STATUS=1
  bandit -c security/bandit.yaml -r src/ || true
else
  bandit -c security/bandit.yaml -r src/ || STATUS=1
fi

echo
echo "== SAST: semgrep =="
if [ -n "$REPORTS_DIR" ]; then
  semgrep scan --config security/semgrep.yml src/ --sarif -o "$REPORTS_DIR/semgrep.sarif" || STATUS=1
  semgrep scan --config security/semgrep.yml src/ || true
else
  semgrep scan --config security/semgrep.yml src/ || STATUS=1
fi

echo
echo "== SCA: pip-audit =="
if [ -n "$REPORTS_DIR" ]; then
  pip-audit -r requirements.txt -f json -o "$REPORTS_DIR/pip-audit.json" || STATUS=1
  pip-audit -r requirements.txt || true
else
  pip-audit -r requirements.txt || STATUS=1
fi

echo
echo "== SCA: safety =="
if [ -n "$REPORTS_DIR" ]; then
  safety check -r requirements.txt --json --output "$REPORTS_DIR/safety.json" || STATUS=1
  safety check -r requirements.txt || true
else
  safety check -r requirements.txt || STATUS=1
fi

echo
echo "== SBOM: cyclonedx =="
if [ -n "$REPORTS_DIR" ]; then
  cyclonedx-py requirements -o "$REPORTS_DIR/sbom.json" requirements.txt || STATUS=1
else
  cyclonedx-py requirements -o sbom.json requirements.txt || STATUS=1
fi

echo
if [ "$STATUS" -eq 0 ]; then
  echo "All security scans passed."
else
  echo "One or more security scans reported findings. Review output above."
fi

exit "$STATUS"
