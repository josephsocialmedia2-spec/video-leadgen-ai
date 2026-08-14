# F1 Video Leadgen AI

Automazione gratuita basata su GitHub Actions per produrre fino a **3 video verticali al giorno** partendo dal piano contenutistico F1 su Google Sheets.

## Flusso

1. Joseph aggiorna il Google Sheet `F1 PIANO CONTENUTISTICO VIDEO AI`.
2. Compila `TESTO_60_SEC` e imposta `STATO = DA_PRODURRE`.
3. GitHub Actions legge il piano ogni mattina.
4. Piper genera la voce italiana in locale sul runner GitHub.
5. FFmpeg genera un Reel verticale 1080×1920, massimo 60 secondi, con operatore digitale F1 e CTA.
6. Il video viene inviato a `agenzia.realmediapro@gmail.com`.
7. Il runner elimina WAV e MP4 temporanei. Il repository non archivia i video.

## Piano Google Drive

Spreadsheet del progetto:

`1DiJ_p0CdgrLVcXz6rY67PD3iJe9n5RvHfz-60UaYTYg`

Per GitHub serve un URL CSV leggibile dal runner. Nel Google Sheet: **File → Condividi → Pubblica sul web**, selezionare il foglio `PIANO_VIDEO` e formato CSV. Copiare l'URL prodotto nel secret GitHub `PLAN_CSV_URL`.

> Pubblicare sul web rende quel foglio accessibile a chi possiede l'URL. Se si preferisce mantenerlo privato, la fase successiva sostituirà questo accesso con Google Sheets API + service account.

## Secret GitHub richiesti

Repository → **Settings → Secrets and variables → Actions → New repository secret**.

- `PLAN_CSV_URL`: URL CSV pubblicato del foglio `PIANO_VIDEO`.
- `GMAIL_APP_PASSWORD`: password per app Google dell'account `agenzia.realmediapro@gmail.com`.

Non inserire password nel codice o nel Google Sheet.

## Esecuzione

Il workflow parte automaticamente ogni giorno alle 05:30 UTC oppure manualmente da:

**Actions → F1 Video AI Daily → Run workflow**.

Genera al massimo tre righe della data odierna che abbiano contemporaneamente:

- `STATO = DA_PRODURRE`
- `TESTO_60_SEC` non vuoto

## Motore video

La versione 1 usa un **operatore digitale grafico animato**: è volutamente leggera per funzionare su runner CPU gratuiti. La struttura è modulare; il file `src/main.py` potrà successivamente passare a un motore lip-sync più realistico senza modificare il piano editoriale, la coda o l'invio email.

## Cancellazione

Ogni file audio/video viene creato dentro `work/` e cancellato dopo l'invio. Anche in caso di errore viene eseguito il cleanup finale del workflow.
