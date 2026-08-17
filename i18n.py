#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Proteus - translation layer.

English is the source language: the keys of the catalogue *are* the English
strings, so untranslated text degrades gracefully to readable English instead
of showing a symbolic identifier.

Usage::

    from i18n import t
    label = t("Source folder")
    text = t("{count} files found").format(count=12)

Adding a language means adding one entry to ``CATALOGUES``; any string missing
from a catalogue falls back to English automatically.
"""

from __future__ import annotations

import threading

#: Language used both as the default and as the source of the message keys.
DEFAULT_LANGUAGE = "en"

#: Selectable languages, mapped to the label shown in the interface.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "it": "Italiano",
}

# ---------------------------------------------------------------------------
# Italian catalogue
# ---------------------------------------------------------------------------

_IT: dict[str, str] = {
    # -- Generic ----------------------------------------------------------
    "Ready": "Pronto",
    "Cancel": "Annulla",
    "Confirm": "Conferma",
    "Browse...": "Sfoglia...",
    "Path:": "Percorso:",
    "Language:": "Lingua:",
    "Warning": "Attenzione",
    "Error": "Errore",
    "Completed": "Completato",
    "YES": "SÌ",
    "NO": "NO",
    "N/A": "N/D",
    "NO MATCH": "NESSUNA CORRISPONDENZA",
    "VERSION {version}": "VERSIONE {version}",

    # -- Tabs -------------------------------------------------------------
    "  ① CONFIGURATION  ": "  ① CONFIGURAZIONE  ",
    "  ② SCAN RESULTS  ": "  ② RISULTATI SCANSIONE  ",
    "  ③ MATCHES  ": "  ③ CORRISPONDENZE  ",
    "  ④ REPLACEMENT  ": "  ④ SOSTITUZIONE  ",

    # -- Tab 1: configuration ---------------------------------------------
    "Search Configuration": "Configurazione Ricerca",
    "Set the folders and the search key, then start the scan.":
        "Imposta le cartelle e la chiave di ricerca, poi avvia la scansione.",
    " SOURCE FOLDER (new logos) ": " CARTELLA SORGENTE (nuovi loghi) ",
    "Folder holding the new logo files (the replacement source):":
        "Cartella contenente i nuovi file logo (sorgente della sostituzione):",
    " FOLDER TO SCAN ": " CARTELLA DA SCANSIONARE ",
    "Folder (and subfolders) to search for the files to replace "
    "(e.g. a server or network share):":
        "Cartella (e sottocartelle) dove cercare i file da sostituire "
        "(es. server, share di rete):",
    " SEARCH KEY ": " CHIAVE DI RICERCA ",
    "Search by:": "Cerca per:",
    "File name": "Nome file",
    "Image content": "Contenuto immagine",
    "Find images that look like the reference ones, whatever they are called.\n"
    "Raster formats only: SVG, PDF and EPS cannot be matched by content.":
        "Trova immagini simili a quelle di riferimento, comunque si chiamino.\n"
        "Solo formati raster: SVG, PDF ed EPS non sono confrontabili per contenuto.",
    "Reference images:": "Immagini di riferimento:",
    "Choose images...": "Scegli immagini...",
    "No reference image chosen": "Nessuna immagine di riferimento",
    "{count} chosen: {names}": "{count} scelte: {names}",
    "Select the old logo, in one or more versions":
        "Seleziona il vecchio logo, in una o piu' versioni",
    "Minimum similarity:": "Somiglianza minima:",
    "Also look inside Office documents (.docx, .pptx, .xlsx)":
        "Cerca anche dentro i documenti Office (.docx, .pptx, .xlsx)",
    "Scanning documents... {done}/{total}":
        "Scansione documenti... {done}/{total}",
    "Pictures found inside documents: {count}":
        "Immagini trovate dentro i documenti: {count}",
    "\n\u26a0  {count} replacements would stretch the picture: inside "
    "a document the frame keeps its own proportions.":
        "\n\u26a0  {count} sostituzioni deformerebbero l'immagine: dentro "
        "un documento la cornice mantiene le proprie proporzioni.",
    "Similarity": "Somiglianza",
    "Searching by content... {done}/{total}":
        "Ricerca per contenuto... {done}/{total}",
    "Content search started — folder: {folder} | references: {count} | "
    "threshold: {threshold}%":
        "Ricerca per contenuto avviata — cartella: {folder} | riferimenti: {count} | "
        "soglia: {threshold}%",
    "{count} files found by content — {sources} sources available":
        "{count} file trovati per contenuto — {sources} sorgenti disponibili",
    "\u26a0  {count} of them are below {threshold}% similarity: look at those "
    "before replacing.":
        "\u26a0  {count} sono sotto il {threshold}% di somiglianza: guardali prima "
        "di sostituire.",
    "orange = found by content, below the confident threshold":
        "arancio = trovato per contenuto, sotto la soglia di confidenza",
    "Wildcard pattern (* = many characters, ? = one character). "
    "Separate multiple patterns with «;».\n"
    "Examples: logo*.png  |  banner_*.jpg  |  icon_??.svg  |  logo*.png; logo*.svg":
        "Pattern con wildcard (* = più caratteri, ? = un carattere). "
        "Più pattern separati da «;».\n"
        "Esempi: logo*.png  |  banner_*.jpg  |  icon_??.svg  |  logo*.png; logo*.svg",
    "Pattern:": "Pattern:",
    "⚠️  Pillow (PIL) is not installed: previews and resolutions will be "
    "unavailable. Install it with: pip install pillow":
        "⚠️  Pillow (PIL) non è installato: anteprime e risoluzioni non saranno "
        "disponibili. Installa con: pip install pillow",
    "🔍  START SCAN": "🔍  AVVIA SCANSIONE",
    "Clear fields": "Pulisci campi",
    "Open log folder": "Apri cartella log",

    # -- Tab 2: scan results ----------------------------------------------
    "Scan Results": "Risultati Scansione",
    "No scan performed yet": "Nessuna scansione effettuata",
    "Review the files found, then start the match analysis. "
    "Double-click a row to open its containing folder.":
        "Controlla i file individuati, poi avvia l'analisi delle corrispondenze. "
        "Doppio clic su una riga per aprire la cartella che la contiene.",
    "File Name": "Nome File",
    "Format": "Formato",
    "Size": "Dimensione",
    "Resolution": "Risoluzione",
    "Full Path": "Percorso Completo",
    " Preview ": " Anteprima ",
    "Select a file to preview it": "Seleziona un file per l'anteprima",
    "🔗  FIND MATCHES": "🔗  TROVA CORRISPONDENZE",
    "← Back to Configuration": "← Torna alla Configurazione",
    "{count} files found — {sources} sources available":
        "{count} file trovati — {sources} sorgenti disponibili",
    "Scan complete: {count} files found.": "Scansione completata: {count} file trovati.",
    "No results": "Nessun risultato",
    "No file matches the given pattern.\n\n"
    "Check the pattern (e.g. logo*.png) and the folder to scan.":
        "Nessun file corrisponde al pattern indicato.\n\n"
        "Verifica il pattern (es. logo*.png) e la cartella da scansionare.",
    "Name: {name}\nFormat: {fmt}\nSize: {size}\nResolution: {dim}\nPath: {path}":
        "Nome: {name}\nFormato: {fmt}\nDimensione: {size}\n"
        "Risoluzione: {dim}\nPercorso: {path}",

    # -- Tab 3: matches ---------------------------------------------------
    "Proposed Matches": "Corrispondenze Proposte",
    "Each file found is paired with the most suitable source (same format, "
    "closest resolution, most similar name).\n"
    "Click the ✓ column or press space to include/exclude a row; "
    "double-click to pick a different source.":
        "Ogni file trovato viene abbinato al sorgente più idoneo (stesso formato, "
        "risoluzione più simile, nome più affine).\n"
        "Clic sulla colonna ✓ o barra spaziatrice per includere/escludere una riga; "
        "doppio clic per scegliere un sorgente diverso.",
    "File to Replace": "File da Sostituire",
    "Target Resolution": "Risoluzione Target",
    "New Source File": "Nuovo File Sorgente",
    "Source Resolution": "Risoluzione Sorgente",
    "Quality": "Qualità",
    "Target Path": "Percorso Target",
    " Original Logo ": " Logo Originale ",
    " Proposed New Logo ": " Nuovo Logo Proposto ",
    "Select a row": "Seleziona una riga",
    "✓ = included   ✗ = excluded   red = no match   "
    "orange = weak match, worth checking":
        "✓ = incluso   ✗ = escluso   rosso = nessuna corrispondenza   "
        "arancio = abbinamento debole, da verificare",
    "Select all": "Seleziona tutto",
    "Deselect all": "Deseleziona tutto",
    "Export CSV": "Esporta CSV",
    "✅  PROCEED WITH REPLACEMENT": "✅  PROCEDI CON LA SOSTITUZIONE",
    "← Back to Results": "← Torna ai Risultati",
    "Name: {name}\nFormat: {fmt}\nRes: {dim}\nWeight: {size}":
        "Nome: {name}\nFormato: {fmt}\nDim: {dim}\nPeso: {size}",
    "Name: {name}\nFormat: {fmt}\nRes: {dim}\nQuality: {quality}":
        "Nome: {name}\nFormato: {fmt}\nDim: {dim}\nQualità: {quality}",
    "No\nMatch": "Nessun\nMatch",
    "Match not found.\nDouble-click to choose one manually.":
        "Corrispondenza non trovata.\nDoppio clic per sceglierla a mano.",
    "{total} files analysed: {matched} matches":
        "{total} file analizzati: {matched} corrispondenze",
    ", {count} without a match": ", {count} senza corrispondenza",
    ", {count} to review": ", {count} da verificare",
    "No data": "Nessun dato",
    "Run the match analysis first.": "Esegui prima l'analisi delle corrispondenze.",
    "Export matches": "Esporta corrispondenze",
    "Export complete": "Esportazione completata",
    "File saved:\n{path}": "File salvato:\n{path}",
    "Export error": "Errore esportazione",

    # -- Manual source dialog ---------------------------------------------
    "Choose a source for {name}": "Scegli sorgente per {name}",
    "File to replace: {name} ({fmt}, {dim})":
        "File da sostituire: {name} ({fmt}, {dim})",
    "Sources with a matching format are listed first.":
        "I sorgenti dello stesso formato sono elencati per primi.",
    "  [different format]": "  [formato diverso]",
    "Select a source file.": "Seleziona un file sorgente.",
    "No sources": "Nessun sorgente",
    "The source folder contains no files.": "La cartella sorgente non contiene file.",

    # -- Tab 4: replacement -----------------------------------------------
    "File Replacement": "Sostituzione File",
    "The files selected in the previous tab will be overwritten with their "
    "matching source files.\n"
    "With backup enabled the operation can be undone from «Restore backups».":
        "I file selezionati nel tab precedente verranno sovrascritti con i "
        "corrispondenti file sorgente.\n"
        "Con il backup attivo l'operazione è reversibile dal pulsante "
        "«Ripristina backup».",
    " Operation summary ": " Riepilogo operazione ",
    "No operation pending.": "Nessuna operazione in attesa.",
    "Back up the original files before overwriting (.bak suffix)":
        "Crea backup dei file originali prima di sovrascrivere (suffisso .bak)",
    "Dry run: performs every check without modifying any file":
        "Simulazione (dry-run): esegue tutti i controlli senza modificare alcun file",
    " Operation log ": " Log operazioni ",
    "⚡  RUN REPLACEMENT": "⚡  ESEGUI SOSTITUZIONE",
    "← Back to Matches": "← Torna alle Corrispondenze",
    "Clear log": "Pulisci log",
    "↩  Restore backups": "↩  Ripristina backup",
    "No replacement selected.": "Nessuna sostituzione selezionata.",
    "No replacement selected.\nGo back to tab ③ and select at least one match.":
        "Nessuna sostituzione selezionata.\n"
        "Torna al tab ③ e seleziona almeno una corrispondenza.",
    "DRY RUN ENABLED: no file will be modified.":
        "SIMULAZIONE ATTIVA: nessun file verrà modificato.",
    "The original files will be saved with a .bak extension (restorable).":
        "I file originali verranno salvati con estensione .bak (ripristinabili).",
    "BACKUP DISABLED: the original files will be overwritten permanently.":
        "BACKUP DISATTIVO: i file originali saranno sovrascritti definitivamente.",
    "{count} of {total} analysed files will be replaced.\n{mode}":
        "Verranno sostituiti {count} file su {total} analizzati.\n{mode}",
    "\n⚠  {count} matches are rated «Weak»: review them in tab ③.":
        "\n⚠  {count} abbinamenti sono classificati «Debole»: verificali nel tab ③.",
    "No replacement to run.": "Nessuna sostituzione da eseguire.",
    "Confirm Replacement": "Conferma Sostituzione",
    "Dry run over {count} files.\n\nNo file will be modified.\n\nContinue?":
        "Simulazione su {count} file.\n\nNessun file verrà modificato.\n\nContinuare?",
    "You are about to overwrite {count} files.\n\nBackup: {backup}\n\nContinue?":
        "Stai per sovrascrivere {count} file.\n\nBackup: {backup}\n\nContinuare?",
    "NO — this cannot be undone": "NO — operazione irreversibile",
    "Files processed: {total}\nCompleted: {ok}\nSkipped: {skipped}\nErrors: {errors}":
        "File elaborati: {total}\nCompletati: {ok}\nSaltati: {skipped}\n"
        "Errori: {errors}",
    "\n\nOperation interrupted by the user.":
        "\n\nOperazione interrotta dall'utente.",
    "Completed with errors": "Completato con errori",
    "{detail}\n\nSee the log for details.": "{detail}\n\nConsulta il log per i dettagli.",
    "Dry run complete": "Simulazione completata",
    "{detail}\n\nNo file was modified.": "{detail}\n\nNessun file è stato modificato.",
    "✅ Replacement completed successfully!\n\n{detail}":
        "✅ Sostituzione completata con successo!\n\n{detail}",
    "Report": "Report",
    "Do you want to save a CSV report of the operation?":
        "Vuoi salvare un report CSV dell'operazione?",
    "Save report": "Salva report",
    "Report save error": "Errore salvataggio report",

    # -- Restore ----------------------------------------------------------
    "Select a valid folder to scan in tab ① before restoring.":
        "Seleziona una cartella da scansionare valida nel tab ① prima di ripristinare.",
    "No backup": "Nessun backup",
    "No .bak file found in:\n{path}": "Nessun file .bak trovato in:\n{path}",
    "Confirm restore": "Conferma ripristino",
    "Found {count} backups covering {files} files in:\n{path}\n\n"
    "The current files will be reverted to their pre-rebranding version.\n\n"
    "Continue?":
        "Trovati {count} backup relativi a {files} file in:\n{path}\n\n"
        "I file correnti verranno riportati alla versione precedente al rebranding.\n\n"
        "Continuare?",
    "Backup": "Backup",
    "Do you want to delete the .bak files after restoring?\n\n"
    "Choose «No» to keep them.":
        "Vuoi eliminare i file .bak dopo il ripristino?\n\n"
        "Scegli «No» per conservarli.",
    "Restore complete": "Ripristino completato",
    "Files restored: {ok}\nErrors: {errors}":
        "File ripristinati: {ok}\nErrori: {errors}",

    # -- Status / progress ------------------------------------------------
    "Scanning...": "Scansione in corso...",
    "Analysing matches...": "Analisi corrispondenze in corso...",
    "Replacing...": "Sostituzione in corso...",
    "Restoring...": "Ripristino in corso...",
    "Reading sources... {done}/{total}": "Lettura sorgenti... {done}/{total}",
    "Analysing files... {done}/{total}": "Analisi file... {done}/{total}",
    "Matching... {done}/{total}": "Abbinamento... {done}/{total}",
    "Replacement... {done}/{total}": "Sostituzione... {done}/{total}",
    "Dry run... {done}/{total}": "Simulazione... {done}/{total}",
    "Restore... {done}/{total}": "Ripristino... {done}/{total}",
    "Cancelling...": "Annullamento in corso...",
    "Operation cancelled.": "Operazione annullata.",
    "Operation failed with an error.": "Operazione terminata con errore.",
    "Operation in progress": "Operazione in corso",
    "Wait for the current operation to finish.":
        "Attendi il completamento dell'operazione corrente.",
    "An operation is still running.\nQuit anyway?":
        "Un'operazione è ancora in esecuzione.\nUscire comunque?",
    "Select source folder (new logos)": "Seleziona cartella sorgente (nuovi loghi)",
    "Select folder to scan": "Seleziona cartella da scansionare",
    "Invalid configuration": "Configurazione non valida",
    "Path": "Percorso",
    "{path}\n\n(Could not open it automatically: {error})":
        "{path}\n\n(Apertura automatica non riuscita: {error})",
    "Could not open the mail client: {error}":
        "Impossibile aprire il client di posta: {error}",
    "No file found in the scan.\nRun the scan first.":
        "Nessun file trovato nella scansione.\nEsegui prima la scansione.",
    "No image file in the source folder.":
        "Nessun file immagine nella cartella sorgente.",

    # -- Log messages -----------------------------------------------------
    "{app} {version} started.": "{app} {version} avviato.",
    "Pillow is unavailable: image previews and resolutions will not be shown.":
        "Pillow non disponibile: anteprime e risoluzioni immagine non saranno mostrate.",
    "Scan started — folder: {folder} | pattern: {pattern}":
        "Scansione avviata — cartella: {folder} | pattern: {pattern}",
    "Source logo folder: {folder}": "Cartella sorgente loghi: {folder}",
    "Source files found: {count}": "File sorgente trovati: {count}",
    "Files matching the pattern: {count}": "File corrispondenti al pattern: {count}",
    "Scan complete: {count} files, {sources} sources available.":
        "Scansione completata: {count} file, {sources} sorgenti disponibili.",
    "Starting match: {count} files to analyse, {sources} sources available.":
        "Avvio abbinamento: {count} file da analizzare, {sources} sorgenti disponibili.",
    "Match complete: {matched}/{total} matches ({weak} weak).":
        "Abbinamento completato: {matched}/{total} corrispondenze ({weak} deboli).",
    "  Access denied or error on {path}: {error}":
        "  Accesso negato o errore su {path}: {error}",
    "  Unreadable source {path}: {error}": "  Sorgente illeggibile {path}: {error}",
    "  Error on {path}: {error}": "  Errore su {path}: {error}",
    "Warning: {message}": "Avviso: {message}",
    "Operation cancelled by the user.": "Operazione annullata dall'utente.",
    "Error: {error}": "Errore: {error}",
    "Source manually set for {target}: {source}":
        "Sorgente impostato manualmente per {target}: {source}",
    "Matches exported to {path}": "Corrispondenze esportate in {path}",
    "Report saved to {path}": "Report salvato in {path}",
    "=== {action} START: {count} files (backup: {backup}) ===":
        "=== INIZIO {action}: {count} file (backup: {backup}) ===",
    "=== {action} COMPLETE: {ok} ok, {skipped} skipped, {errors} errors "
    "out of {total} files ===":
        "=== {action} COMPLETATA: {ok} ok, {skipped} saltati, {errors} errori "
        "su {total} file ===",
    "REPLACEMENT": "SOSTITUZIONE",
    "DRY RUN": "SIMULAZIONE",
    "Replacement": "Sostituzione",
    "Dry run": "Simulazione",
    "yes": "sì",
    "no": "no",
    "  ○ [simulated] {target}  ←  {source}": "  ○ [simulato] {target}  ←  {source}",
    "  backup: {path}": "  backup: {path}",
    "  ✅ Replaced: {target}  ←  {source}": "  ✅ Sostituito: {target}  ←  {source}",
    "  ⏭ Skipped {target}: {message}": "  ⏭ Saltato {target}: {message}",
    "  ❌ Error on {target}: {message}": "  ❌ Errore su {target}: {message}",
    "=== RESTORE START from {path} ===": "=== INIZIO RIPRISTINO da {path} ===",
    "  ↩ Restored: {target}": "  ↩ Ripristinato: {target}",
    "  ❌ Restore error on {target}: {message}":
        "  ❌ Errore ripristino {target}: {message}",
    "=== RESTORE COMPLETE: {ok} ok, {errors} errors ===":
        "=== RIPRISTINO COMPLETATO: {ok} ok, {errors} errori ===",
    "{action} complete: {ok} ok, {skipped} skipped, {errors} errors.":
        "{action} completata: {ok} ok, {skipped} saltati, {errors} errori.",
    "Restore complete: {ok} ok, {errors} errors.":
        "Ripristino completato: {ok} ok, {errors} errori.",
    "Language changed to {language}.": "Lingua impostata su {language}.",

    # -- core.py: validation ----------------------------------------------
    "Enter at least one search pattern.": "Inserisci almeno un pattern di ricerca.",
    "Choose at least one reference image to search by content.":
        "Scegli almeno un'immagine di riferimento per cercare per contenuto.",
    "None of the reference images can be read. Vector formats (SVG) and "
    "documents (PDF, EPS) cannot be matched by content.":
        "Nessuna immagine di riferimento e' leggibile. I formati vettoriali (SVG) "
        "e i documenti (PDF, EPS) non sono confrontabili per contenuto.",
    "Pattern «{pattern}» contains a path separator: give the file name only "
    "(e.g. logo*.png).":
        "Il pattern «{pattern}» contiene un separatore di percorso: indica solo "
        "il nome del file (es. logo*.png).",
    "Pattern «{pattern}» is too broad and would select any file. "
    "Specify at least an extension.":
        "Il pattern «{pattern}» è troppo generico e selezionerebbe qualsiasi file. "
        "Specifica almeno un'estensione.",
    "Select a valid source folder.": "Seleziona una cartella sorgente valida.",
    "Select a valid folder to scan.": "Seleziona una cartella da scansionare valida.",
    "The source folder and the folder to scan are the same: the new logos "
    "would be replaced with themselves.":
        "La cartella sorgente e quella da scansionare coincidono: i nuovi loghi "
        "verrebbero sostituiti con se stessi.",
    "The source folder sits inside the folder to scan: it will be excluded "
    "from the search automatically.":
        "La cartella sorgente si trova dentro quella da scansionare: verrà "
        "esclusa automaticamente dalla ricerca.",

    # -- core.py: replacement outcomes ------------------------------------
    "Source file not found, or not a file.":
        "File sorgente non trovato o non è un file.",
    "File to replace not found, or not a file.":
        "File da sostituire non trovato o non è un file.",
    "Source and destination are the same file.":
        "Sorgente e destinazione sono lo stesso file.",
    "Dry run: nothing written to disk.":
        "Simulazione: nessuna modifica scritta su disco.",
    "No match.": "Nessuna corrispondenza.",
    "Restored from backup.": "Ripristinato dal backup.",

    # -- core.py: match quality -------------------------------------------
    "Excellent": "Ottima",
    "Good": "Buona",
    "Weak": "Debole",
    "Manual": "Manuale",

    # -- core.py: CSV headers ---------------------------------------------
    "Included": "Incluso",
    "Target resolution": "Risoluzione target",
    "Target weight": "Peso target",
    "Source resolution": "Risoluzione sorgente",
    "Score": "Punteggio",
    "Target path": "Percorso target",
    "Source path": "Percorso sorgente",
    "Outcome": "Esito",
    "File": "File",
    "Source": "Sorgente",
    "Message": "Messaggio",

    # -- PDF: findings the user has to act on by hand ----------------------
    "PDF support needs the «pypdf» package, which is not installed.":
        "Il supporto PDF richiede il pacchetto «pypdf», che non è installato.",
    "Install it with: pip install pypdf":
        "Installalo con: pip install pypdf",
    "This PDF could not be read: {error}":
        "Impossibile leggere questo PDF: {error}",
    "Open it in a PDF reader to check it is not damaged.":
        "Aprilo con un lettore PDF per verificare che non sia danneggiato.",
    "This PDF is encrypted, so its images cannot be read.":
        "Questo PDF è cifrato, quindi le sue immagini non sono leggibili.",
    "Remove the password, then run the scan again.":
        "Rimuovi la password, poi ripeti la scansione.",
    "This PDF is digitally signed: replacing an image would invalidate the signature.":
        "Questo PDF ha una firma digitale: sostituire un'immagine la "
        "invaliderebbe.",
    "Replace the logo in the source document and sign it again.":
        "Sostituisci il logo nel documento di partenza e firmalo di nuovo.",
    "Page {page} of this PDF could not be read: {error}":
        "Impossibile leggere la pagina {page} di questo PDF: {error}",
    "The other pages were still processed.":
        "Le altre pagine sono state elaborate comunque.",
    "Page {page} contains an inline image that cannot be replaced automatically.":
        "La pagina {page} contiene un'immagine inline che non può essere "
        "sostituita automaticamente.",
    "Edit this page by hand in a PDF editor.":
        "Modifica questa pagina a mano con un editor PDF.",
    "Image on page {page} uses the unsupported encoding {encoding}.":
        "L'immagine a pagina {page} usa la codifica non supportata {encoding}.",
    "Replace this picture by hand in a PDF editor.":
        "Sostituisci questa immagine a mano con un editor PDF.",
    "Image on page {page} could not be decoded: {error}":
        "Impossibile decodificare l'immagine a pagina {page}: {error}",
    "No replaceable image found in this PDF: a logo drawn as vector artwork cannot be swapped.":
        "Nessuna immagine sostituibile in questo PDF: un logo disegnato come "
        "grafica vettoriale non può essere scambiato.",
    "Replace it by hand, or export the page and edit the original.":
        "Sostituiscilo a mano, oppure esporta la pagina e modifica l'originale.",
    "Image {entry} is no longer in the document.":
        "L'immagine {entry} non è più nel documento.",
    "Image {entry} has changed since the scan; nothing was written.":
        "L'immagine {entry} è cambiata dopo la scansione: non è stato scritto "
        "nulla.",
    "Image {name} could not be extracted for comparison.":
        "Impossibile estrarre l'immagine {name} per il confronto.",

    # -- PDF: interface --------------------------------------------------
    "Also look inside PDF files (raster images only)":
        "Cerca anche dentro i file PDF (solo immagini raster)",
    "Scanning PDFs... {done}/{total}":
        "Scansione PDF... {done}/{total}",
    "Pictures found inside PDFs: {count}":
        "Immagini trovate dentro i PDF: {count}",
    "  Needs attention: {path} — {reason}":
        "  Richiede attenzione: {path} — {reason}",
    "⚠  {count} file(s) may carry the logo but could not be handled automatically — they need manual attention.":
        "⚠  {count} file potrebbero contenere il logo ma non sono gestibili "
        "automaticamente: richiedono un intervento manuale.",
    "Show details": "Mostra dettagli",
    "Needs manual attention": "Richiede intervento manuale",
}

#: Every available catalogue. English needs none: it is the source language.
CATALOGUES: dict[str, dict[str, str]] = {"it": _IT}


# ---------------------------------------------------------------------------
# Current language
# ---------------------------------------------------------------------------

_lock = threading.RLock()
_current_language = DEFAULT_LANGUAGE


def get_language() -> str:
    """Return the language code currently in use."""
    with _lock:
        return _current_language


def set_language(code: str) -> str:
    """
    Switch the active language.

    Unknown codes fall back to the default rather than raising: a corrupted
    settings file must never stop the application from starting.
    """
    global _current_language
    with _lock:
        _current_language = code if code in LANGUAGES else DEFAULT_LANGUAGE
        return _current_language


def language_name(code: str) -> str:
    """Human-readable name of a language code."""
    return LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])


def code_for_name(name: str) -> str:
    """Language code matching a display name; default if unknown."""
    for code, label in LANGUAGES.items():
        if label == name:
            return code
    return DEFAULT_LANGUAGE


def t(message: str) -> str:
    """
    Translate `message` into the active language.

    Returns the English source unchanged when the language is English or when
    the catalogue has no entry for it, so a missing translation shows readable
    text rather than a placeholder.
    """
    with _lock:
        catalogue = CATALOGUES.get(_current_language)
    if not catalogue:
        return message
    return catalogue.get(message, message)


def missing_translations(code: str) -> list[str]:
    """
    Source strings that `code` does not translate.

    Used by the test suite to keep the catalogues honest as the interface
    changes.
    """
    catalogue = CATALOGUES.get(code, {})
    return [key for key in _IT if key not in catalogue]
