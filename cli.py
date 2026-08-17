#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Proteus - command line interface, for unattended use.

The graphical interface protects the user with previews, colours and
confirmation dialogs. A scheduled job has none of that: nobody is watching, so
the safeguards have to be built into the defaults instead.

  * a run is a **dry run** unless `--apply` is given;
  * backups are on unless `--no-backup` is given;
  * a run that would write refuses to start when hits are too uncertain to be
    accepted without human eyes (`--max-uncertain`).

The exit code is the real return value — a scheduler reads that, not the log:

    0  finished, everything replaced (or simulated) cleanly
    1  finished, but some replacements failed
    2  nothing matched
    3  the request itself was wrong (bad folders, bad pattern)
    4  refused on safety grounds
    5  finished, but something needs a human: see the reported problems
    130 interrupted

Exit code 5 exists because of one rule that holds everywhere in Proteus: if a
file that may carry the logo cannot be dealt with — an encrypted or signed PDF,
a vector logo, an unreadable image — it is **reported, never dropped**. In a
scheduled job the exit code is the only thing anyone reads, so a run that left
work undone must not look identical to a clean one.

Examples
--------
    # See what would happen, changing nothing
    python -m cli --scan /srv/share --source ./new_logos --pattern "logo*.png"

    # Find the old logo wherever it hides, documents included, and write
    python -m cli --scan /srv/share --source ./new_logos \\
                  --reference ./old/logo.png --office --apply --report out.csv
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import core
import i18n
import paths

# Exit codes. Named because a scheduler branches on them.
EXIT_OK = 0
EXIT_ERRORS = 1
EXIT_NOTHING_FOUND = 2
EXIT_BAD_REQUEST = 3
EXIT_REFUSED = 4
#: The run did what it could, but some findings need manual intervention.
EXIT_ATTENTION = 5
EXIT_INTERRUPTED = 130

#: How often progress is reported, in seconds. A scheduled job writes to a log
#: file, so a line per file would produce megabytes of noise.
PROGRESS_INTERVAL = 2.0


class Reporter:
    """Console output that is readable both live and in a log file."""

    def __init__(self, quiet: bool = False, verbose: bool = False):
        self.quiet = quiet
        self.verbose = verbose
        self._last = 0.0
        #: Problems reported during the run, kept so the summary and the exit
        #: code can account for them.
        self.findings: list = []

    def say(self, message: str) -> None:
        if not self.quiet:
            print(message, flush=True)

    def detail(self, message: str) -> None:
        if self.verbose and not self.quiet:
            print(message, flush=True)

    def problem(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    def finding(self, problem) -> None:
        """
        Report something the user must handle by hand.

        Goes to stderr and survives --quiet: the whole reason this exists is
        that it must not be possible to miss it.
        """
        self.findings.append(problem)
        print(f"  ! {problem.path}", file=sys.stderr, flush=True)
        print(f"    {problem.reason}", file=sys.stderr, flush=True)
        if problem.hint:
            print(f"    -> {problem.hint}", file=sys.stderr, flush=True)

    def progress(self, label: str, done: int, total: int) -> None:
        """Throttled progress, so a long scan does not flood the log."""
        if self.quiet or not total:
            return
        now = time.monotonic()
        if done < total and now - self._last < PROGRESS_INTERVAL:
            return
        self._last = now
        print(f"  {label}: {done}/{total} ({done * 100 // total}%)", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proteus",
        description="Bulk-replace logos across a folder tree, unattended.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 ok · 1 errors · 2 nothing found · 3 bad request "
               "· 4 refused on safety grounds · 5 finished, but something "
               "needs a human",
    )

    parser.add_argument("--version", action="version",
                        version=f"{core.APP_NAME} {core.APP_TAGLINE} {core.APP_VERSION}")

    what = parser.add_argument_group("what to scan")
    what.add_argument("--scan", metavar="FOLDER",
                      help="folder to search for files to replace")
    what.add_argument("--source", metavar="FOLDER",
                      help="folder holding the new logos")

    how = parser.add_argument_group("how to find it")
    how.add_argument("--pattern", default="", metavar="GLOB",
                     help='wildcard pattern, e.g. "logo*.png". Several may be '
                          'separated by ";". With --reference it acts as a '
                          'pre-filter.')
    how.add_argument("--reference", nargs="+", default=[], metavar="IMAGE",
                     help="one or more copies of the OLD logo: find images that "
                          "look like them, whatever they are called")
    how.add_argument("--similarity", type=int, default=int(core.DEFAULT_SIMILARITY * 100),
                     metavar="PCT",
                     help="minimum visual similarity for --reference "
                          f"(default: {int(core.DEFAULT_SIMILARITY * 100)})")
    how.add_argument("--office", action="store_true",
                     help="also look inside .docx/.pptx/.xlsx documents")
    how.add_argument("--pdf", action="store_true",
                     help="also look inside PDF files (raster images only; a "
                          "vector logo is reported, not replaced)")

    action = parser.add_argument_group("what to do")
    action.add_argument("--apply", action="store_true",
                        help="actually write. Without it nothing is modified.")
    action.add_argument("--no-backup", action="store_true",
                        help="do not keep a .bak of each original (not advised)")
    action.add_argument("--restore", action="store_true",
                        help="restore originals from their backups and exit")
    action.add_argument("--audit", action="store_true",
                        help="inventory only: report what carries the logo and "
                             "where, without pairing or replacing. --source is "
                             "not needed.")

    safety = parser.add_argument_group("safety")
    safety.add_argument("--max-uncertain", type=int, default=0, metavar="N",
                        help="refuse to --apply when more than N hits are below "
                             f"{int(core.SIMILARITY_CONFIDENT * 100)}%% similarity "
                             "(default: 0, since nobody is watching)")
    safety.add_argument("--allow-distortion", action="store_true",
                        help="allow replacements that would stretch a picture "
                             "inside a document")

    out = parser.add_argument_group("output")
    out.add_argument("--report", metavar="FILE.csv",
                     help="write a CSV report of what was found and done")
    out.add_argument("--language", default=i18n.DEFAULT_LANGUAGE,
                     choices=sorted(i18n.LANGUAGES),
                     help="language of messages and report headers")
    out.add_argument("--quiet", action="store_true", help="only report problems")
    out.add_argument("--verbose", action="store_true", help="one line per file")

    return parser


def collect_targets(args, reporter: Reporter) -> list[core.FileInfo]:
    """Everything the run should consider replacing."""
    by_content = bool(args.reference)
    targets: list[core.FileInfo] = []

    def walk_error(path: str, exc: Exception) -> None:
        """
        A folder the scan could not enter is a finding, not a log line.

        "We scanned everything" is false while one branch of the tree was
        refused, and only the user can say whether that branch mattered.
        """
        if isinstance(exc, OSError):
            reason, hint = paths.describe_unreadable_folder(exc, path)
        else:
            reason, hint = str(exc), ""
        reporter.finding(core.Problem(path, reason, hint))

    exclude = ([args.source] if args.source and core.is_within(args.source, args.scan)
               else [])

    if by_content:
        reporter.say("Searching by image content...")
        hits = core.scan_by_content(
            args.scan, args.reference, threshold=args.similarity / 100.0,
            pattern=args.pattern, exclude_dirs=exclude, on_error=walk_error,
            progress=lambda d, t: reporter.progress("compared", d, t),
        )
        targets.extend(core.FileInfo.from_path(path, similarity=score)
                       for path, score in hits)
    elif args.pattern:
        reporter.say(f"Searching by name: {args.pattern}")
        for path in core.scan_files(args.scan, args.pattern,
                                    exclude_dirs=exclude, on_error=walk_error):
            try:
                targets.append(core.FileInfo.from_path(path))
            except OSError as exc:
                reporter.problem(f"  cannot read {path}: {exc}")

    if args.office:
        reporter.say("Looking inside Office documents...")
        targets.extend(core.scan_office_documents(
            args.scan,
            references=args.reference if by_content else (),
            threshold=args.similarity / 100.0,
            exclude_dirs=exclude, on_error=walk_error,
            on_problem=reporter.finding,
            progress=lambda d, t: reporter.progress("documents", d, t),
        ))

    if args.pdf:
        reporter.say("Looking inside PDF files...")
        targets.extend(core.scan_pdf_documents(
            args.scan,
            patterns=core.parse_patterns(args.pattern),
            references=args.reference if by_content else (),
            threshold=args.similarity / 100.0,
            exclude_dirs=exclude, on_error=walk_error,
            on_problem=reporter.finding,
            progress=lambda d, t: reporter.progress("PDFs", d, t),
        ))

    return targets


def run_audit(args, reporter: Reporter) -> int:
    """
    Inventory the tree without pairing or replacing anything.

    This is step one of a rebranding: before anybody commits to a date, they
    need to know how many copies of the logo exist and in which departments.
    `--source` is not required, because at that stage the new logo may not have
    been designed yet — and requiring it would have forced people to invent an
    empty folder just to be allowed to look.
    """
    if not os.path.isdir(args.scan):
        reporter.problem(f"Not a folder: {args.scan}")
        return EXIT_BAD_REQUEST
    if args.reference:
        for problem in core.validate_references(args.reference):
            reporter.problem(problem)
            return EXIT_BAD_REQUEST

    reporter.say(f"Inventory of {args.scan}")
    targets = collect_targets(args, reporter)

    breakdown = core.audit_breakdown(targets)
    reporter.say("")
    reporter.say(f"{breakdown['files']} file(s) carry the logo"
                 + (f", {breakdown['embedded']} of them inside documents"
                    if breakdown["embedded"] else "")
                 + f" — {core.format_size(breakdown['bytes'])} in total")

    if breakdown["by_format"]:
        reporter.say("")
        reporter.say("By format:")
        for fmt, count in breakdown["by_format"].items():
            reporter.say(f"  {count:>6}  {fmt}")

    if breakdown["by_folder"]:
        reporter.say("")
        reporter.say("By folder:")
        # Truncated on purpose, and the truncation is stated: a silent top-20
        # would read as the whole picture.
        shown = list(breakdown["by_folder"].items())
        for folder, count in shown[:20]:
            reporter.say(f"  {count:>6}  {folder}")
        if len(shown) > 20:
            reporter.say(f"  ... and {len(shown) - 20} more folders "
                         f"(all of them are in the CSV)")

    if reporter.findings:
        reporter.say("")
        reporter.say(f"{len(reporter.findings)} finding(s) will need manual work "
                     f"— listed on stderr and in the report")

    if args.report:
        try:
            core.export_audit_csv(targets, reporter.findings, args.report)
            reporter.say(f"Report written to {args.report}")
        except OSError as exc:
            reporter.problem(f"Could not write the report: {exc}")

    if not targets:
        return _finish(EXIT_NOTHING_FOUND, reporter)
    return _finish(EXIT_OK, reporter)


def check_safety(args, matches: list[core.Match], reporter: Reporter) -> int | None:
    """
    Refuse a writing run that a human would have been expected to review.

    Returns an exit code to stop with, or None to carry on. Only applies with
    `--apply`: a dry run is exactly how you find these out.
    """
    if not args.apply:
        return None

    uncertain = [m for m in matches if m.target.needs_review]
    if len(uncertain) > args.max_uncertain:
        reporter.problem(
            f"Refusing to write: {len(uncertain)} hits are below "
            f"{int(core.SIMILARITY_CONFIDENT * 100)}% similarity and nobody is "
            f"here to look at them (--max-uncertain is {args.max_uncertain})."
        )
        for match in uncertain[:10]:
            reporter.problem(f"  {match.target.similarity_str}  {match.target.name}")
        if len(uncertain) > 10:
            reporter.problem(f"  ... and {len(uncertain) - 10} more")
        reporter.problem("Raise --similarity, review them in the interface, or "
                         "raise --max-uncertain deliberately.")
        return EXIT_REFUSED

    if not args.allow_distortion:
        distorting = [m for m in matches if m.distorts]
        if distorting:
            reporter.problem(
                f"Refusing to write: {len(distorting)} replacements would stretch "
                "the picture, because inside a document the frame keeps its own "
                "proportions."
            )
            for match in distorting[:10]:
                reporter.problem(f"  {match.target.name}: "
                                 f"{match.target.dim_str} -> {match.source_dim_str}")
            reporter.problem("Use matching proportions, or --allow-distortion.")
            return EXIT_REFUSED

    return None


def run_restore(args, reporter: Reporter) -> int:
    backups = core.find_backups(args.scan)
    if not backups:
        reporter.say(f"No backup found in {args.scan}")
        return EXIT_NOTHING_FOUND

    distinct = len({core.backup_origin(b) for b in backups})
    reporter.say(f"Restoring {distinct} files from {len(backups)} backups...")

    if not args.apply:
        reporter.say("Dry run: nothing was restored. Add --apply to do it.")
        return EXIT_OK

    report = core.restore_backups(
        args.scan, progress=lambda d, t, o: reporter.progress("restored", d, t))
    reporter.say(f"Restored: {report.ok}, errors: {report.errors}")
    return EXIT_ERRORS if report.errors else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    i18n.set_language(args.language)
    reporter = Reporter(quiet=args.quiet, verbose=args.verbose)

    if not args.scan:
        parser.error("--scan is required")
    if args.restore:
        if not os.path.isdir(args.scan):
            reporter.problem(f"Not a folder: {args.scan}")
            return EXIT_BAD_REQUEST
        return run_restore(args, reporter)

    if args.audit and args.apply:
        parser.error("--audit never writes, so --apply makes no sense with it")
    if not args.source and not args.audit:
        parser.error("--source is required (or use --restore, or --audit)")
    if not args.pattern and not args.reference and not args.office and not args.pdf:
        parser.error("give at least one of --pattern, --reference, --office or --pdf")

    if args.audit:
        return run_audit(args, reporter)

    problems = core.validate_config(
        args.source, args.scan, args.pattern,
        require_pattern=not (args.reference or args.office or args.pdf))
    if args.reference:
        problems += core.validate_references(args.reference)
    if problems:
        for problem in problems:
            reporter.problem(problem)
        return EXIT_BAD_REQUEST

    for warning in core.config_warnings(args.source, args.scan):
        reporter.say(f"Note: {warning}")

    # --- find ---
    targets = collect_targets(args, reporter)
    if not targets:
        reporter.say("Nothing matched.")
        # A scan that found nothing replaceable but did hit problems has not
        # succeeded — it has found work for a person.
        return _finish(EXIT_NOTHING_FOUND, reporter)

    embedded = sum(1 for target in targets if target.embedded)
    reporter.say(f"Found {len(targets)} files"
                 + (f" ({embedded} inside documents)" if embedded else ""))

    # --- pair ---
    sources = [core.FileInfo.from_path(path)
               for path in core.collect_source_files(args.source)]
    if not sources:
        reporter.problem(f"No image in the source folder: {args.source}")
        return EXIT_BAD_REQUEST

    matches = core.build_matches(targets, sources,
                                 progress=lambda d, t: reporter.progress("paired", d, t))
    usable = [match for match in matches if match.source is not None]
    unmatched = len(matches) - len(usable)
    reporter.say(f"Paired {len(usable)} of {len(matches)}"
                 + (f", {unmatched} without a match" if unmatched else ""))

    for match in usable:
        reporter.detail(f"  {match.target.name} <- {match.source_name} "
                        f"[{match.quality_label}]")

    if not usable:
        reporter.say("Nothing to replace.")
        _write_report(args, matches, reporter)
        return _finish(EXIT_NOTHING_FOUND, reporter)

    refusal = check_safety(args, usable, reporter)
    if refusal is not None:
        _write_report(args, matches, reporter)
        return refusal

    # --- replace ---
    dry_run = not args.apply
    reporter.say("Simulating..." if dry_run else "Replacing...")

    report = core.replace_all(
        usable, backup=not args.no_backup, dry_run=dry_run,
        progress=lambda d, t, o: reporter.progress("processed", d, t),
    )

    for outcome in report.outcomes:
        if outcome.status == "error":
            reporter.problem(f"  failed: {outcome.target}: {outcome.message}")
        elif outcome.status == "skipped":
            reporter.detail(f"  skipped: {outcome.target}: {outcome.message}")

    reporter.say(f"{'Would replace' if dry_run else 'Replaced'}: {report.ok}, "
                 f"skipped: {report.skipped}, errors: {report.errors}")
    if dry_run:
        reporter.say("Dry run: nothing was written. Add --apply to do it.")

    _write_report(args, matches, reporter, report)
    if report.errors:
        return EXIT_ERRORS
    return _finish(EXIT_OK, reporter)


def _finish(code: int, reporter: Reporter) -> int:
    """
    Final word on the run, accounting for anything left to a human.

    A clean exit code on a run that quietly skipped three logos is the failure
    this whole mechanism exists to prevent: in an unattended job the exit code
    is all anyone sees, so unfinished business has to change it.
    """
    if not reporter.findings:
        return code
    reporter.problem(
        f"{len(reporter.findings)} finding(s) need manual intervention "
        f"(listed above). Nothing else was left undone.")
    return EXIT_ATTENTION if code == EXIT_OK else code


def _write_report(args, matches, reporter: Reporter,
                  report: core.ReplaceReport | None = None) -> None:
    if not args.report:
        return
    try:
        if report is not None and report.outcomes:
            core.export_report_csv(report, args.report)
        else:
            core.export_matches_csv(matches, args.report)
        reporter.say(f"Report written to {args.report}")
    except OSError as exc:
        reporter.problem(f"Could not write the report: {exc}")


def entry_point() -> int:
    """Wrapper that turns an interruption into the conventional exit code."""
    # The progress output carries no emoji, but core messages might, and a
    # Windows console defaults to a legacy code page.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    try:
        return main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(entry_point())
