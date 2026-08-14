import asyncio
import csv
import io
import json
import os
import shutil
import smtplib
import subprocess
import textwrap
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import edge_tts

PLAN_CSV_URL = os.environ.get("PLAN_CSV_URL", "").strip()
MAIL_FROM = os.environ.get("MAIL_FROM", "agenzia.realmediapro@gmail.com").strip()
MAIL_TO = os.environ.get("MAIL_TO", "agenzia.realmediapro@gmail.com").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
MAX_VIDEOS = int(os.environ.get("MAX_VIDEOS", "3"))
SADTALKER_DIR = Path(os.environ.get("SADTALKER_DIR", "/opt/SadTalker"))
STATUS_WEBHOOK_URL = os.environ.get("STATUS_WEBHOOK_URL", "").strip()

TZ = ZoneInfo("Europe/Rome")
TODAY = datetime.now(TZ).date().isoformat()
ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
STATE_FILE = ROOT / "state" / "processed.json"

OPERATOR_CONFIG = {
    "F1_OPERATOR_01": {
        "avatar_url": os.environ.get("AVATAR_01_URL", "").strip(),
        "preferred_voice": os.environ.get("VOICE_01", "it-IT-IsabellaNeural").strip(),
        "label": "SOFIA",
    },
    "F1_OPERATOR_02": {
        "avatar_url": os.environ.get("AVATAR_02_URL", "").strip(),
        "preferred_voice": os.environ.get("VOICE_02", "it-IT-DiegoNeural").strip(),
        "label": "MARCO",
    },
    "F1_OPERATOR_03": {
        "avatar_url": os.environ.get("AVATAR_03_URL", "").strip(),
        "preferred_voice": os.environ.get("VOICE_03", "it-IT-ElsaNeural").strip(),
        "label": "GIULIA",
    },
}


def read_plan():
    if not PLAN_CSV_URL:
        raise RuntimeError("PLAN_CSV_URL non configurato nei GitHub Actions secrets.")
    with urllib.request.urlopen(PLAN_CSV_URL, timeout=30) as response:
        data = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(data)))


def load_processed():
    if not STATE_FILE.exists():
        return set()
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(payload.get("processed_ids", []))
    except Exception:
        return set()


def save_processed(processed):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"processed_ids": sorted(processed)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def choose_rows(rows, processed):
    picked = []
    for row in rows:
        status = (row.get("STATO") or "").strip().upper()
        text = (row.get("TESTO_60_SEC") or "").strip()
        day = (row.get("DATA") or "").strip()
        video_id = (row.get("ID_VIDEO") or "").strip()
        if day == TODAY and status == "DA_PRODURRE" and text and video_id not in processed:
            picked.append(row)
    return picked[:MAX_VIDEOS]


def download(url, destination):
    if not url:
        raise RuntimeError(f"URL avatar mancante per {destination.name}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "F1-Video-AI/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())
    if destination.stat().st_size < 10_000:
        raise RuntimeError(f"Avatar non valido o troppo piccolo: {destination.name}")


async def choose_italian_voice(preferred):
    voices = await edge_tts.list_voices()
    italian = [v["ShortName"] for v in voices if v.get("Locale", "").lower().startswith("it-it")]
    if not italian:
        raise RuntimeError("Nessuna voce italiana disponibile nel provider TTS.")
    return preferred if preferred in italian else italian[0]


async def synthesize_voice(text, preferred_voice, mp3_path):
    voice = await choose_italian_voice(preferred_voice)
    print("Voce selezionata:", voice)
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+2%", pitch="+0Hz")
    await communicate.save(str(mp3_path))
    return voice


def mp3_to_wav(mp3_path, wav_path):
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def run_sadtalker(avatar_path, wav_path, result_root):
    inference = SADTALKER_DIR / "inference.py"
    if not inference.exists():
        raise RuntimeError(f"SadTalker non installato in {SADTALKER_DIR}")

    result_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python", str(inference),
        "--driven_audio", str(wav_path),
        "--source_image", str(avatar_path),
        "--result_dir", str(result_root),
        "--still",
        "--preprocess", "full",
        "--size", "256",
    ]
    print("Avvio SadTalker CPU...")
    subprocess.run(cmd, cwd=str(SADTALKER_DIR), check=True)

    candidates = sorted(result_root.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("SadTalker non ha prodotto alcun MP4.")
    return candidates[0]


def wrap_text(value, width, max_lines):
    lines = textwrap.wrap((value or "").strip(), width=width)
    return "\n".join(lines[:max_lines])


def make_vertical_video(row, talking_head, output_path, operator_label):
    title_file = output_path.with_suffix(".title.txt")
    cta_file = output_path.with_suffix(".cta.txt")
    title_file.write_text(wrap_text(row.get("TITOLO_HOOK") or "F1 Immobiliare", 34, 3), encoding="utf-8")
    cta_file.write_text(wrap_text(row.get("CTA") or "Contatta F1 Immobiliare", 46, 3), encoding="utf-8")

    title_path = str(title_file).replace("'", "'\\''")
    cta_path = str(cta_file).replace("'", "'\\''")
    font_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    filter_complex = (
        "[0:v]scale=1080:1080:force_original_aspect_ratio=decrease,"
        "pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=black[face];"
        "[1:v][face]overlay=0:300[tmp];"
        f"[tmp]drawbox=x=0:y=0:w=1080:h=210:color=white@0.97:t=fill,"
        f"drawtext=fontfile={font_bold}:text='F1 IMMOBILIARE':x=(w-text_w)/2:y=55:fontsize=64:fontcolor=0x111111,"
        f"drawtext=fontfile={font_regular}:text='PRESENTATORE DIGITALE • {operator_label}':x=(w-text_w)/2:y=145:fontsize=27:fontcolor=0x3f4a58,"
        f"drawtext=fontfile={font_bold}:textfile='{title_path}':x=(w-text_w)/2:y=1410:fontsize=44:fontcolor=white:line_spacing=12:box=1:boxcolor=black@0.48:boxborderw=22,"
        f"drawtext=fontfile={font_regular}:textfile='{cta_path}':x=(w-text_w)/2:y=1660:fontsize=32:fontcolor=white:line_spacing=10:box=1:boxcolor=black@0.35:boxborderw=18[v]"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(talking_head),
            "-f", "lavfi", "-i", "color=c=0x0e1726:s=1080x1920:r=25",
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
            "-maxrate", "1400k", "-bufsize", "2800k", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-shortest", "-t", "60",
            str(output_path),
        ],
        check=True,
    )


def send_mail(row, mp4_path, voice_name, operator_label):
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_APP_PASSWORD non configurata nei GitHub Actions secrets.")
    if mp4_path.stat().st_size > 24 * 1024 * 1024:
        raise RuntimeError("Video oltre il limite prudenziale per allegato Gmail (24 MB).")

    video_id = row.get("ID_VIDEO", "F1-VIDEO")
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    msg["Subject"] = f"F1 VIDEO PRONTO — {video_id}"
    msg.set_content(
        "Video pronto per la pubblicazione.\n\n"
        f"ID: {video_id}\n"
        f"Data piano: {row.get('DATA', '')}\n"
        f"Slot: {row.get('SLOT', '')}\n"
        f"Rubrica: {row.get('RUBRICA', '')}\n"
        f"Titolo: {row.get('TITOLO_HOOK', '')}\n"
        f"Avatar: {operator_label}\n"
        f"Voce neurale: {voice_name}\n\n"
        "Il file temporaneo viene cancellato dal runner dopo l'invio."
    )
    msg.add_attachment(mp4_path.read_bytes(), maintype="video", subtype="mp4", filename=f"{video_id}.mp4")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(MAIL_FROM, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def post_status(row, state, detail=""):
    if not STATUS_WEBHOOK_URL:
        return
    payload = json.dumps(
        {"id_video": row.get("ID_VIDEO", ""), "stato": state, "dettaglio": detail},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        STATUS_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            response.read()
    except Exception as exc:
        print("STATUS_WEBHOOK warning:", exc)


def cleanup(paths):
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()
        except Exception as exc:
            print("cleanup warning", path, exc)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    processed = load_processed()
    rows = choose_rows(read_plan(), processed)
    print(f"Righe da produrre oggi ({TODAY}): {len(rows)}")
    if not rows:
        return

    for row in rows:
        video_id = (row.get("ID_VIDEO") or "video").replace("/", "-")
        operator_id = (row.get("OPERATORE_IA") or "F1_OPERATOR_01").strip()
        config = OPERATOR_CONFIG.get(operator_id)
        if not config:
            raise RuntimeError(f"Operatore IA non configurato: {operator_id}")

        avatar = WORK / f"{video_id}-avatar.jpg"
        mp3 = WORK / f"{video_id}.mp3"
        wav = WORK / f"{video_id}.wav"
        result_root = WORK / f"{video_id}-sadtalker"
        final_mp4 = WORK / f"{video_id}.mp4"
        title_txt = final_mp4.with_suffix(".title.txt")
        cta_txt = final_mp4.with_suffix(".cta.txt")

        post_status(row, "IN_LAVORAZIONE")
        try:
            download(config["avatar_url"], avatar)
            voice_name = asyncio.run(synthesize_voice(row["TESTO_60_SEC"], config["preferred_voice"], mp3))
            mp3_to_wav(mp3, wav)
            talking_head = run_sadtalker(avatar, wav, result_root)
            make_vertical_video(row, talking_head, final_mp4, config["label"])
            send_mail(row, final_mp4, voice_name, config["label"])

            processed.add((row.get("ID_VIDEO") or "").strip())
            save_processed(processed)
            post_status(row, "INVIATO", f"{config['label']} / {voice_name}")
            print("INVIATO", video_id)
        except Exception as exc:
            post_status(row, "ERRORE", str(exc)[:500])
            print("ERRORE", video_id, exc)
            raise
        finally:
            cleanup([avatar, mp3, wav, result_root, final_mp4, title_txt, cta_txt])


if __name__ == "__main__":
    main()
