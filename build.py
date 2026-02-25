#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script per la compilazione di Rebranding Tool con PyInstaller.
Segue lo stesso pattern di EmailSender/build.py.
"""

import os
import sys
import subprocess
import shutil
import time
from pathlib import Path


class RebrandingToolBuilder:
    def __init__(self):
        self.app_name = "RebrandingTool"
        self.main_script = "main.py"
        self.output_dir = "dist"

    def check_prerequisites(self) -> bool:
        print("🔍 Verifica prerequisiti...")

        # Python
        try:
            result = subprocess.run(["py", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                print("❌ Python non trovato!")
                return False
            print(f"✅ Python trovato: {result.stdout.strip()}")
        except FileNotFoundError:
            print("❌ Comando 'py' non trovato!")
            return False

        # PyInstaller
        try:
            result = subprocess.run(
                ["py", "-m", "PyInstaller", "--version"], capture_output=True, text=True
            )
            if result.returncode != 0:
                print("⚠️  PyInstaller non trovato, installazione in corso...")
                inst = subprocess.run(
                    ["py", "-m", "pip", "install", "pyinstaller"], capture_output=True, text=True
                )
                if inst.returncode != 0:
                    print(f"❌ Errore installazione PyInstaller: {inst.stderr}")
                    return False
                print("✅ PyInstaller installato")
            else:
                print(f"✅ PyInstaller trovato: {result.stdout.strip()}")
        except FileNotFoundError:
            print("❌ Impossibile verificare PyInstaller")
            return False

        # Pillow
        try:
            result = subprocess.run(
                ["py", "-c", "from PIL import Image; print('ok')"], capture_output=True, text=True
            )
            if result.returncode != 0:
                print("⚠️  Pillow non trovato, installazione in corso...")
                subprocess.run(["py", "-m", "pip", "install", "pillow"], capture_output=True)
                print("✅ Pillow installato")
            else:
                print("✅ Pillow disponibile")
        except Exception:
            pass

        # File principali
        required = [self.main_script, "rebranding_tool.py"]
        for f in required:
            if not os.path.exists(f):
                print(f"❌ File non trovato: {f}")
                return False
            print(f"✅ File trovato: {f}")

        return True

    def clean_temp_directories(self):
        print("🧹 Pulizia cartelle temporanee...")
        for temp_dir in ["build", "dist", "__pycache__"]:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"  ✅ {temp_dir} rimosso")
                except Exception as e:
                    print(f"  ⚠️  Impossibile rimuovere {temp_dir}: {e}")
        time.sleep(1)

    def build_executable(self) -> str | None:
        print("🔨 Compilazione eseguibile...")

        hidden_imports = [
            "tkinter", "tkinter.ttk", "tkinter.filedialog",
            "tkinter.messagebox", "tkinter.scrolledtext",
            "PIL", "PIL.Image", "PIL.ImageTk",
            "pathlib", "fnmatch", "shutil", "threading",
            "logging", "datetime", "queue", "os", "sys",
            "ttkbootstrap", "ttkbootstrap.themes", "ttkbootstrap.style", "ttkbootstrap.widgets",
        ]

        add_data = []
        if os.path.exists("sace.ico"):
            add_data.append("sace.ico;.")
        if os.path.exists("banner.jpg"):
            add_data.append("banner.jpg;.")

        # Includi risorse ttkbootstrap
        try:
            import ttkbootstrap
            tb_dir = Path(ttkbootstrap.__file__).parent
            add_data.append(f"{tb_dir};ttkbootstrap")
            print(f"✅ Risorse ttkbootstrap incluse: {tb_dir}")
        except Exception as e:
            print(f"⚠️  ttkbootstrap non includibile: {e}")

        excludes = [
            "matplotlib", "numpy", "pandas", "scipy",
            "PyQt5", "PyQt6", "PySide2", "PySide6",
            "jupyter", "IPython", "sphinx", "pytest",
            "win32com", "pythoncom",
        ]

        cmd = [
            "py", "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            f"--name={self.app_name}",
            "--noconfirm",
        ]

        if os.path.exists("sace.ico"):
            cmd.append("--icon=sace.ico")

        for imp in hidden_imports:
            cmd.extend(["--hidden-import", imp])

        cmd.extend(["--collect-all", "ttkbootstrap"])
        cmd.extend(["--collect-submodules", "ttkbootstrap"])
        cmd.extend(["--collect-data", "ttkbootstrap"])

        for data in add_data:
            cmd.extend(["--add-data", data])

        for exc in excludes:
            cmd.extend(["--exclude-module", exc])

        cmd.append(self.main_script)

        print("🚀 Avvio compilazione...")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode == 0:
                exe_path = os.path.join("dist", f"{self.app_name}.exe")
                if os.path.exists(exe_path):
                    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
                    print(f"✅ Compilazione completata!")
                    print(f"📁 Eseguibile: {exe_path}")
                    print(f"📏 Dimensione: {size_mb:.1f} MB")
                    return exe_path
                else:
                    print("❌ Eseguibile non trovato dopo compilazione")
                    return None
            else:
                print(f"❌ Errore compilazione (codice {result.returncode}):")
                if result.stdout:
                    print(f"   STDOUT: {result.stdout[-2000:]}")
                if result.stderr:
                    print(f"   STDERR: {result.stderr[-2000:]}")
                return None

        except subprocess.TimeoutExpired:
            print("❌ Timeout compilazione (>10 minuti)")
            return None
        except Exception as exc:
            print(f"❌ Errore imprevisto: {exc}")
            return None

    def create_distribution(self, exe_path: str):
        print("📦 Preparazione distribuzione...")
        logs_dir = os.path.join("dist", "logs")
        os.makedirs(logs_dir, exist_ok=True)
        print(f"  📁 Cartella logs creata")
        return True

    def build(self) -> bool:
        print("=" * 55)
        print("   REBRANDING TOOL - BUILD")
        print("=" * 55)
        print()

        if not self.check_prerequisites():
            print("\n❌ BUILD FALLITO: Prerequisiti non soddisfatti")
            return False

        print()
        self.clean_temp_directories()
        print()

        exe_path = self.build_executable()
        if not exe_path:
            print("\n❌ BUILD FALLITO: Errore durante la compilazione")
            return False

        print()
        self.create_distribution(exe_path)
        print()
        print("=" * 55)
        print("   BUILD COMPLETATO CON SUCCESSO!")
        print("=" * 55)
        print(f"📁 Eseguibile: {exe_path}")
        print(f"📁 Logs: dist/logs/")
        print()
        print("✅ L'applicazione è pronta per la distribuzione!")
        return True


def main():
    builder = RebrandingToolBuilder()
    try:
        success = builder.build()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Operazione interrotta dall'utente")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Errore imprevisto: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
