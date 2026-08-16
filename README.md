# 🖼️ Proteus - Rebranding Tool

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Commercial Licence Available](https://img.shields.io/badge/Commercial%20Licence-Available-green.svg)](COMMERCIAL-LICENSE.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/MarcoLombardoDev/Proteus/actions/workflows/ci.yml/badge.svg)](https://github.com/MarcoLombardoDev/Proteus/actions/workflows/ci.yml)

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

Row 7 in tabs ② and ③ is worth a look: `annual_report.docx!/image1.png` is a picture
**embedded in a Word document**, found and paired like any loose file. No wildcard would
have reached it.

**① in content-search mode** — no pattern at all, just a copy of the old logo:

![Content search configuration](docs/screenshots/05_content_search.png)

**The command line**, on the same sample data — a dry run, a refusal, and the applied
campaign:

![Command line session](docs/screenshots/06_command_line.png)

The middle run is the one to read. It found the logo inside the document, but two of the
hits were below 95% similarity, so it **refused to write anything and exited 4** — naming
both files and how to proceed deliberately. That is what "unattended" has to look like
when nobody is watching the screen.

<sub>Generated with [`docs/generate_screenshots.py`](docs/generate_screenshots.py), which boots
the real app under Xvfb against sample data in a temporary folder (no network, and your own
settings are left untouched). The terminal image is not a mock-up either: the script runs
the real command line and draws its actual output, exit codes included. Regenerate after a
UI change with `xvfb-run -a python docs/generate_screenshots.py`.</sub>

---

## Table of Contents

1. [Why this tool](#why-this-tool)
2. [Features](#features)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Search patterns](#search-patterns)
6. [Content search](#content-search)
7. [Office documents](#office-documents)
8. [Command line and unattended runs](#command-line-and-unattended-runs)
9. [Matching algorithm](#matching-algorithm)
10. [Safety model](#safety-model)
11. [Backup and restore](#backup-and-restore)
12. [CSV reports](#csv-reports)
13. [Languages](#languages)
14. [Files and folders](#files-and-folders)
15. [Building a standalone executable](#building-a-standalone-executable)
16. [Development](#development)
17. [Requirements](#requirements)
18. [Scope and limitations](#scope-and-limitations)
19. [License & Commercial Licensing](#license--commercial-licensing)
20. [Disclaimer](#disclaimer)

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

When there is no human to keep in the loop — a nightly job, a deployment pipeline, twenty
branch-office shares — the [command line](#command-line-and-unattended-runs) replaces that
supervision with explicit rules rather than dropping it: still a dry run by default, and it
refuses to write when a match is not certain.


---

## Features

**Finding**
- **Content search**: find the old logo by what it *looks like*, not by what it is
  called — the half of a rebranding that wildcards cannot solve
- **Inside Office documents**: pictures embedded in `.docx`, `.pptx` and `.xlsx` are found
  and replaced like any other file — which is where most logos actually live
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

**Automating**
- A **command line** covering everything the interface does, so the same campaign can run
  as a scheduled task, a cron job or a pipeline step
- **Unattended by design**: a run writes nothing unless asked, refuses on uncertain matches,
  and returns an exit code the scheduler can act on

**Reporting**
- CSV export of the proposed matches and of the replacement outcome
- Rotating log files, with a fallback location when the application folder is read-only
- A permanent licence notice in the window footer, satisfying the "Appropriate Legal
  Notices" requirement of AGPL-3.0 section 5 — with the licensing address spelled out and
  clickable, since the person running the tool is the one who might need to buy a licence

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

Any argument switches to the [command line](#command-line-and-unattended-runs) instead:

```bash
python main.py --help
```

---

## Usage

The application walks you through four tabs, in order.

### ① Configuration

| Field | Meaning |
|---|---|
| **Source folder** | Where the *new* logos live. Every supported image file in it becomes a replacement candidate. |
| **Folder to scan** | The tree to search for files to replace. Scanned recursively. |
| **Search by** | *File name* (wildcard pattern) or *Image content* (visual similarity). |
| **Search key** | Wildcard pattern for the file names to replace, e.g. `logo*.png`. In content mode it is an optional pre-filter. |
| **Reference images** | Content mode only: one or more copies of the *old* logo to search for. |
| **Minimum similarity** | Content mode only: how close a match must be to count. Defaults to 90%. |
| **Language** | English or Italian, applied immediately. |

The tool refuses to start when the two folders are the same, and warns you when the source
folder is nested inside the scanned one (in which case it is excluded from the search
automatically, so your new logos are never treated as targets).

### ② Scan results

Every matching file with its format, weight, resolution and — after a content search —
its similarity to the reference. Rows below the confident threshold are orange. Select a
row to preview it;
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

## Content search

Wildcards solve the easy half of a rebranding. The hard half is the logo filed as
`header_bg.png`, `img_04.jpg`, or something in a folder named after a project from 2014.
No pattern finds those, because nobody named them after the brand.

Switch **Search by** to *Image content*, point Proteus at one or more copies of the **old
logo**, and it finds every image that looks like them — whatever the file is called.

### How it works

Each image is reduced to a 9×8 greyscale grid and encoded as a 64-bit **difference hash**:
each pixel becomes one bit saying whether it is brighter than its right-hand neighbour.
Two images are compared by Hamming distance over those 64 bits.

Encoding the *gradient* rather than absolute brightness is what makes the hash survive the
three things that happen to a logo as it travels around an organisation: **rescaling**,
**re-encoding**, and **quality loss**. Transparency is flattened onto a fixed white matte
first, so the same mark exported once with an alpha channel and once without still reads
as itself.

### What it will and will not find

| | |
|---|---|
| Same logo at another size | ✅ tested from 60×20 to 960×320 |
| Same logo in another format (PNG/JPEG/BMP/…) | ✅ |
| Heavily re-compressed JPEG | ✅ tested down to quality 35 |
| With or without an alpha channel | ✅ |
| **Recoloured** logo | ✅ — see the caveat below |
| Logo **inside** a Word, PowerPoint or Excel file | ✅ see [Office documents](#office-documents) |
| **Cropped or rotated** logo | ❌ |
| Logo composited into a larger picture | ❌ only whole images are compared |
| SVG, PDF, EPS, EMF/WMF | ❌ nothing to rasterise; use a pattern for those |

### Colour is not what it discriminates on

A difference hash reads **luminance gradients**, and the *shape* is what creates them.
The same silhouette in another colour therefore still matches — measured at 100% for a
green or blue version of a red mark, 98% for black.

That cuts both ways. It is useful, because a logo is found across all its colourways. It
is also the main source of false positives: **two unrelated marks with similar
silhouettes will match too.** What actually breaks a match is a change of shape or
layout — the same test set drops to 70% for a genuinely different picture.

This is the reason the threshold is strict and every hit is previewed before anything is
written.

### Why the threshold is strict

**Minimum similarity** defaults to 90%, and that default is deliberate. Proteus overwrites
files: a false positive here does not produce a wrong row in a list, it destroys an
unrelated image. Lower it knowingly.

Anything found below **95%** is shown in orange and reported in the log, because those are
the rows a human actually needs to look at. The similarity of every hit is shown as a
column and is sortable, and the pattern field still works as a pre-filter to narrow the
search before any image is decoded.

---

## Office documents

In a real rebranding most of the logos are not loose PNGs on a share — they are inside
reports, decks and spreadsheet templates. Tick **Also look inside Office documents** and
Proteus treats a picture embedded in a `.docx` the same as one sitting on disk: it appears
in the results, gets a preview and a match, and is replaced with a backup.

Modern Office files are ZIP packages, and every picture in them is stored as an ordinary
image file under a `media/` folder inside. Proteus reads and rewrites them with the
standard library alone — there is no new dependency, and no Office installation is needed.

Supported: `.docx` `.docm` `.dotx` `.dotm` `.pptx` `.pptm` `.potx` `.potm` `.ppsx`
`.xlsx` `.xlsm` `.xltx` `.xltm`.

### One picture, every occurrence

Office stores a picture **once** however many times it appears. A logo used in the body
*and* in the page header is a single file inside the package, so one replacement fixes
both — and the document is backed up **once**, no matter how many of its pictures change.
That matters: replacing three logos one at a time would otherwise leave three backups of
successive states and no clean copy of the original.

### The frame does not follow the picture

This is the way a bulk replacement can quietly ruin a thousand documents.

The size and position of a picture are stored in the **document**, not in the image. A
shape laid out at 3.33 × 1.11 inches stays 3.33 × 1.11 inches after the image inside it is
swapped. Drop a square logo into a frame built for a 3:1 one and Word stretches it to fit.
Nothing errors; the deck just looks wrong, and nobody notices until it is printed.

Proteus compares the aspect ratio of the old picture with the new one and **flags the
replacement in orange**, listing the count in the operation summary before you commit.
The old picture's own ratio is used as a proxy for the frame, since the frame was almost
certainly sized to it when the image was first inserted.

### Not handled

- **`.doc`, `.ppt`, `.xls`** — the pre-2007 binary formats are OLE compound files, not ZIP
  packages.
- **EMF/WMF metafiles**, which Office produces when a logo is *pasted* rather than
  inserted. They cannot be rasterised by Pillow, so they could be neither previewed nor
  compared — only swapped blindly, which is worse than not touching them.
- Logos drawn with native Office shapes, or composited into a larger picture.

---

## Command line and unattended runs

Everything the interface does is also available without one. Pass any argument and Proteus
runs as a command-line tool instead of opening a window — same entry point, same logic,
no window server needed:

```bash
python main.py --scan /srv/intranet --source ./new-logos --pattern "logo*.png"
```

That command **changes nothing**. A run is a dry run unless you add `--apply`, because the
default has to be the safe one when nobody is watching the screen.

```bash
python main.py --scan /srv/intranet --source ./new-logos \
               --pattern "logo*.png" --apply --report campaign.csv
```

### Why this exists

The interface asks you to look at each pairing before it writes. That is exactly right when
a person is present, and useless in three situations:

| Situation | What the interface cannot do |
|---|---|
| Nightly job on a file server | Nobody is there to click ④ *Replace* |
| A build or deployment pipeline | No display, and a failure must stop the pipeline |
| Twenty branch-office shares | The same campaign, repeated by hand twenty times |

**Unattended** simply means "runs to completion with no human in front of it": a scheduled
task, a cron job, a pipeline step. The safety a person would provide — noticing a wrong
pairing before it is written — has to be encoded in the arguments instead.

### The safety model, without a human

Three rules replace the operator's eyes. All three can be overridden, but only deliberately:

| Rule | Default | Override |
|---|---|---|
| Nothing is written | Dry run | `--apply` |
| An uncertain hit refuses the whole run | 0 tolerated | `--max-uncertain N` |
| A replacement that would stretch a picture in a document refuses the run | forbidden | `--allow-distortion` |

An **uncertain hit** is a content-search match below 95% similarity — the ones the interface
would colour for review. Name-based matches are never uncertain: you asked for that pattern
explicitly.

A refusal is not a silent no-op. The offending files are listed, the CSV report is still
written if you asked for one, and the exit code says why.

### Exit codes

The whole point of a scheduled job: the scheduler must be able to tell what happened.

| Code | Meaning |
|---|---|
| `0` | Done — or a dry run that found work |
| `1` | Finished, but some replacements failed |
| `2` | Nothing matched |
| `3` | Bad request: missing or invalid arguments, unreadable folder |
| `4` | Refused on safety grounds — uncertain hits or a distortion |
| `130` | Interrupted (Ctrl-C) |

`2` is deliberately not an error. A weekly job finding nothing left to rebrand has succeeded.

### Options

```
what to scan
  --scan FOLDER            folder to search for files to replace
  --source FOLDER          folder holding the new logos

how to find it
  --pattern GLOB           wildcard, e.g. "logo*.png"; several separated by ";"
  --reference IMAGE...     one or more copies of the OLD logo — content search
  --similarity PCT         minimum visual similarity for --reference (default 90)
  --office                 also look inside .docx/.pptx/.xlsx documents

what to do
  --apply                  actually write. Without it nothing is modified.
  --no-backup              do not keep a .bak of each original (not advised)
  --restore                restore originals from their backups and exit

safety
  --max-uncertain N        tolerate at most N hits below 95% similarity
  --allow-distortion       allow replacements that would stretch a picture

output
  --report FILE.csv        CSV of what was found and done
  --language {en,it}       language of messages and report headers
  --quiet                  only report problems
  --verbose                one line per file
```

`--restore` is a dry run by default too, and it also honours `--apply`.

### Scheduling it

Progress goes to stdout, problems to stderr, so redirecting the two separately gives you a
log and an alert channel:

```bash
# /etc/cron.d/rebranding — every Sunday at 03:00
0 3 * * 0 rebrand /opt/proteus/run.sh --scan /srv/shares --source /srv/brand/2026 \
    --reference /srv/brand/old-logo.png --office --apply \
    --report /var/log/proteus/$(date +\%F).csv >>/var/log/proteus/run.log 2>&1
```

```powershell
# Windows Task Scheduler
schtasks /create /tn "Rebranding" /sc weekly /d SUN /st 03:00 /tr `
  "C:\Proteus\proteus-cli.exe --scan \\fs01\shares --source C:\Brand\2026 --pattern logo*.png --apply"
```

On Windows use **`proteus-cli.exe`**, not `Proteus.exe`. The interface binary is built
`--windowed` and therefore has no console at all: it would run correctly but print nothing,
leaving a failed job undiagnosable. The two binaries share one entry point and differ only
in that.

### Trying it safely

The honest way to adopt this is in three steps, and the exit code tells you when to move on:

1. `--verbose` with no `--apply` — read every proposed pairing.
2. Add `--report` and open the CSV.
3. Add `--apply`. Keep backups; `--restore` undoes the campaign.

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
| Content search hitting an unrelated image | Strict default threshold, similarity shown per row, uncertain hits coloured and logged |
| A replacement silently distorting a picture in a document | Aspect ratios compared, mismatches coloured and counted in the summary |
| A document rewritten while several of its pictures change | Grouped per document: rewritten once, backed up once, atomically |
| Unsure about a whole campaign | Dry run reproduces the entire operation without writing |
| Nobody watching an automated run | The command line is a dry run unless `--apply`, and refuses to write when any hit is uncertain or would distort |
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
├── office.py                     # Reading and rewriting pictures inside OOXML packages
├── cli.py                        # Command line and unattended runs
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
├── tests/                        # logic, GUI, i18n, build, content, office, CLI, docs
├── CLAUDE.md                     # Conventions for anyone working on the repo
├── LICENSE                       # AGPL-3.0
├── COMMERCIAL-LICENSE.md         # Commercial terms and price list
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

On Windows, `compile.bat` does the same. The result is **two** single-file binaries in
`dist/`, with the icon embedded and a `logs/` folder prepared alongside them:

| Binary | Built | For |
|---|---|---|
| `Proteus.exe` (~21 MB) | `--windowed` | The interface |
| `proteus-cli.exe` | `--console` | Scripts and scheduled jobs |

They share one entry point and differ only in that flag. The split is not cosmetic: a
`--windowed` executable has no console on Windows, so a CLI run through it would print
nothing at all and a failed job could not be diagnosed.

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

The suite is spread across eight files:

| File | Covers |
|---|---|
| `tests/test_core.py` | Scanning, matching, atomic replacement, backups, restore, CSV, settings, plus an end-to-end campaign |
| `tests/test_gui.py` | Startup, the full wizard flow, dry run, row toggling, sorting, manual override, restore, language switching, shutdown |
| `tests/test_i18n.py` | Translation layer, catalogue completeness and placeholder integrity |
| `tests/test_build.py` | Console encoding, platform separators, launcher choice and build prerequisites |
| `tests/test_content_search.py` | Perceptual hashing across scales, formats and transparency — and, just as important, what must *not* match |
| `tests/test_office.py` | Real .docx/.pptx/.xlsx built and re-opened with the official libraries, package rewriting, backups and aspect-ratio guarding |
| `tests/test_cli.py` | Every exit code, the safety refusals and their overrides, reports, restore, output control and entry-point dispatch |
| `tests/test_docs.py` | Screenshots referenced and shown, the price list agreeing with itself, and the AGPL text left verbatim |

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

The screenshot script needs `mss`, and `python-docx` for the Office sample document — it
skips that one file with a message rather than failing if the library is absent. The
terminal image is produced by running the real command line and drawing its output, so it
cannot drift out of step with the code.

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

- **Content search discriminates on shape, not colour.** A recoloured logo still matches;
  an unrelated mark with a similar silhouette may match too. Cropping and rotation defeat
  it entirely.
- **Only whole images are compared.** A logo composited into a larger picture, or drawn
  with native Office shapes rather than inserted as a picture, is not found.
- **Legacy Office formats are out of scope.** `.doc`, `.ppt` and `.xls` are OLE compound
  files, not ZIP packages. So are EMF/WMF metafiles, which Office produces when a logo is
  *pasted* rather than inserted.
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
- **The command line trades review for rules.** Its refusals are threshold-based; they
  catch an uncertain match, not a confidently wrong one. A first campaign is still worth
  running through the interface, or at least as a dry run with `--report`.
- The Windows executables are built and published by CI; local builds have been verified on
  Linux.

---

## License & Commercial Licensing

Proteus is open-source software released under the
**[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)**.

Copyright © 2026 Marco Lombardo.

**The free build is the whole product.** Every feature documented above is in it. There is
no paid edition, no feature gate, no licence key, no seat limit and no phone-home. If
AGPL-3.0 works for you, you are done reading — Proteus is yours to use.

### What AGPL-3.0 Means for You

| Use Case | Allowed? | Obligation |
|---|---|---|
| Internal use, any number of machines and users | ✅ Yes | None |
| Modify it and keep the changes to yourself | ✅ Yes | None |
| Fork & publish on GitHub | ✅ Yes | Must stay AGPL-3.0 |
| Redistribute it, modified or not, under AGPL-3.0 | ✅ Yes | Must ship the source |
| Deploy a modified version as a network service | ✅ Yes | Must publish the source of your modified version |
| Integrate into a **closed-source product** | ⚠️ Restricted | Requires a commercial licence |
| Offer as a **proprietary SaaS** without sharing source | ❌ Not under AGPL | Requires a commercial licence |
| **Resell** it, or ship it inside a product you sell | ❌ Not under AGPL | Requires a commercial licence |

The dividing line is one rule: **AGPL-3.0 is free as long as the source stays open.**


### Commercial Licensing

The commercial licence removes the copyleft obligation, and nothing else. It is for
organisations embedding Proteus in a proprietary product, running a modified version as a
service without publishing the source, reselling it under their own terms — or simply
barred by internal policy from using AGPL code.

| Tier | Price | Scope |
|---|---:|---|
| **Community** | **Free** | Everything Proteus does, under AGPL-3.0. Unlimited internal use. |
| **Internal** | **€500 / year** | Closed-source internal use, one legal entity. No redistribution. |
| **OEM / Redistribution** | **€1,900 / year** | Embed it in a product you sell, or run it as a hosted service. |
| **Enterprise** | **from €2,900 / year** | Group-wide, unlimited products, procurement and legal questionnaires answered. |
| **Perpetual** | **€1,500** / **from €7,000** one-off | Internal or OEM scope, bought once, for the major version current at purchase. |

The same commitments apply at every paid tier:

- **Email support is always included** — 5 business days at Internal, 3 at OEM, 2 at
  Enterprise. It is never sold separately to a paying customer.
- **Custom development is never included**, at any tier. It is available on request and
  **quoted separately**, per project, at a fixed price agreed before work starts
  (indicative day rate: **€450 / day**).
- **Perpetual fallback, no retroactive price rise, cancel any time.** Versions released
  during your term stay licensed to you forever.
- **50% off** for organisations under 10 employees and €1M revenue. **Free** commercial
  licences for non-profits, academia and published research — ask.

Prices are per organisation, excluding VAT. **Seats are never counted.** Full terms, what is
*not* included, and the third-party component review:
**[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)**.

### How to get in touch

Everything commercial — buying a licence, asking for a quote, commissioning custom
development, or checking whether you need a licence at all (the answer is often *no*) —
goes to one address:

> **[marco.lombardo@gmail.com](mailto:marco.lombardo@gmail.com?subject=Proteus%20commercial%20licence%20enquiry)** — Marco Lombardo

The same address is shown in the application's footer, and clicking it opens your mail
client on a pre-filled enquiry. Please keep **GitHub Issues for bugs and feature
requests**, not for licensing.

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
