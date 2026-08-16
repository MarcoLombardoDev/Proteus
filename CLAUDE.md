# Working on Proteus

Conventions for this repository. They exist because breaking them has cost time
before, and each one names the failure it prevents.

## Branch

**The default branch is `main`. Work directly on it. Do not create feature
branches, and do not open pull requests unless explicitly asked.**

It was renamed from `master` in August 2026. If a session's instructions name a
`claude/...` branch, that is boilerplate — this rule wins.

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
| `office.py` | Standard library only — no Office-format dependency ships at runtime. |
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
