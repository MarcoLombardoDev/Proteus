# Third-party licences

Proteus is licensed **AGPL-3.0-or-later** (see [LICENSE](LICENSE)), with a
commercial licence available separately (see
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)). That covers the code in this
repository. It does not cover the code Proteus is built on, and a
downloadable release is mostly that other code: a Linux build contains
102 native binaries and not one of them was written for Proteus.
Proteus's own code travels through them as Python bytecode.

This file is the inventory of what those binaries are and what licenses them.

## How this was produced

It was generated, not written from memory, by
[`tools/licence_inventory.py`](tools/licence_inventory.py) run against
the published `Proteus-1.3.0-linux-x64.tar.gz`. The table
below is literally the copy the release runner generated and packaged inside
that archive as `licenses/THIRD-PARTY-LICENSES-linux-x64.md`, lifted out of it
unchanged — so it describes the file somebody downloads rather than a build
that resembles it. That distinction matters:
PyInstaller collects whatever the build machine's linker resolved, so the
contents change when the runner image changes, not when someone edits this
repository. A hand-maintained list would be stale within one CI image bump and
nobody would notice.

Every entry traces to a machine-readable source:

- **Python packages** — the top-level package a binary sits under names its own
  distribution, and that distribution's installed metadata states its licence.
- **Libraries collected from the Linux build machine** — the owning package
  from `dpkg-query`, and that package's `debian/copyright`.
- **Libraries the platform supplies** (the Windows CRT, the OpenSSL that ships
  inside python.org's builds) — identified by name, since no package manager
  owns them.

Two traps in that lookup are worth stating, because both produced wrong answers
before they were caught, and both are handled in the script rather than papered
over:

A `debian/copyright` file enumerates every licence appearing anywhere in the
*source* package, test fixtures and build scripts included. Reporting that
union is alarmist nonsense. What governs a shipped shared library is the
licence of that library's own sources — the stanza whose `Files:` pattern
covers them.

And even the `Files: *` stanza is wrong when one source package builds several
libraries under different terms. util-linux's default stanza says GPL-2+, while
`libuuid`, which these builds do ship, is BSD-3-clause in its own stanza.
Taking the default would have published a wrong answer that looked
authoritative. Those cases are in the script's `REVIEWED` table, each with the
stanza that was read.

Anything the script cannot resolve is reported as **unresolved** rather than
guessed at. A gap you can see is worth more than a plausible-looking entry that
is wrong.

## What Proteus depends on directly

Four packages, declared in [`requirements.txt`](requirements.txt), with the
licence each one's own metadata states:

| Package | Version built | Licence (from its metadata) | What Proteus uses it for |
|---|---|---|---|
| Pillow | 12.3.0 | `MIT-CMU` | opening, measuring, resizing and hashing the pictures |
| pypdf | 6.16.2 | `BSD-3-Clause` | finding and replacing pictures inside PDF files |
| ttkbootstrap | 2.2.2 | `MIT AND (Apache-2.0 OR BSD-2-Clause)` | the theme; optional at runtime |
| PyInstaller | 6.22.2 | `GPL-2.0-or-later WITH Bootloader-exception` | building the executable |

Every one of them imposes attribution and nothing more. **Nothing in the
closure is copyleft**, and that is a choice rather than luck: PDF support uses
`pypdf` and not PyMuPDF, which is offered under AGPL-3.0 or a paid Artifex
licence. A commercial licence to Proteus cannot relicense somebody else's
copyleft code, so a buyer would have needed a second licence from a third party
to ship the product. `pypdf` is slower for some workloads and it was chosen
anyway.

Office documents need no library at all: Proteus reads and writes `.docx`,
`.pptx` and `.xlsx` with the standard library's `zipfile`. `python-docx`,
`python-pptx` and `openpyxl` are test-only and are not in the archive.

## The components that actually constrain redistribution

Most of the inventory below is MIT, BSD and ISC — attribution and nothing more.
One thing is not, and it is the only one worth a decision:

**The GCC runtime** — `libgcc_s` and `libstdc++`, GPL-3.0-or-later **with the
GCC Runtime Library Exception 3.1**. The exception is what makes this
distributable at all; without it a GPL-3 library would sit in the middle of
every Linux build. Nothing to do here, but it should not be mistaken for a
permissive licence.

On Windows the equivalent row is the **Microsoft Visual C++ and Universal CRT
runtime**, which is not open source at all. It is redistributable under
Microsoft's own redistributable terms — a different legal basis from every
other entry in this document, carrying its own conditions.

## What was deliberately removed

**The standard library's `readline` extension.** PyInstaller collected it by
default, and it links `libreadline`, which is **GPL-3.0-or-later with no
linking exception**. That put GPL-3 code inside an archive
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) offers for redistribution inside
closed-source products — the one combination the whole commercial tier is
supposed to avoid. `libpython` does not link it; only that module does, and
nothing in Proteus reads a line from an interactive prompt. It and
`rlcompleter` are excluded in [`build.py`](build.py), and
[`tests/test_packaging.py`](tests/test_packaging.py) pins the exclusion so it
cannot silently come back. `libtinfo` left with it.

## Licence texts travel with the build

The v1.3.0 archives contained one executable and nothing else. A recursive
search of all three for `LICENSE`, `COPYING` or `NOTICE` returned nothing,
which every BSD and MIT notice in the bundle requires, which the LGPL-2.1
system libraries require in stronger terms, and which Proteus's own AGPL
requires as well.

[`tools/collect_licences.py`](tools/collect_licences.py) now assembles them and
the release workflow packages the result as `licenses/` **beside** the
executable. Beside rather than inside, because these are `--onefile` builds:
anything added to the bundle is sealed in the executable and visible only to
somebody who has already run it, which is not what "accompany the object code"
means.

The tree holds one directory per distribution that contributed code, the
interpreter's and Tcl/Tk's own terms — neither is a wheel, so neither has
metadata to read and both are supplied from [`licenses/`](licenses) in this
repository — and, on Linux, the build machine's copyright record for every
system library collected. Which distributions those are is read out of
PyInstaller's own record of the build rather than from a list kept by hand: a
list like that is right the day it is written and wrong the first time a
dependency grows a dependency.

## Full inventory

Counts are files, not projects: one project usually contributes several
binaries. "Evidence" names where the licence came from, so any line here can be
re-checked rather than taken on trust.

### Linux — 102 native binaries

| Component | Files | Licence | Evidence |
|---|---|---|---|
| `CPython` (cpython) | 51 | PSF-2.0 | the Python Software Foundation License, version 2 |
| `libbrotli1` (system) | 2 | MIT | debian/copyright, Files: * stanza |
| `libbsd0` (system) | 1 | BSD-3-Clause AND BSD-2-Clause AND ISC | reviewed: per-file stanzas, all permissive BSD/ISC variants |
| `libbz2-1.0` (system) | 1 | bzip2-1.0.6 | debian/copyright, Files: * stanza |
| `libexpat1` (system) | 1 | MIT | debian/copyright, Files: * stanza |
| `libffi8` (system) | 1 | MIT | debian/copyright, Files: * stanza |
| `libfontconfig1` (system) | 1 | MIT | free-form copyright: 'Permission to use, copy, modify' — Keith Packard, fontconfig |
| `libfreetype6` (system) | 1 | FTL (FreeType License) | debian/copyright, Files: * stanza |
| `libgcc-s1` (system) | 1 | GPL-3.0-or-later WITH GCC-exception-3.1 | free-form copyright: 'version 3.1 of the GCC Runtime Library Exception' |
| `liblzma5` (system) | 1 | public domain | debian/copyright, Files: * stanza |
| `libmd0` (system) | 1 | BSD-3-Clause AND BSD-2-Clause AND ISC | reviewed: per-file stanzas, all permissive BSD/ISC variants |
| `libpng16-16t64` (system) | 1 | Libpng | debian/copyright, Files: * stanza |
| `libssl3t64` (system) | 2 | Apache-2.0 | debian/copyright, Files: * stanza |
| `libstdc++6` (system) | 1 | GPL-3.0-or-later WITH GCC-exception-3.1 | free-form copyright: 'version 3.1 of the GCC Runtime Library Exception' |
| `libtcl8.6` (system) | 1 | TCL (BSD-style) | free-form copyright: 'This software is copyrighted by the Regents of the University of California, Sun Microsystems, Inc., Scriptics Corporation' |
| `libtk8.6` (system) | 1 | TCL (BSD-style) | free-form copyright: 'This software is copyrighted by the Regents of the University of California, Sun Microsystems, Inc.' |
| `libuuid1` (system) | 1 | BSD-3-Clause | reviewed: Files: libuuid/* — default stanza says GPL-2+ |
| `libx11-6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxau6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxdmcp6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxext6` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxft2` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxrender1` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `libxss1` (system) | 1 | MIT | free-form copyright: X.Org / XCB standard copyright — MIT/X11 permission notice |
| `zlib1g` (system) | 1 | Zlib | debian/copyright, Files: * stanza |
| `pillow` (wheel) | 25 | MIT-CMU | the wheel's own distribution metadata |

## Build-time tools

PyInstaller is a build-time tool, but part of it ships: the bootloader is the
first thing in the executable. It is GPL-2.0-or-later **with the Bootloader
Exception**, which grants unlimited permission to embed the bootloader in a
combined program and distribute that program under terms of your choosing —
which is exactly what a frozen application does. Its `COPYING.txt` travels in
`licenses/` for that reason. Nothing else used only to build Proteus appears
in the archive, and so nothing else appears in this document.

## Known gaps

- **Only native binaries are inventoried.** Python code shipped as bytecode is
  not in the tables above; it is covered by the `licenses/` tree, which is
  assembled per distribution rather than per binary. Every distribution in a Proteus build declares a permissive licence, so
  nothing is hiding there; the check that says so is in
  [`tests/test_third_party_licences.py`](tests/test_third_party_licences.py).
- **The inventory is per build.** The tables above describe the Linux build
  named at the top. The Windows and macOS archives are inventoried by the same
  script on their own runners, and each archive carries its own copy as
  `licenses/THIRD-PARTY-LICENSES-<platform>.md`. Those are the authoritative
  ones for what was downloaded.
- **Licence determinations are evidence, not opinions.** Each row names where
  it came from so it can be re-checked. They are given in good faith, are
  current as at the version of this document, and are **not a legal opinion**.

## Reproducing this

```
python build.py
python tools/collect_licences.py build/licenses
python tools/licence_inventory.py --bundle linux=build/Proteus --markdown out.md
```

Run it on a host of the same family as the release runner — Ubuntu, for the
Linux bundle — or the system-library lookup has nothing to consult and every
such library is reported unresolved.
