**Proteus — Rebranding Tool.** Carries a corporate rebranding through an organisation's
files: it finds the files still carrying the old logo, pairs each one with the most
suitable replacement, shows a before/after preview of every pairing, and overwrites them
atomically with recoverable backups.

- **Finds** by name, by visual similarity, and inside Office documents and PDFs — pictures
  no wildcard would ever reach.
- **Never writes silently** — a dry run by default, an explicit `--apply`, and a refusal
  (exit code 4) rather than a guess when a match falls below the similarity threshold.
- **Interface and command line in one binary** — double-click for the GUI, or
  `--help` from a terminal for scheduled and unattended runs.
- **Bilingual** — English and Italian, switchable at runtime.

## Download

| Platform | File |
|---|---|
| Windows (x64) | `Proteus-{{VERSION}}-windows-x64.zip` |
| macOS (Apple silicon) | `Proteus-{{VERSION}}-macos-arm64.zip` |
| Linux (x64) | `Proteus-{{VERSION}}-linux-x64.tar.gz` |

Each archive is built on that platform's own runner — no cross-compilation, no emulation.
Unpack and run: no installation, and no Python needed.

Each unpacks to a single `Proteus/` folder. Start it with the script beside the program —
`start.cmd` on Windows, `start.command` on macOS, `start.sh` on Linux. It checks the
program against the digest recorded when the archive was built and stops rather than
launching if they disagree, which is how a truncated download gets caught at the point of
launch instead of somewhere further in. On Windows the console stays up until the window
appears, because the first launch is slow. The program still starts on its own if you
prefer.

### Windows will say the publisher is unknown

It is meant to. These builds carry **no code-signing certificate**, so Microsoft Defender
SmartScreen shows *"Windows protected your PC"* and offers only **Don't run**. Click
**More info**, then **Run anyway**. Nothing is wrong with the download; SmartScreen is
reporting that it has never seen this publisher, which is true.

Because that warning asks you to trust a file you cannot check by looking at it, the
SHA-256 of all three archives is listed under **Checksums** at the bottom of these notes.
In PowerShell:

```powershell
Get-FileHash .\Proteus-{{VERSION}}-windows-x64.zip -Algorithm SHA256
```

If what it prints matches the line below, the file is byte for byte what the build
produced. Those digests are here rather than in the archives on purpose: one that travels
with the file it describes can only tell you the file is undamaged.

On **macOS**, Gatekeeper refuses an unidentified developer the same way: right-click the
application and choose **Open**, or run `xattr -dr com.apple.quarantine Proteus`.

Each archive unpacks to a folder holding the executable and a `licenses/` directory: the
terms of everything Proteus is built on, plus an inventory of every native library in the
build and where each licence determination came from. That inventory is generated on the
machine that produced the archive, so it describes what you actually downloaded.

Running from source instead is described in the
[README](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/README.md).

## Changes

See [CHANGELOG.md](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/CHANGELOG.md).

## Licence

Licensed **AGPL-3.0-or-later** — see
[LICENSE](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/LICENSE). A commercial
licence, without the AGPL's obligations, is available for closed-source and redistribution
use: see
[COMMERCIAL-LICENSE.md](https://github.com/MarcoLombardoDev/Proteus/blob/{{TAG}}/COMMERCIAL-LICENSE.md).
