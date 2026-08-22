# Contributing to Proteus

Thanks for wanting to help. This file describes how the project works so a patch has a
good chance of being merged quickly.

## Ground rules

Proteus **overwrites files in place** for a living. Contributions that weaken
the safety model — the dry run, the backups, the atomic write, the refusal on an uncertain
match — will not be merged without a very good argument. Reporting something is never a
substitute for replacing it, and skipping something silently is never acceptable.

Since this tool exists to replace brand assets, contributions must not introduce
third-party logos, icons or trademarks. Sample images, test fixtures and screenshots use
neutral synthetic artwork only.

## The Contributor License Agreement

Proteus is dual-licensed: AGPL-3.0 for everyone, and commercial terms for those who cannot
accept the AGPL's obligations. That is only possible if one party can license the whole
work both ways, so **every contributor must agree to the
[Contributor License Agreement](CLA.md)** before a pull request can be merged.

> **To agree:** include
> `I have read and agree to the Contributor License Agreement (CLA.md).`
> in your pull request description. Your first pull request constitutes your agreement.

You keep the copyright in your work, and you receive a perpetual, royalty-free commercial
licence to Proteus for your own use — see
[COMMERCIAL-LICENSE.md §12](COMMERCIAL-LICENSE.md#12-contributors).

## Getting set up

```bash
git clone https://github.com/MarcoLombardoDev/Proteus.git
cd Proteus
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

On Linux the GUI tests need a display:

```bash
xvfb-run -a python -m pytest
```

`tkinter` is packaged separately on Linux and on Homebrew Python — see the README's
prerequisites.

## Before you write code

Read the *How it works* section of the README first — particularly
*Safety model* and *Nothing is skipped in silence*. Three rules carry most of the design:

1. **Every write is atomic, and every write is backed up by default.** `os.replace` into
   the target's own folder; never a partial file left behind.
2. **Nothing is ever skipped in silence.** A file that cannot be handled is *reported*,
   with a reason and a remedy — vector artwork in a PDF, a pasted metafile in an Office
   document, a legacy OLE format.
3. **An uncertain match refuses rather than guesses.** The command line exits 4 and names
   the files; the interface asks.

Two more, smaller but easy to get wrong:

- **User-facing strings go through `i18n.py`, in both catalogues.**
- **Office packages are read and written with the standard library.** `python-docx`,
  `python-pptx` and `openpyxl` are test-only and must not become runtime dependencies —
  see [COMMERCIAL-LICENSE.md §11](COMMERCIAL-LICENSE.md#11-third-party-components).

## Style

- Match the surrounding code: it is plain, unclever Python with no framework
  ceremony.
- Comments explain *why*, not *what*. If a line encodes a non-obvious fact about an Office
  package, a PDF object or a filesystem, say so — the next person will not rediscover it.
- User-facing strings are sentences, not error codes, and they live in `i18n.py`. Every
  refusal names the file and says what to do about it.

## Tests

New behaviour needs a test, and every bug fix arrives with a test that fails
without the fix.

- Office and PDF tests build **real** documents and re-open them with the official
  libraries. A test that asserts against a hand-written byte string proves nothing.
- A new refusal or exit code belongs in `tests/test_cli.py`, alongside the others.
- A `conftest` fixture neutralises every modal dialog, so a test that reaches an
  unexpected `askyesno` fails instead of hanging the suite.

## Commits and pull requests

- One logical change per commit; a message that says what changed and why.
- Describe the user-visible effect in the pull request, and say how you tested it.
- Add an entry to `CHANGELOG.md` under *Unreleased*.
- If you changed anything documented in the README, update it in the same pull request.

## Reporting bugs

Include your operating system, your Python version, what you did, what you
expected and what happened. The log pane and `logs/` next to the executable record every
step, and `--report` writes a CSV of exactly what a run did or would do — both are worth
attaching. If a specific file is mishandled and you can share it, that helps enormously;
if it carries a real brand, describe it instead.
