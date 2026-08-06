# Rebranding Tool

Strumento per la **sostituzione massiva di file grafici/logo** sviluppato in Python per SACE S.p.A.

## Funzionalità

Il tool guida l'utente attraverso 4 tab (wizard):

| Tab | Descrizione |
|-----|-------------|
| **① Configurazione** | Cartella sorgente (nuovi loghi), cartella da scansionare, pattern di ricerca (es. `logo*.png`) |
| **② Risultati Scansione** | Elenco dei file trovati con anteprima, nome, percorso, formato, peso e risoluzione |
| **③ Corrispondenze** | Abbinamento automatico con il sorgente più adatto, doppia anteprima *prima/dopo*, giudizio di qualità, esclusione o scelta manuale riga per riga |
| **④ Sostituzione** | Sovrascrittura dei file con backup automatico, simulazione (dry-run), log dettagliato e ripristino dei backup |

Altre caratteristiche:

- avanzamento visibile e **annullamento** delle operazioni lunghe (utile su share di rete);
- **sostituzione atomica**: un errore a metà copia non lascia mai il file originale troncato;
- **backup non distruttivi**: una seconda campagna di rebranding non sovrascrive il `.bak` della prima;
- **ripristino** dei file originali dai backup con un pulsante;
- **export CSV** delle corrispondenze e del report di sostituzione;
- le ultime cartelle e opzioni usate vengono ricordate tra un avvio e l'altro.

## Requisiti

- Python 3.10+ (con `tkinter`)
- `pillow` — obbligatorio per anteprime e lettura delle risoluzioni
- `ttkbootstrap` — opzionale, solo estetico: senza, l'app usa i temi `ttk` standard
- `pyinstaller` — solo per generare l'eseguibile

## Installazione e Avvio

### Prima esecuzione - installa dipendenze:
```bat
install_dependencies.bat
```

### Avvio diretto (sviluppo/test):
```bat
run.bat
```
Su Linux/macOS: `./run.sh`

### Compilazione eseguibile `.exe`:
```bat
compile.bat
```
L'eseguibile viene generato in `dist/RebrandingTool.exe`.

## Pattern di ricerca supportati

| Pattern | Significato |
|---------|-------------|
| `logo*.png` | Tutti i PNG che iniziano con "logo" |
| `banner_*.jpg` | Tutti i JPG che iniziano con "banner_" |
| `*.svg` | Tutti i file SVG |
| `icon_??.png` | PNG con "icon_" seguito da esattamente 2 caratteri |
| `logo*.png; logo*.svg` | Più pattern insieme, separati da `;` |

La ricerca è ricorsiva e ignora maiuscole/minuscole. I file `.bak` prodotti dal tool
sono sempre esclusi, così come la cartella sorgente quando si trova dentro quella
da scansionare.

## Algoritmo di Corrispondenza

1. **Stesso formato**: il sorgente deve avere la stessa estensione del target.
   `.jpg`/`.jpeg` e `.tif`/`.tiff` sono considerati equivalenti.
2. **Risoluzione più vicina**: fra i candidati vince quello con la risoluzione più
   simile. Lo scarto è *relativo* alla dimensione del target (distanza euclidea
   normalizzata sulla diagonale), così 20 px di differenza pesano molto su
   un'icona 32×32 e poco su un banner 1920×1080.
3. **Nome file più simile**: a parità di risoluzione fa da spareggio.

La colonna **Qualità** riassume il solo scarto di risoluzione:

| Giudizio | Significato |
|----------|-------------|
| Ottima | scarto ≤ 10% |
| Buona | scarto ≤ 35% |
| Debole | scarto maggiore, da verificare a mano |
| Manuale | sorgente scelto dall'utente |
| — | nessuna corrispondenza trovata |

Con doppio clic su una riga si può sostituire la proposta automatica con un
qualsiasi file della cartella sorgente.

## Backup e ripristino

Con l'opzione **Backup** attiva ogni file originale viene copiato prima della
sovrascrittura:

- prima campagna → `logo.png.bak`
- campagne successive → `logo.png.20260806-101500.bak`

Il pulsante **Ripristina backup** nel tab ④ riporta i file allo stato precedente
al rebranding, usando sempre il backup più vecchio disponibile (cioè l'originale).

## Simulazione (dry-run)

L'opzione **Simulazione** esegue tutti i controlli e produce il log completo
senza scrivere nulla su disco. È il modo consigliato per verificare una campagna
su una share di rete prima di eseguirla davvero.

## Note

- I file **EPS e PDF** non hanno anteprima né risoluzione (limitazione Pillow).
  Per gli **SVG** la risoluzione viene letta dal markup (`width`/`height` o `viewBox`).
- I log sono in `logs/` accanto all'applicazione; se quel percorso è in sola
  lettura (es. `C:\Program Files`) vengono scritti in
  `%LOCALAPPDATA%\RebrandingTool\logs`. Sono a rotazione (5 file da 2 MB).

## Sviluppo

```bash
pip install -r requirements-dev.txt
python -m pytest                 # Windows/macOS
xvfb-run -a python -m pytest     # Linux headless
```

La suite copre sia la logica applicativa sia l'interfaccia:

| File | Contenuto |
|------|-----------|
| `core.py` | Logica pura (scansione, abbinamento, sostituzione, backup, CSV, impostazioni), senza dipendenze da tkinter |
| `rebranding_tool.py` | Interfaccia grafica |
| `main.py` | Avvio applicazione |
| `build.py` | Compilazione con PyInstaller |
| `tests/test_core.py` | Test della logica |
| `tests/test_gui.py` | Test dell'interfaccia (headless) |

---
*SACE S.p.A - Tool interno*
