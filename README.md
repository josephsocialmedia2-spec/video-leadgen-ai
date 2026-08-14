# F1 Video Leadgen AI

Automazione basata su GitHub Actions per produrre fino a **3 video verticali al giorno** partendo dal piano contenutistico F1 su Google Sheets.

## Flusso operativo

1. Si aggiorna il Google Sheet `F1 PIANO CONTENUTISTICO VIDEO AI`.
2. Si compila `TESTO_60_SEC` e si imposta `STATO = DA_PRODURRE`.
3. GitHub Actions legge il piano.
4. `edge-tts` genera una voce neurale italiana.
5. SadTalker riceve **foto avatar + audio** e genera un vero talking-head video.
6. FFmpeg impagina il talking head in 1080×1920 con intestazione F1, hook e CTA.
7. Il video finale viene inviato a `agenzia.realmediapro@gmail.com`.
8. Audio, immagini e MP4 temporanei vengono cancellati dal runner.
9. Nel repository resta solo l'ID del video già elaborato in `state/processed.json`, per evitare doppi invii.

## Piano Google Drive

Spreadsheet del progetto:

`1DiJ_p0CdgrLVcXz6rY67PD3iJe9n5RvHfz-60UaYTYg`

Per il runner serve un URL CSV leggibile. Nel Google Sheet: **File → Condividi → Pubblica sul web**, selezionare il foglio `PIANO_VIDEO` e il formato CSV. Copiare l'URL nel secret GitHub `PLAN_CSV_URL`.

## Secret GitHub richiesti

Repository → **Settings → Secrets and variables → Actions → New repository secret**.

- `PLAN_CSV_URL`: URL CSV del foglio `PIANO_VIDEO`.
- `GMAIL_APP_PASSWORD`: password per app Google di `agenzia.realmediapro@gmail.com`.
- `AVATAR_01_URL`: URL diretto dell'immagine di SOFIA.
- `AVATAR_02_URL`: URL diretto dell'immagine di MARCO.
- `AVATAR_03_URL`: URL diretto dell'immagine di GIULIA.
- `STATUS_WEBHOOK_URL`: opzionale; endpoint per aggiornare automaticamente lo stato nel Google Sheet.

Gli URL avatar devono restituire direttamente un file immagine e non una pagina HTML di anteprima.

## Voci

Il programma interroga il provider TTS e usa soltanto voci con locale `it-IT`. Le preferenze predefinite sono:

- SOFIA: `it-IT-IsabellaNeural`
- MARCO: `it-IT-DiegoNeural`
- GIULIA: `it-IT-ElsaNeural`

Se una voce non è disponibile, il programma sceglie automaticamente una voce italiana presente in quel momento.

Le preferenze possono essere sovrascritte con le GitHub Actions Variables `VOICE_01`, `VOICE_02`, `VOICE_03`.

## SadTalker

Il workflow clona il repository ufficiale `OpenTalker/SadTalker`, scarica i modelli ufficiali e usa la modalità CPU a 256 px per il talking head. Non viene usato il vecchio operatore grafico FFmpeg.

La prima versione evita GFPGAN nel rendering finale per limitare tempo e memoria sul runner CPU. FFmpeg ricompone poi il risultato a 1080×1920.

## Esecuzione

Il workflow parte automaticamente ogni giorno alle 05:30 UTC oppure manualmente da:

**Actions → F1 Video AI Daily → Run workflow**

Elabora al massimo tre righe della data odierna con:

- `STATO = DA_PRODURRE`
- `TESTO_60_SEC` non vuoto
- `ID_VIDEO` non già presente in `state/processed.json`

## Cancellazione

Tutti gli asset di lavoro vengono creati dentro `work/` oppure nella directory temporanea del runner e cancellati alla fine. Il repository non archivia WAV, MP3, avatar o MP4.

## Nota sulle prestazioni

SadTalker è un modello di generazione video pesante. I runner GitHub standard sono CPU: il workflow è configurato con un timeout esteso. Se i test CPU risultassero troppo lenti per 3 video da 60 secondi, l'orchestrazione resterà identica e si potrà spostare soltanto il motore SadTalker su un runner GPU esterno, senza modificare Google Sheet, email o logica editoriale.
