import csv, io, os, smtplib, subprocess, tempfile, textwrap, urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

PLAN_CSV_URL = os.environ.get('PLAN_CSV_URL','').strip()
MAIL_FROM = os.environ.get('MAIL_FROM','agenzia.realmediapro@gmail.com').strip()
MAIL_TO = os.environ.get('MAIL_TO','agenzia.realmediapro@gmail.com').strip()
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD','').strip()
MAX_VIDEOS = int(os.environ.get('MAX_VIDEOS','3'))
TZ = ZoneInfo('Europe/Rome')
TODAY = datetime.now(TZ).date().isoformat()
ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work'
VOICE = ROOT / 'models' / 'it_IT-paola-medium.onnx'
VOICE_JSON = ROOT / 'models' / 'it_IT-paola-medium.onnx.json'

VOICE_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx?download=true'
VOICE_JSON_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx.json?download=true'


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print('Downloading', dest.name)
        urllib.request.urlretrieve(url, dest)


def read_plan():
    if not PLAN_CSV_URL:
        raise RuntimeError('PLAN_CSV_URL non configurato nei GitHub Actions secrets/variables.')
    with urllib.request.urlopen(PLAN_CSV_URL, timeout=30) as r:
        data = r.read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(data)))


def choose_rows(rows):
    picked=[]
    for row in rows:
        status=(row.get('STATO') or '').strip().upper()
        text=(row.get('TESTO_60_SEC') or '').strip()
        d=(row.get('DATA') or '').strip()
        if d == TODAY and status == 'DA_PRODURRE' and text:
            picked.append(row)
    return picked[:MAX_VIDEOS]


def tts(text, wav_path):
    download(VOICE_URL, VOICE)
    download(VOICE_JSON_URL, VOICE_JSON)
    subprocess.run(
        ['python','-m','piper','-m',str(VOICE),'-c',str(VOICE_JSON),'-f',str(wav_path),'--',text],
        check=True
    )


def escape_drawtext(s):
    return (s.replace('\\','\\\\').replace(':','\\:').replace("'","\\'")
             .replace('%','\\%').replace(',','\\,'))


def make_video(row, wav_path, mp4_path):
    title=(row.get('TITOLO_HOOK') or 'F1 Immobiliare').strip()
    cta=(row.get('CTA') or 'Seguici per altri consigli immobiliari.').strip()
    operator=(row.get('OPERATORE_IA') or 'F1_OPERATOR_01').strip()
    # Operatore digitale grafico: leggero, deterministico e compatibile con runner CPU.
    title_e=escape_drawtext(title[:100])
    cta_e=escape_drawtext(cta[:120])
    op_e=escape_drawtext(operator.replace('_',' '))
    vf = (
        "drawbox=x=0:y=0:w=1080:h=1920:color=0x0e1726:t=fill,"
        "drawbox=x=0:y=0:w=1080:h=185:color=0xffffff@0.96:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='F1 IMMOBILIARE':x=(w-text_w)/2:y=55:fontsize=64:fontcolor=0x111111,"
        "drawbox=x=160:y=330:w=760:h=980:color=0x182c47:t=fill,"
        "drawbox=x=260:y=445:w=560:h=560:color=0xf1c27d:t=fill,"
        "drawbox=x=365:y=600:w=55:h=40:color=black:t=fill,"
        "drawbox=x=660:y=600:w=55:h=40:color=black:t=fill,"
        "drawbox=x=430:y=790:w=220:h=30:color=0x7f1d1d:t=fill:enable='lt(mod(t,0.44),0.22)',"
        "drawbox=x=430:y=770:w=220:h=90:color=0x7f1d1d:t=fill:enable='gte(mod(t,0.44),0.22)',"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='{op_e}':x=(w-text_w)/2:y=1060:fontsize=50:fontcolor=white,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='OPERATORE DIGITALE F1':x=(w-text_w)/2:y=1130:fontsize=34:fontcolor=0xb8c4d6,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='{title_e}':x=(w-text_w)/2:y=1400:fontsize=44:fontcolor=white:box=1:boxcolor=0x000000@0.45:boxborderw=20,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='{cta_e}':x=(w-text_w)/2:y=1620:fontsize=34:fontcolor=white:box=1:boxcolor=0x000000@0.35:boxborderw=16"
    )
    subprocess.run([
        'ffmpeg','-y','-f','lavfi','-i','color=c=black:s=1080x1920:r=25',
        '-i',str(wav_path),'-vf',vf,'-map','0:v','-map','1:a',
        '-c:v','libx264','-preset','veryfast','-crf','28','-maxrate','1800k','-bufsize','3600k','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','128k','-shortest','-t','60',str(mp4_path)
    ], check=True)


def send_mail(row, mp4_path):
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError('GMAIL_APP_PASSWORD non configurata nei GitHub Actions secrets.')
    msg=EmailMessage()
    msg['From']=MAIL_FROM
    msg['To']=MAIL_TO
    vid=row.get('ID_VIDEO','F1-VIDEO')
    msg['Subject']=f'F1 VIDEO PRONTO — {vid}'
    msg.set_content(
        f"Video pronto per la pubblicazione.\n\nID: {vid}\nData piano: {row.get('DATA','')}\nSlot: {row.get('SLOT','')}\nRubrica: {row.get('RUBRICA','')}\nTitolo: {row.get('TITOLO_HOOK','')}\n\nIl file temporaneo viene cancellato dal runner dopo l'invio."
    )
    data=mp4_path.read_bytes()
    msg.add_attachment(data, maintype='video', subtype='mp4', filename=f'{vid}.mp4')
    with smtplib.SMTP_SSL('smtp.gmail.com',465) as s:
        s.login(MAIL_FROM,GMAIL_APP_PASSWORD)
        s.send_message(msg)


def main():
    WORK.mkdir(exist_ok=True)
    rows=choose_rows(read_plan())
    print(f'Righe da produrre oggi ({TODAY}): {len(rows)}')
    if not rows:
        return
    for row in rows:
        vid=(row.get('ID_VIDEO') or 'video').replace('/','-')
        wav=WORK/f'{vid}.wav'
        mp4=WORK/f'{vid}.mp4'
        try:
            tts(row['TESTO_60_SEC'], wav)
            make_video(row, wav, mp4)
            send_mail(row, mp4)
            print('INVIATO', vid)
        finally:
            for p in (wav,mp4):
                try:
                    if p.exists(): p.unlink()
                except Exception as e:
                    print('cleanup warning', p, e)

if __name__=='__main__':
    main()
