#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Build script for Proteus - Rebranding Tool, using PyInstaller.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: PyInstaller uses ';' on Windows and ':' elsewhere to separate source from
#: destination in --add-data. The value used to be hardcoded to ';', which broke
#: the build on every non-Windows platform.
DATA_SEP = os.pathsep


def force_utf8_output() -> None:
    """
    Make stdout and stderr able to carry the emoji used in the progress output.

    On Windows the default encoding is a legacy code page — cp1252 on the CI
    runners, cp850 in a plain console — where printing an emoji raises
    UnicodeEncodeError. That killed the build on its very first status line,
    before any actual work started, and then killed the error handler too when
    it tried to report the failure with another emoji.

    `errors="replace"` keeps this safe even where UTF-8 is unavailable: an
    unrepresentable character degrades to a placeholder instead of raising.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # Not a reconfigurable text stream (redirected, wrapped, closed).
            pass


def python_launcher() -> list[str]:
    """
    Command used to invoke Python.

    `py` only exists on Windows and not inside virtual environments, so we fall
    back to the interpreter running this script, which is always correct.
    """
    if os.name == "nt":
        try:
            probe = subprocess.run(["py", "--version"], capture_output=True, text=True)
            if probe.returncode == 0:
                return ["py"]
        except (FileNotFoundError, OSError):
            pass
    return [sys.executable]


class RebrandingToolBuilder:
    def __init__(self) -> None:
        self.app_name = "Proteus"
        #: Second, console-attached binary for the command line. On Windows a
        #: --windowed executable has no console at all: every print() from the
        #: CLI would vanish and a scheduled job could not be diagnosed. The two
        #: binaries share the same entry point and differ only in that flag.
        self.cli_name = "proteus-cli"
        self.main_script = "main.py"
        self.output_dir = "dist"
        self.python = python_launcher()
        self.exe_suffix = ".exe" if os.name == "nt" else ""

    # ------------------------------------------------------------------

    def _run(self, args: list[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(self.python + args, capture_output=True, text=True, **kwargs)

    def _ensure_module(self, module: str, package: str) -> bool:
        probe = self._run(["-c", f"import {module}"])
        if probe.returncode == 0:
            print(f"✅ {package} available")
            return True

        print(f"⚠️  {package} not found, installing...")
        install = self._run(["-m", "pip", "install", package])
        if install.returncode != 0:
            print(f"❌ Failed to install {package}: {install.stderr.strip()[-500:]}")
            return False
        print(f"✅ {package} installed")
        return True

    def check_prerequisites(self) -> bool:
        print("🔍 Checking prerequisites...")
        print(f"✅ Python: {sys.version.split()[0]} ({' '.join(self.python)})")

        if not self._ensure_module("PyInstaller", "pyinstaller"):
            return False
        if not self._ensure_module("PIL", "pillow"):
            return False
        # PDF support. Optional at runtime, but the shipped executable should
        # have it: a user who ticks the PDF box in a frozen build cannot
        # pip-install anything.
        self._ensure_module("pypdf", "pypdf")
        # ttkbootstrap is optional: the app also works without it, on ttk themes.
        self._ensure_module("ttkbootstrap", "ttkbootstrap")

        for required in (self.main_script, "rebranding_tool.py", "core.py",
                         "i18n.py", "office.py", "cli.py", "pdf.py", "paths.py"):
            if not os.path.exists(required):
                print(f"❌ File not found: {required}")
                return False
            print(f"✅ Found file: {required}")

        return True

    def clean_temp_directories(self) -> None:
        print("🧹 Cleaning temporary folders...")
        for temp_dir in ("build", "dist", "__pycache__"):
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"  ✅ {temp_dir} removed")
                except OSError as exc:
                    print(f"  ⚠️  Could not remove {temp_dir}: {exc}")
        time.sleep(1)

    def build_executable(self, name: str | None = None, windowed: bool = True) -> str | None:
        name = name or self.app_name
        kind = "windowed" if windowed else "console"
        print(f"🔨 Building the {kind} executable ({name})...")

        hidden_imports = [
            "tkinter", "tkinter.ttk", "tkinter.filedialog",
            "tkinter.messagebox", "tkinter.scrolledtext",
            "PIL", "PIL.Image", "PIL.ImageTk",
            # PyInstaller does not find it on its own: without it ImageTk
            # fails at runtime with "No module named 'PIL._tkinter_finder'" and
            # the image previews disappear from the .exe.
            "PIL._tkinter_finder",
            "core", "rebranding_tool", "i18n", "office", "cli", "pdf", "paths",
            "pypdf",
        ]

        add_data = []
        for asset in ("app.ico",):
            if os.path.exists(asset):
                add_data.append(f"{asset}{DATA_SEP}.")
            else:
                print(f"⚠️  Missing resource, not bundled: {asset}")

        excludes = [
            "matplotlib", "numpy", "pandas", "scipy",
            "PyQt5", "PyQt6", "PySide2", "PySide6",
            "jupyter", "IPython", "sphinx", "pytest",
            "win32com", "pythoncom",
        ]

        cmd = [
            "-m", "PyInstaller",
            "--onefile",
            "--windowed" if windowed else "--console",
            f"--name={name}",
            "--noconfirm",
        ]

        # Only the first pass clears the cache: doing it again would make the
        # second binary a full rebuild for no benefit.
        if windowed:
            cmd.append("--clean")

        if os.path.exists("app.ico"):
            cmd.append("--icon=app.ico")

        for imp in hidden_imports:
            cmd += ["--hidden-import", imp]
        for data in add_data:
            cmd += ["--add-data", data]
        for exc in excludes:
            cmd += ["--exclude-module", exc]

        # --collect-all gathers modules, submodules and resources in one go.
        # The previous version combined it with --add-data on the same folder
        # plus --collect-submodules/--collect-data, duplicating the files.
        if self._run(["-c", "import ttkbootstrap"]).returncode == 0:
            cmd += ["--collect-all", "ttkbootstrap"]
            print("✅ ttkbootstrap resources bundled")

        cmd.append(self.main_script)

        print("🚀 Starting the build...")
        try:
            result = self._run(cmd, timeout=900)
        except subprocess.TimeoutExpired:
            print("❌ Build timed out (>15 minutes)")
            return None

        if result.returncode != 0:
            print(f"❌ Build failed (exit code {result.returncode}):")
            if result.stdout:
                print(f"   STDOUT: {result.stdout[-2000:]}")
            if result.stderr:
                print(f"   STDERR: {result.stderr[-2000:]}")
            return None

        exe_path = os.path.join(self.output_dir, f"{name}{self.exe_suffix}")
        if not os.path.exists(exe_path):
            print(f"❌ Executable not found after the build: {exe_path}")
            return None

        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"✅ {name} built — {exe_path} ({size_mb:.1f} MB)")
        return exe_path

    def create_distribution(self, exe_path: str, cli_path: str | None = None) -> bool:
        print("📦 Preparing the distribution...")
        logs_dir = os.path.join(self.output_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        print(f"  📁 Folder created: {logs_dir}")

        lines = [
            "Proteus - Rebranding Tool",
            "=========================",
            "",
            f"Interface:    {os.path.basename(exe_path)}",
        ]
        if cli_path:
            lines += [
                f"Command line: {os.path.basename(cli_path)}"
                " --help   (for scripts and scheduled jobs)",
                "",
                "The command line never writes anything unless --apply is given.",
            ]
        lines += [
            "",
            "Logs are written to the 'logs' folder next to the executable.",
            "If the executable lives in a read-only location, logs go to",
            "%LOCALAPPDATA%\\Proteus\\logs instead.",
            "",
        ]

        readme = Path(self.output_dir) / "READ_ME_FIRST.txt"
        readme.write_text("\n".join(lines), encoding="utf-8")
        return True

    def build(self) -> bool:
        print("=" * 55)
        print("   PROTEUS - BUILD")
        print("=" * 55)
        print()

        if not self.check_prerequisites():
            print("\n❌ BUILD FAILED: prerequisites not met")
            return False

        print()
        self.clean_temp_directories()
        print()

        exe_path = self.build_executable()
        if not exe_path:
            print("\n❌ BUILD FAILED: error during compilation")
            return False

        print()
        cli_path = self.build_executable(self.cli_name, windowed=False)
        if not cli_path:
            print("\n❌ BUILD FAILED: error while building the command line")
            return False

        print()
        self.create_distribution(exe_path, cli_path)
        print()
        print("=" * 55)
        print("   BUILD COMPLETED SUCCESSFULLY!")
        print("=" * 55)
        print(f"📁 Interface:    {exe_path}")
        print(f"📁 Command line: {cli_path}")
        print(f"📁 Logs: {os.path.join(self.output_dir, 'logs')}")
        print()
        print("✅ The application is ready for distribution!")
        return True


def main() -> int:
    # Before anything is printed: the first status line contains an emoji.
    force_utf8_output()

    builder = RebrandingToolBuilder()
    try:
        return 0 if builder.build() else 1
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by the user")
        return 1
    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
