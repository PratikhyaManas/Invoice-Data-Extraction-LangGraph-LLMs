# Security Tooling

This project ships with both **SAST** (Static Application Security Testing)
and **SCA** (Software Composition Analysis) baked into local dev and CI.
Nothing here calls out to a paid service — everything runs with
open-source tools so it works the same on a laptop, in GitHub Actions,
or as a pre-deploy check in a Databricks CI/CD pipeline.

## SAST — Static Application Security Testing

Scans the pipeline's own source code for insecure patterns (eval/exec,
SQL built from f-strings, hardcoded secrets, unsafe deserialization,
etc.) without executing it.

| Tool      | What it checks                                            | Config                     |
|-----------|------------------------------------------------------------|-----------------------------|
| `bandit`  | Python-specific security anti-patterns (AST-based)         | `security/bandit.yaml`      |
| `semgrep` | Broader pattern-based rules + project-specific custom rules | `security/semgrep.yml`      |
| `ruff` (S-rules) | Lightweight flake8-bandit checks at lint time, fast feedback in the editor | `pyproject.toml` (`[tool.ruff.lint] select = [..., "S"]`) |

Run locally:

```bash
pip install -r requirements-dev.txt

bandit -c security/bandit.yaml -r src/
semgrep scan --config security/semgrep.yml src/
ruff check src/
```

## SCA — Software Composition Analysis

Scans the project's **third-party dependencies** (everything in
`requirements.txt`) for known CVEs, and generates a Software Bill of
Materials (SBOM) for audit/compliance purposes.

| Tool         | What it checks                                   |
|--------------|---------------------------------------------------|
| `pip-audit`  | Cross-references pinned versions against the OSV/PyPI advisory database |
| `safety`     | Cross-references pinned versions against the Safety DB (secondary source, catches things pip-audit misses) |
| `cyclonedx-bom` | Generates a CycloneDX SBOM (`sbom.json`) for supply-chain audit trails |

Run locally:

```bash
pip install -r requirements-dev.txt

pip-audit -r requirements.txt
safety check -r requirements.txt
cyclonedx-py requirements -o sbom.json requirements.txt
```

## Running everything at once

```bash
make security       # SAST + SCA, human-readable output
make security-ci     # same, but writes machine-readable reports to reports/
```

## CI enforcement

`.github/workflows/security.yml` runs on every push and pull request:

1. `bandit` and `semgrep` (SAST) — fails the build on medium+ severity findings.
2. `pip-audit` and `safety` (SCA) — fails the build on any known-vulnerable pinned dependency.
3. Uploads a CycloneDX SBOM and the SARIF-format bandit/semgrep reports as
   build artifacts (SARIF also renders directly in the GitHub Security tab
   if the repo has code scanning enabled).

## Triage policy

* No global suppressions. Any finding that is a false positive gets an
  inline `# nosec <bandit-rule-id> - <reason>` (bandit) or
  `# nosemgrep: <rule-id>` (semgrep) comment at the specific line, so
  the justification is reviewable in the diff.
* Dependency CVEs are triaged within 5 business days of the CI report;
  if a fix isn't yet available upstream, the exception and mitigating
  control are documented in `security/EXCEPTIONS.md` (create this file
  the first time you need it — none exist yet on a fresh checkout).
* Secrets (API keys, tokens) are never stored in this repo. Use
  Databricks secret scopes (`dbutils.secrets.get(scope, key)`) and
  reference the scope/key names via `PipelineConfig`, never the literal
  value.
