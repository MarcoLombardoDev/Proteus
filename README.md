# 🖼️ Proteus - Rebranding Tool

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Commercial License Available](https://img.shields.io/badge/Commercial%20License-Available-green.svg)](#license--commercial-licensing)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-107-brightgreen.svg)](#development)

> **Proteus** — named after the shape-shifting sea god — is a rebranding tool: it changes
> what your files look like without changing where they are.

Proteus is a Python desktop application for the **bulk replacement of logo and
graphic files** across a large folder tree — a company file server, a website checkout, a
network share. You point it at a folder of new logos and a folder to scan; it finds the
files that match a pattern, pairs each one with the most suitable replacement, shows you
a before/after preview of every pairing, and then overwrites them **atomically, with
recoverable backups**.

It exists because doing this by hand across hundreds of files is slow and, worse, silently
error-prone: it is very easy to drop a 1920×600 banner where a 32×32 favicon belonged.

> 🌍 The interface is available in **English** (default) and **Italian**, switchable at
> runtime from the configuration tab.

---

## Screenshots

> The folders and files below are **synthetic sample data** generated purely to
> illustrate the interface. The coloured rectangles stand in for real logos.

| | |
|---|---|
| **① Configuration** — source folder, folder to scan, search pattern, language | **② Scan results** — every matching file with format, weight and resolution |
| ![Configuration tab](docs/screenshots/01_configuration.png) | ![Scan results tab](docs/screenshots/02_scan_results.png) |
| **③ Matches** — proposed pairings, quality grade, before/after preview | **④ Replacement** — summary, backup and dry-run options, live log |
| ![Matches tab](docs/screenshots/03_matches.png) | ![Replacement tab](docs/screenshots/04_replacement.png) |

<sub>Generated with [`docs/generate_screenshots.py`](docs/generate_screenshots.py), which boots
the real app under Xvfb against sample data in a temporary folder (no network, and your own
settings are left untouched). Regenerate after a UI change with
`xvfb-run -a python docs/generate_screenshots.py`.</sub>

---

## Table of Contents

1. [Why this tool](#why-this-tool)
2. [Features](#features)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Search patterns](#search-patterns)
6. [Matching algorithm](#matching-algorithm)
7. [Safety model](#safety-model)
8. [Backup and restore](#backup-and-restore)
9. [CSV reports](#csv-reports)
10. [Languages](#languages)
11. [Files and folders](#files-and-folders)
12. [Building a standalone executable](#building-a-standalone-executable)
13. [Development](#development)
14. [Requirements](#requirements)
15. [Scope and limitations](#scope-and-limitations)
16. [License & Commercial Licensing](#license--commercial-licensing)
17. [Disclaimer](#disclaimer)

---

## Why this tool

A rebranding exercise is rarely one file. The same logo lives in a dozen resolutions
across a website, an intranet, print templates and legacy folders — `logo_header.png`,
`logo_footer.png`, `logo_small.png`, `logo.svg`, `logo_press.jpg`. Replacing them by hand
means finding each one, guessing which new asset belongs where, and hoping you did not
overwrite something with the wrong size.

Proteus automates the finding and the pairing, but deliberately **keeps the human
in the loop**: nothing is written until you have seen each proposed pairing, and every
pairing carries a quality grade telling you where the automation is confident and where it
is guessing.

---

## Features

**Finding**
- Recursive search with wildcard patterns; multiple patterns at once (`logo*.png; logo*.svg`)
- Case-insensitive matching, symlink/junction cycle protection, per-folder error reporting
  so an unreadable network share does not abort the whole scan
- Automatically skips its own `.bak` files, and skips the source folder when it happens to
  sit inside the folder being scanned

**Pairing**
- Same-format constraint, with `.jpg`/`.jpeg` and `.tif`/`.tiff` treated as equivalent
- Closest-resolution selection, normalised so the gap is judged *relative* to the target size
- File-name similarity as a tie-break between equally-sized candidates
- SVG dimensions read from the markup (`width`/`height`, falling back to `viewBox`)
- A **quality grade** per pairing — Excellent / Good / Weak / Manual — with weak matches
  highlighted for review
- Manual override: double-click any row to pick a different source file

**Replacing**
- **Atomic writes**: the copy lands on a temporary file and is promoted with `os.replace`,
  so a failure halfway through never truncates the original
- **Non-clobbering backups**: a second rebranding campaign does not overwrite the first
  campaign's `.bak`
- **Dry run** that performs every check and produces the full log without touching a file
- **One-click restore** from the backups, always reverting to the pre-rebranding original
- Cancellable at any point, with visible progress — designed for slow network shares

**Reporting**
- CSV export of the proposed matches and of the replacement outcome
- Rotating log files, with a fallback location when the application folder is read-only
- A permanent licence notice in the window footer, satisfying the "Appropriate Legal
  Notices" requirement of AGPL-3.0 section 5

---

## Installation

### Prerequisites

- **Python 3.10 or newer**, including `tkinter`
  - Windows: keep the *tcl/tk and IDLE* option selected in the Python installer
  - Debian/Ubuntu: `sudo apt install python3-tk`
  - Fedora: `sudo dnf install python3-tkinter`
  - macOS (Homebrew): `brew install python-tk`

### Install dependencies

```bash
pip install -r requirements.txt
```

On Windows you can instead double-click **`install_dependencies.bat`**, which also verifies
that `tkinter` is present before installing anything.

### Run

```bash
python main.py
```

| Platform | Shortcut |
|---|---|
| Windows | `run.bat` |
| Linux / macOS | `./run.sh` |

---

## Usage

The application walks you through four tabs, in order.

### ① Configuration

| Field | Meaning |
|---|---|
| **Source folder** | Where the *new* logos live. Every supported image file in it becomes a replacement candidate. |
| **Folder to scan** | The tree to search for files to replace. Scanned recursively. |
| **Search key** | Wildcard pattern for the file names to replace, e.g. `logo*.png`. |
| **Language** | English or Italian, applied immediately. |

The tool refuses to start when the two folders are the same, and warns you when the source
folder is nested inside the scanned one (in which case it is excluded from the search
automatically, so your new logos are never treated as targets).

### ② Scan results

Every matching file with its format, weight and resolution. Select a row to preview it;
double-click to open its containing folder. Columns are sortable, and sorting is
type-aware — `2.0 MB` ranks above `900 KB`, and `10` after `2`.

### ③ Matches

The heart of the tool. Each target file is shown next to its proposed replacement, with
both resolutions, a quality grade and a side-by-side preview.

- **Click the ✓ column** (or press <kbd>Space</kbd>) to include or exclude a row
- **Double-click a row** to choose a different source file, ordered by suitability
- **Colours**: green = included, grey = excluded, red = no match found,
  orange = weak match worth a look

Rows with no match are excluded automatically; you cannot accidentally replace a file with
nothing.

### ④ Replacement

A summary of exactly what is about to happen, two safety switches, and a live log.

| Option | Effect |
|---|---|
| **Backup** | Copies each original to `.bak` before overwriting. Enabled by default. |
| **Dry run** | Runs every check and produces the full log, writing nothing. |

After a real run you are offered a CSV report of the outcome.

---

## Search patterns

| Pattern | Matches |
|---|---|
| `logo*.png` | Every PNG whose name starts with `logo` |
| `banner_*.jpg` | Every JPG starting with `banner_` |
| `*.svg` | Every SVG file |
| `icon_??.png` | `icon_` followed by exactly two characters, `.png` |
| `logo*.png; logo*.svg` | Several patterns at once, separated by `;` |

Matching is case-insensitive, so `logo*.png` also finds `LOGO_Header.PNG`.

Patterns that would select *every* file (`*`, `?`, or only wildcards) are rejected, as are
patterns containing a path separator — the pattern applies to file names, not paths.

---

## Matching algorithm

For each file to replace, candidates are filtered and then ranked.

**1. Same format (hard constraint).** A `.png` is only ever replaced by a `.png`. The only
equivalences are `.jpg`↔`.jpeg` and `.tif`↔`.tiff`.

**2. Closest resolution (dominant criterion).** Among the candidates, the one whose
resolution is nearest wins. The gap is the euclidean distance between the two resolutions,
**normalised over the target's diagonal**:

```
distance = √((w₁-w₂)² + (h₁-h₂)²) / √(w₁² + h₁²)
```

Normalising matters: a 20 px difference is a serious mismatch on a 32×32 icon and
irrelevant on a 1920×1080 banner. An absolute distance would treat them the same.

**3. File-name similarity (tie-break).** When several sources share a resolution, the one
whose name is most similar to the target wins, measured with `difflib.SequenceMatcher`
over the file stems.

The ranking score combines the last two at 65% resolution / 35% name. The **grade shown to
you**, however, depends on the resolution gap *alone* — name similarity decides which
candidate is chosen, but it must never make a pixel-perfect match look worse:

| Grade | Relative resolution gap |
|---|---|
| **Excellent** | ≤ 10% |
| **Good** | ≤ 35% |
| **Weak** | above 35% — review by hand |
| **Manual** | you chose the source yourself |
| **—** | no candidate of that format exists |

For formats whose resolution cannot be read (PDF, EPS) the grade falls back to name
similarity alone.

---

## Safety model

Bulk-overwriting files on a shared drive deserves care. The guarantees are:

| Risk | Mitigation |
|---|---|
| Copy fails halfway, leaving a truncated file | Copy to a temporary file in the same folder, then promote with `os.replace` (atomic on one filesystem) |
| Second campaign destroys the pristine original | Backups never overwrite an existing `.bak`; later ones get a timestamp |
| Source and target are the same file | Detected via `os.path.samefile` and skipped with an explicit message |
| Source folder nested in the scanned tree | Excluded from the scan automatically |
| Replacing a file with nothing | Rows without a match cannot be enabled |
| Unsure about a whole campaign | Dry run reproduces the entire operation without writing |
| Wrong replacement already applied | Restore from backups reverts to the pre-rebranding state |
| Long scan on an unresponsive share | Cancellable, with per-folder error reporting rather than a hard abort |

---

## Backup and restore

With **Backup** enabled, each original is copied before being overwritten:

| Campaign | Backup file |
|---|---|
| First | `logo.png.bak` |
| Later ones | `logo.png.20260812-101500.bak` |

**Restore backups** in tab ④ walks the scanned folder, and for every file with backups it
restores the **oldest** one — the version predating the first replacement, which is what
"undo the rebranding" actually means. You are asked whether to delete the `.bak` files
afterwards.

Backup files are excluded from scans, so they never become replacement targets themselves.

---

## CSV reports

Both exports use `;` as the separator and a UTF-8 BOM, so they open cleanly in Excel with
European locale settings.

- **Matches export** (tab ③): inclusion flag, target and source names, both resolutions,
  weight, grade, numeric score and both full paths.
- **Outcome report** (offered after a real run): status, file, source, backup path and any
  error message, one row per file.

Column headers follow the interface language.

---

## Languages

English is the default and the source language of every message. Italian is fully
translated. The choice is persisted and applied immediately — the interface is rebuilt in
place, keeping your scan results, your pairings and your log.

Adding a language means adding one dictionary to `CATALOGUES` in
[`i18n.py`](i18n.py). Anything you do not translate falls back to English rather than
showing a placeholder. Three tests keep the catalogues honest:

- every string passed through `t()` has an entry,
- no entry is stale,
- `{placeholders}` are preserved across languages (a dropped one would raise in front of
  the user).

---

## Files and folders

```
├── main.py                       # Entry point
├── core.py                       # Logic: scan, match, replace, backup, CSV, settings
├── rebranding_tool.py            # Tkinter interface
├── i18n.py                       # Translation layer and language catalogues
├── build.py                      # PyInstaller build
├── app.ico                       # Application icon (generated)
├── assets/generate_icon.py       # Regenerates app.ico
├── docs/generate_screenshots.py  # Regenerates the README screenshots
├── docs/screenshots/             # Committed screenshots
├── requirements.txt              # Runtime dependencies
├── requirements-dev.txt          # Test dependencies
├── run.bat / run.sh              # Launchers
├── install_dependencies.bat      # Windows dependency setup
├── compile.bat                   # Windows build shortcut
├── tests/                        # 107 tests (logic, GUI, i18n)
├── LICENSE                       # AGPL-3.0
└── CLA.md                        # Contributor License Agreement
```

`core.py` has **no tkinter dependency**, which is what makes the logic testable without a
display and reusable from a script.

**Runtime data** is written next to the application, in `logs/` and `config/`. If that
location is read-only — the typical `C:\Program Files` install — both fall back to
`%LOCALAPPDATA%\Proteus\` (or `~/.local/share/Proteus/` elsewhere). Logs
rotate at 2 MB, keeping five files.

---

## Building a standalone executable

```bash
python build.py
```

On Windows, `compile.bat` does the same. The result is a single-file
`dist/Proteus.exe` (~21 MB), with the icon embedded and a `logs/` folder prepared
alongside it.

The build script installs anything missing, picks the right `--add-data` separator for the
platform, and falls back to the running interpreter when the Windows `py` launcher is not
available.

---

## Development

```bash
pip install -r requirements-dev.txt

python -m pytest                 # Windows / macOS
xvfb-run -a python -m pytest     # Linux (the GUI tests need a display)
```

The suite is **107 tests** across three files:

| File | Covers |
|---|---|
| `tests/test_core.py` | Scanning, matching, atomic replacement, backups, restore, CSV, settings, plus an end-to-end campaign |
| `tests/test_gui.py` | Startup, the full wizard flow, dry run, row toggling, sorting, manual override, restore, language switching, shutdown |
| `tests/test_i18n.py` | Translation layer, catalogue completeness and placeholder integrity |

GUI tests run headless and are skipped automatically where no display exists. A `conftest`
fixture neutralises every modal dialog, so a test that reaches an unexpected `askyesno`
fails instead of hanging the suite forever.

CI runs the suite on **Ubuntu and Windows** against **Python 3.10 and 3.12**, and then
builds the Windows executable so a broken build surfaces before distribution.

To regenerate the artwork or the documentation images:

```bash
python assets/generate_icon.py
pip install mss && xvfb-run -a python docs/generate_screenshots.py
```

---

## Requirements

| Package | Required? | Why |
|---|---|---|
| `pillow` ≥ 9.1 | **Yes** | Image previews and resolution reading. 9.1 is the floor because of `Image.Resampling`. |
| `tkinter` | **Yes** | The interface. Ships with Python, but packaged separately on Linux. |
| `ttkbootstrap` ≥ 1.10 | Optional | Nicer theming. Without it the app uses standard ttk themes; either major version works. |
| `pyinstaller` ≥ 5.13 | Build only | Producing the standalone executable. |
| `mss` | Docs only | Capturing the README screenshots. |

Without Pillow the application still runs and still replaces files — it just cannot show
previews or read resolutions, and says so on the configuration tab.

---

## Scope and limitations

- **Previews and resolutions are unavailable for EPS and PDF.** Pillow cannot read them
  without Ghostscript. Files of those types can still be matched, graded by name
  similarity, and replaced.
- **SVG resolution comes from the markup.** An SVG sized only in percentages or relative
  units reports no resolution, and falls back to name-based grading.
- **Replacement is byte-for-byte.** The tool copies the source file; it does not convert
  formats or rescale images. A 500×200 source stays 500×200 after replacing a 240×80 target.
- **Atomicity is per file, not per campaign.** Each file is replaced atomically, but a run
  interrupted midway leaves earlier files already replaced. That is what the backups and
  the restore button are for.
- **`os.replace` is atomic only within one filesystem.** The temporary file is created in
  the target's own folder, so this holds in practice, including on mapped network drives.
- The Windows executable is built and published by CI; local builds have been verified on
  Linux.

---

## License & Commercial Licensing

Proteus is open-source software released under the
**[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)**.

### What AGPL-3.0 Means for You

| Use Case | Allowed? | Obligation |
|---|---|---|
| Personal / internal company use | ✅ Yes | None |
| Modify & redistribute privately | ✅ Yes | None |
| Deploy a modified version on a server | ✅ Yes | Must publish the source of your modified version |
| Fork & publish on GitHub | ✅ Yes | Must use AGPL-3.0 |
| Integrate into a **closed-source commercial product** | ⚠️ Restricted | Requires a commercial license (see below) |
| Offer as a **proprietary SaaS** without sharing source | ❌ Not allowed under AGPL | Requires a commercial license |

### Commercial Licensing

If you need to use Proteus in a **proprietary application**, a **closed-source
service**, or an **enterprise deployment** without being bound by the AGPL-3.0 copyleft
requirements, a **commercial license** is available.

A commercial license grants you the right to:

- embed Proteus in closed-source software,
- run it as part of a service without disclosing your source code,
- use it in commercial products without AGPL obligations.

For commercial licensing enquiries, please open an issue on this repository.

### Contributing

Contributions are welcome. All contributors must agree to the
[Contributor License Agreement (CLA)](CLA.md) before a Pull Request can be merged. The CLA
grants the Project Owner the right to dual-license contributions under AGPL-3.0 and
commercial terms — this is what makes the dual-licensing model sustainable.

> **To agree to the CLA:** include
> `I have read and agree to the Contributor License Agreement (CLA.md).`
> in your Pull Request description.

One project-specific rule: since this tool exists to replace brand assets, **contributions
must not introduce third-party logos, icons or trademarks**. Sample images, test fixtures
and screenshots use neutral synthetic artwork only.

---

## Disclaimer

This software **overwrites files in place**. It ships with backups enabled by default, a
dry-run mode and a restore function, and every write is atomic — but no safety net replaces
your own backups.

Before running a campaign against a production file server or a shared drive:

1. run it with **Dry run** enabled and read the log,
2. keep **Backup** enabled for the real run,
3. make sure you have an independent backup of the target tree.

The software is provided **"as is", without warranty of any kind**, as set out in sections
15 and 16 of the AGPL-3.0. The authors accept no liability for data loss or for any damage
arising from its use.

---

*Copyright © 2026 Marco Lombardo. Licensed under AGPL-3.0 — commercial licensing available.*
