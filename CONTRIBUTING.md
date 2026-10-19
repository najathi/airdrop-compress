# Contributing to AirDrop Compress

Thanks for helping. Bug reports, documentation fixes, plugins and code are all welcome.

## Ways to contribute

- **Report a bug:** use the [bug report form](https://github.com/najathi/airdrop-compress/issues/new?template=bug_report.yml). Include your macOS version, the app version and log lines (with private file names removed).
- **Suggest a feature:** use the [feature request form](https://github.com/najathi/airdrop-compress/issues/new?template=feature_request.yml).
- **Build a plugin:** see the [Plugin guide](docs/PLUGINS.md). You don't need to change the app.
- **Security issues:** please report them privately. See [SECURITY.md](SECURITY.md).

## Development setup

```bash
git clone https://github.com/najathi/airdrop-compress.git
cd airdrop-compress
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Run the app from source with a **separate profile**, so your real settings and AirDrop folder are untouched:

```bash
AIRDROP_COMPRESS_HOME=/tmp/adc-dev AIRDROP_DIR=/tmp/adc-inbox .venv/bin/python -m airdrop_compress gui
```

Copy files into `/tmp/adc-inbox` to see them processed.

## Tests and checks

```bash
.venv/bin/python -m pytest              # all tests (needs macOS: uses sandbox-exec, textutil, xattr)
.venv/bin/python -m pyflakes airdrop_compress tests
.venv/bin/pip-audit -r requirements.txt  # known vulnerabilities in dependencies
```

The CI workflow runs the tests on every pull request.

## Guidelines

- **Keep it working.** Build on the existing structure (see [Architecture](docs/ARCHITECTURE.md)). Avoid rewrites.
- **Originals are sacred.** Never modify, move or delete a received file.
- **Untrusted input.** Received files can come from strangers. New parsers belong in the sandbox (see `airdrop_compress/sandbox.py` and `processors/document_worker.py`).
- **No shell.** Run external programs with absolute paths and argument lists.
- **Tests** for every bug fix and feature. Use the `AIRDROP_COMPRESS_HOME` and `AIRDROP_DIR` fixtures; tests must never touch real user folders.
- **Docs.** Update `docs/` (and `CHANGELOG.md`) when behaviour changes. Only document what's implemented.
- **Style.** Match the surrounding code. The UI is plain HTML/CSS/JS in `airdrop_compress/ui/web/`, with no build step and no external resources.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change, with tests.
3. Run the tests and linters above.
4. Open a pull request using the template, describing what changed and how you tested it.

By contributing, you agree that your contributions are licensed under the [MIT licence](LICENSE).
