#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script per la compilazione di Rebranding Tool con PyInstaller.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: PyInstaller usa ';' su Windows e ':' altrove per separare sorgente e
#: destinazione in --add-data. Il valore era cablato a ';' e rompeva la build
#: su qualunque piattaforma non Windows.
DATA_SEP = os.pathsep


def python_launcher() -> list[str]:
    """
    Comando da usare per invocare Python.

    `py` esiste solo su Windows e non nei virtual environment: si ripiega
    sull'interprete che sta eseguendo questo script, che è sempre corretto.
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
        self.app_name = "RebrandingTool"
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
            print(f"✅ {package} disponibile")
            return True

        print(f"⚠️  {package} non trovato, installazione in corso...")
        install = self._run(["-m", "pip", "install", package])
        if install.returncode != 0:
            print(f"❌ Errore installazione {package}: {install.stderr.strip()[-500:]}")
            return False
        print(f"✅ {package} installato")
        return True

    def check_prerequisites(self) -> bool:
        print("🔍 Verifica prerequisiti...")
        print(f"✅ Python: {sys.version.split()[0]} ({' '.join(self.python)})")

        if not self._ensure_module("PyInstaller", "pyinstaller"):
            return False
        if not self._ensure_module("PIL", "pillow"):
            return False
        # ttkbootstrap è opzionale: l'app funziona anche senza, con i temi ttk.
        self._ensure_module("ttkbootstrap", "ttkbootstrap")

        for required in (self.main_script, "rebranding_tool.py", "core.py"):
            if not os.path.exists(required):
                print(f"❌ File non trovato: {required}")
                return False
            print(f"✅ File trovato: {required}")

        return True

    def clean_temp_directories(self) -> None:
        print("🧹 Pulizia cartelle temporanee...")
        for temp_dir in ("build", "dist", "__pycache__"):
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"  ✅ {temp_dir} rimosso")
                except OSError as exc:
                    print(f"  ⚠️  Impossibile rimuovere {temp_dir}: {exc}")
        time.sleep(1)

    def build_executable(self) -> str | None:
        print("🔨 Compilazione eseguibile...")

        hidden_imports = [
            "tkinter", "tkinter.ttk", "tkinter.filedialog",
            "tkinter.messagebox", "tkinter.scrolledtext",
            "PIL", "PIL.Image", "PIL.ImageTk",
            # PyInstaller non lo trova da solo: senza, ImageTk fallisce a
            # runtime con "No module named 'PIL._tkinter_finder'" e nel .exe
            # spariscono banner e anteprime.
            "PIL._tkinter_finder",
            "core", "rebranding_tool",
        ]

        add_data = []
        for asset in ("sace.ico", "banner.jpg"):
            if os.path.exists(asset):
                add_data.append(f"{asset}{DATA_SEP}.")
            else:
                print(f"⚠️  Risorsa mancante, non inclusa: {asset}")

        excludes = [
            "matplotlib", "numpy", "pandas", "scipy",
            "PyQt5", "PyQt6", "PySide2", "PySide6",
            "jupyter", "IPython", "sphinx", "pytest",
            "win32com", "pythoncom",
        ]

        cmd = [
            "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            f"--name={self.app_name}",
            "--noconfirm",
            "--clean",
        ]

        if os.path.exists("sace.ico"):
            cmd.append("--icon=sace.ico")

        for imp in hidden_imports:
            cmd += ["--hidden-import", imp]
        for data in add_data:
            cmd += ["--add-data", data]
        for exc in excludes:
            cmd += ["--exclude-module", exc]

        # --collect-all raccoglie moduli, sottomoduli e risorse in un colpo solo.
        # La versione precedente lo combinava con --add-data sulla stessa
        # cartella e con --collect-submodules/--collect-data, duplicando i file.
        if self._run(["-c", "import ttkbootstrap"]).returncode == 0:
            cmd += ["--collect-all", "ttkbootstrap"]
            print("✅ Risorse ttkbootstrap incluse")

        cmd.append(self.main_script)

        print("🚀 Avvio compilazione...")
        try:
            result = self._run(cmd, timeout=900)
        except subprocess.TimeoutExpired:
            print("❌ Timeout compilazione (>15 minuti)")
            return None

        if result.returncode != 0:
            print(f"❌ Errore compilazione (codice {result.returncode}):")
            if result.stdout:
                print(f"   STDOUT: {result.stdout[-2000:]}")
            if result.stderr:
                print(f"   STDERR: {result.stderr[-2000:]}")
            return None

        exe_path = os.path.join(self.output_dir, f"{self.app_name}{self.exe_suffix}")
        if not os.path.exists(exe_path):
            print(f"❌ Eseguibile non trovato dopo la compilazione: {exe_path}")
            return None

        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("✅ Compilazione completata!")
        print(f"📁 Eseguibile: {exe_path}")
        print(f"📏 Dimensione: {size_mb:.1f} MB")
        return exe_path

    def create_distribution(self, exe_path: str) -> bool:
        print("📦 Preparazione distribuzione...")
        logs_dir = os.path.join(self.output_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        print(f"  📁 Cartella creata: {logs_dir}")

        readme = Path(self.output_dir) / "LEGGIMI.txt"
        readme.write_text(
            "Rebranding Tool - SACE S.p.A\n"
            "============================\n\n"
            f"Eseguibile: {os.path.basename(exe_path)}\n"
            "I log vengono scritti nella cartella 'logs' accanto all'eseguibile.\n"
            "Se l'eseguibile si trova in un percorso di sola lettura, i log\n"
            "finiscono in %LOCALAPPDATA%\\RebrandingTool\\logs.\n",
            encoding="utf-8",
        )
        return True

    def build(self) -> bool:
        print("=" * 55)
        print("   REBRANDING TOOL - BUILD")
        print("=" * 55)
        print()

        if not self.check_prerequisites():
            print("\n❌ BUILD FALLITO: prerequisiti non soddisfatti")
            return False

        print()
        self.clean_temp_directories()
        print()

        exe_path = self.build_executable()
        if not exe_path:
            print("\n❌ BUILD FALLITO: errore durante la compilazione")
            return False

        print()
        self.create_distribution(exe_path)
        print()
        print("=" * 55)
        print("   BUILD COMPLETATO CON SUCCESSO!")
        print("=" * 55)
        print(f"📁 Eseguibile: {exe_path}")
        print(f"📁 Logs: {os.path.join(self.output_dir, 'logs')}")
        print()
        print("✅ L'applicazione è pronta per la distribuzione!")
        return True


def main() -> int:
    builder = RebrandingToolBuilder()
    try:
        return 0 if builder.build() else 1
    except KeyboardInterrupt:
        print("\n⚠️  Operazione interrotta dall'utente")
        return 1
    except Exception as exc:
        print(f"\n❌ Errore imprevisto: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
