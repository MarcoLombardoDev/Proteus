**Proteus — Rebranding Tool.** Carries a corporate rebranding through an organisation's
files: it finds the files still carrying the old logo, pairs each one with the most
suitable replacement, shows a before/after preview of every pairing, and overwrites them
atomically with recoverable backups.

- **Finds** by name, by visual similarity, and inside Office documents and PDFs — pictures
  no wildcard would ever reach.
- **Never writes silently** — a dry run by default, an explicit `--apply`, and a refusal
  (exit code 4) rather than a guess when a match falls below the similarity threshold.
- **Interface and command line in one binary** — double-click for the GUI, or
  `--help` from a terminal for scheduled and unattended runs.
- **Bilingual** — English and Italian, switchable at runtime.

## Download

| Platform | File |
|---|---|
| Windows (x64) | `Proteus-{{VERSION}}-windows-x64.zip` |
| macOS (Apple silicon) | `Proteus-{{VERSION}}-macos-arm64.zip` |
| Linux (x64) | `Proteus-{{VERSION}}-linux-x64.tar.gz` |

Each archive is built on that platform's own runner — no cross-compilation, no emulation.
Unpack and run: no installation, and no Python needed. The builds are **unsigned**, so
Windows SmartScreen and macOS Gatekeeper warn on first launch.

Each archive unpacks to a folder holding the executable and a `licenses/` directory: the
terms of everything Proteus is built on, plus an inventory of every native library in the
build and where each licence determination came from. That inventory is generated on the
machine that produced the archive, so it describes what you actually downloaded.

Running from source instead is described in the
[README](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/README.md).

## Changes

See [CHANGELOG.md](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/CHANGELOG.md).

## Licence

Licensed **AGPL-3.0-or-later** — see
[LICENSE](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/LICENSE). A commercial
licence, without the AGPL's obligations, is available for closed-source and redistribution
use: see
[COMMERCIAL-LICENSE.md](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/COMMERCIAL-LICENSE.md).
