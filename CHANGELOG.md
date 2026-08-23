# Changelog

All notable changes to Proteus are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file starts at 1.3.0, the first version whose changes were recorded here.
Everything before it is reconstructed from the commit history and is
deliberately summarised rather than itemised.

## [Unreleased]

### Added
- **Real builds for Windows, macOS and Linux.** `.github/workflows/release.yml`
  replaces the Windows-only `build.yml`: one matrix, three genuine runners, one
  archive per platform attached to the release. PyInstaller does not
  cross-compile, so this is the only way each binary can be real.
- Every bundle is **smoke-tested on its own platform** before it is offered for
  download — `--version` and `--help` have to return cleanly, or the asset is
  not published.
- `.github/release-body.md`, so the text a downloader reads lives in the
  repository and can be edited without touching a workflow.
- `CHANGELOG.md` — this file.

### Changed
- **Every Python source file carries the same seven-line licence header**, in
  the same place: the product name, the copyright line, an
  `SPDX-License-Identifier: AGPL-3.0-or-later` a tool can read, a pointer to
  LICENSE for the warranty disclaimer, and a pointer to COMMERCIAL-LICENSE.md
  for the commercial option.
  None of Proteus's 23 files had one.
  The `# -*- coding: utf-8 -*-` declarations went with it: they have meant
  nothing since Python 3, and Orion's ruff configuration flags them as UP009.
  Nothing but comments changed — the parsed syntax tree of all 152 files is
  identical before and after, which is how that was checked rather than
  assumed.
- **`LICENSE` is now the verbatim FSF text of the AGPL-3.0.** The previous copy
  was reflowed to long lines, which the licence's own header does not permit
  ("changing it is not allowed") and which stops GitHub recognising it.
- **`COMMERCIAL-LICENSE.md` was restructured into the shared 14-section layout**
  used by Orion, Iris and Argus, so the same clause sits at the same number in
  every product. Prices are unchanged; a **Perpetual option** was added to the
  price list, at three times the annual rate of the same tier, on the four
  fixed-price tiers.
- `CLA.md` was aligned with the same three products, keeping the branding-assets
  representation that is specific to this one.
- Release assets are now archives named
  `Proteus-<version>-<platform>.zip` / `.tar.gz`, rather than a bare
  `Proteus.exe`.

## [1.3.0] — 2026-08-17

Released as `v1.3`; renumbered here to semantic versioning.

### Added
- **PDF support** — finds and replaces the pictures embedded inside PDF files,
  reporting the ones drawn as vector artwork instead of silently skipping them.
- **Office documents** — the same for pictures inside `.docx`, `.pptx` and
  `.xlsx`, read and written with the standard library alone.
- **Content search** — finds the old logo by what it looks like rather than by
  filename, so a file nobody named consistently is still found.
- **Command line and unattended runs** — `--audit`, `--apply`, exit codes, and
  a refusal (exit 4) rather than a guess when a match falls below the
  similarity threshold.
- **One executable for both halves**: double-click for the interface,
  `Proteus.exe --help` from a terminal for the command line.
- English and Italian interfaces, switchable at runtime.
- AGPL-3.0 licensing with a commercial licence alongside it, and a licensing
  contact shown in the application footer.

### Fixed
- A held-open file is now told apart from a permissions problem, instead of
  both being reported the same way.
- The build script no longer crashes under a legacy console code page.
- The GUI tests share one Tk interpreter, and the writability test no longer
  depends on the platform.
