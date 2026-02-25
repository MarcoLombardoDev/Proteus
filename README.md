# Rebranding Tool

Strumento per la **sostituzione massiva di file grafici/logo** sviluppato in Python per SACE S.p.A.

## Funzionalità

Il tool guida l'utente attraverso 4 tab (wizard):

| Tab | Descrizione |
|-----|-------------|
| **① Configurazione** | Scelta cartella sorgente (nuovi loghi), cartella da scansionare, pattern di ricerca (es. `logo*.png`) |
| **② Risultati Scansione** | Elenco file trovati con anteprima, nome, percorso, formato, dimensione |
| **③ Corrispondenze** | Abbinamento automatico con il file sorgente più adatto (stesso formato, dimensione più vicina). L'utente può escludere singole corrispondenze |
| **④ Sostituzione** | Sovrascrittura dei file originali con i nuovi, con opzione backup automatico (`.bak`) |

## Requisiti

- Python 3.10+
- Dipendenze: `pillow`, `ttkbootstrap`, `pyinstaller`

## Installazione e Avvio

### Prima esecuzione - installa dipendenze:
```bat
install_dependencies.bat
```

### Avvio diretto (sviluppo/test):
```bat
run.bat
```

### Compilazione eseguibile `.exe`:
```bat
compile.bat
```
L'eseguibile verrà generato in `dist/RebrandingTool.exe`.

## Pattern di ricerca supportati

| Pattern | Significato |
|---------|-------------|
| `logo*.png` | Tutti i file PNG che iniziano con "logo" |
| `banner_*.jpg` | Tutti i JPG che iniziano con "banner_" |
| `*.svg` | Tutti i file SVG |
| `icon_??.png` | File PNG con "icon_" seguito da esattamente 2 caratteri |

## Algoritmo di Corrispondenza

1. **Stesso formato**: il file sorgente deve avere la stessa estensione del file target
2. **Dimensione più vicina**: tra i candidati con lo stesso formato, viene scelto quello con la risoluzione in pixel più simile al file originale (distanza euclidea `√((w1-w2)²+(h1-h2)²)`)

## Note

- I file **SVG, EPS, PDF** non hanno anteprima disponibile (limitazione PIL/Pillow)
- Con l'opzione **Backup** attiva, i file originali vengono salvati come `nomefile.ext.bak`
- I log vengono salvati nella cartella `logs/`

---
*SACE S.p.A - Tool interno*
