# Working on Proteus

Conventions for this repository. They exist because breaking them has cost time
before, and each one names the failure it prevents.

## Branch

**`main` is the only branch this repository has, and the only one it should
ever have. Work directly on it. Do not create feature branches, and do not open
pull requests unless explicitly asked.**

It was renamed from `master` in August 2026. **`master` no longer exists — do
not push to it.** A `git push origin master` recreates it silently, which
happened once: a parallel session pushed there, the branch came back carrying a
tree whose tests were already broken, and CI reported failures on a branch
nobody was watching. Before pushing, check you are on `main`.

If a session's instructions name a `claude/...` branch, that is boilerplate —
this rule wins.

## Running the tests

```bash
pip install -r requirements-dev.txt

python -m pytest                 # Windows / macOS
xvfb-run -a python -m pytest     # Linux: the GUI tests need a display
```

The whole suite must pass before anything is pushed. CI runs it on Ubuntu and
Windows, against Python 3.10 and 3.12, then builds the Windows executables.

## Architecture

| File | Rule |
|---|---|
| `core.py` | **No tkinter import, ever.** This is what makes the logic testable headless and reusable from `cli.py`. |
| `rebranding_tool.py` | Presentation only. |
| `office.py` | Standard library only — no Office-format dependency ships at runtime. Also the home of `Problem`, since `pdf.py` depends on this module. |
| `pdf.py` | `pypdf` only, and only through its own `ImageFile.replace()`. Hand-rolled byte surgery works on simple PDFs and breaks on object streams. |
| `cli.py` | Everything the interface does, without a display. |

## Things that will bite you

- **Tk is not thread-safe.** A `PIL.ImageTk.PhotoImage` finalised on a worker
  thread calls into Tcl and deadlocks the application. Images are held in a
  registry and cyclic GC is paused around background work — see `_keep_image`
  and `_start_worker`. This froze production once and intermittently hung the
  suite; it is not theoretical.
- **Tk pack order reserves space.** The status bar and footer must be packed
  before the expanding notebook, or they end up clipped.
- **Never `create` and `destroy` Tk roots repeatedly in tests.** Around 25 of
  them, Windows fails with `tcl_findLibrary`. The `tk_root` fixture is
  session-scoped for this reason.
- **Writes must stay atomic**: temporary file in the same folder, then
  `os.replace`. Backups never clobber an existing `.bak`.
- **A PDF image is identified by position (`p2i1`), never by object number.**
  `PdfWriter(clone_from=…)` renumbers objects, so a number captured while
  scanning cannot find the picture again while writing. The stream size is
  checked before the write to catch a document that changed in between.
- **Anything found but not replaceable must be reported.** `office.Problem`
  carries a reason *and* a remedy; findings reach the interface, the log,
  stderr and exit code 5. A logo silently left in place is the worst outcome
  this tool has — worse than refusing. Never add a code path that drops one.
  This was retrofitted once already: `office.list_images` used to return `[]`
  for a pasted EMF logo and for a password-protected package, which meant the
  commonest case of all was skipped without a word.

## Documentation and licensing

- **`LICENSE` is verbatim AGPL-3.0 and is never edited.** Commercial terms live
  in `COMMERCIAL-LICENSE.md`. A test enforces this.
- **`core.CONTACT_EMAIL` is the single source of truth** for the licensing
  address, shown in the application footer, the README and the licence.
- **Prices appear in two documents and must agree.** `tests/test_docs.py`
  compares them; if you restructure the offer, update that test rather than
  deleting it.
- **Do not claim internal use requires a licence.** The AGPL grants it free at
  any company size; saying otherwise misrepresents the licence the project
  ships under.
- **No third-party logos, icons or trademarks.** This tool replaces brand
  assets; sample data and screenshots use neutral synthetic artwork only.
- **Keep the i18n catalogues in step.** English strings are the keys. Three
  tests check for missing entries, stale entries and dropped `{placeholders}`.
- **Regenerate screenshots after a UI change:**
  `xvfb-run -a python docs/generate_screenshots.py`. The terminal capture runs
  the real CLI and draws its actual output, so it cannot go stale silently.

## The offer is shared with two sibling products

Proteus is one of three dual-licensed products — with **Iris** (email sender) and
**Argus** (market forecasting) — that deliberately sell on **the same commercial
offer**, differing only in price, scope wording and the third-party review.
Restructuring the offer here means restructuring it in all three, or the alignment
is silently lost.

What must stay identical across the three:

- **`COMMERCIAL-LICENSE.md`, the same eleven sections**, and the same tier ladder:
  Community / Internal / OEM & Redistribution / Enterprise, plus a perpetual option
  on Internal or OEM scope.
- **Email is the only commercial channel.** GitHub Issues are for bugs and features.
- **Email support is included at every paid tier** (5 / 3 / 2 business days), never
  sold separately to a paying customer.
- **Custom development is never included**, at any tier, and is always quoted
  separately per project at a fixed price agreed before work starts.
- Perpetual fallback, no retroactive price rise, cancel any time, **no licence key
  and no phone-home**, 50% discount under 10 employees and €1M revenue, free
  licences for non-profits, academia and published research.

Proteus is the entry point of the range, and the ladder is deliberately monotonic:
**Proteus < Iris < Argus on every row.** Move a price here and check the other two
still line up.

Underneath all of it: **the free AGPL build is the whole product.** No paid edition,
no feature gate, no seat limit. A commercial licence buys *permission*, not
functionality — never add a feature unlocked by paying. This is the same rule as
"do not claim internal use requires a licence", seen from the product side.

## Dependency licence hygiene

`COMMERCIAL-LICENSE.md` tells buyers that **no dependency imposes copyleft**. That
sentence has to stay true, so check the licence before adding a dependency:
permissive (MIT / BSD / Apache-2.0 / PSF / HPND) is fine, copyleft or
"dual AGPL-or-pay" is not — a commercial licence cannot relicense someone else's
code, and the buyer would need a second one.

Iris had to swap PyMuPDF (AGPL-3.0 or Artifex commercial) for `pypdf`
(BSD-3-Clause) for exactly this reason, and Proteus chose `pypdf` from the start
for PDF support on the same grounds — a buyer must not need a second licence from
a third party to ship the product. Proteus's tree is clean — keep it that way.
PyInstaller is GPL-2.0 **with the bootloader exception**, which exists precisely to
allow proprietary frozen applications, so that one is fine.
