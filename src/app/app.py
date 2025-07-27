from flask import Flask, request, redirect, url_for, render_template, send_from_directory
from pathlib import Path
import uuid
import shutil
from src.transcriber.utils import extract_audio
from src.transcriber.whisper_runner import run_whisper
import json

app = Flask(__name__)

UPLOAD_DIR = Path("data/video")
AUDIO_DIR = Path("data/audio")
TRANSCRIPT_DIR = Path("data/transcripts")

for d in [UPLOAD_DIR, AUDIO_DIR, TRANSCRIPT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


@app.route("/", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files["video"]
        if not file.filename.endswith((".mp4", ".mov", ".mkv")):
            return "Invalid file type", 400

        file_id = str(uuid.uuid4())
        video_path = UPLOAD_DIR / f"{file_id}.mp4"
        audio_path = AUDIO_DIR / f"{file_id}.wav"
        transcript_path = TRANSCRIPT_DIR / f"{file_id}.json"

        with open(video_path, "wb") as f:
            shutil.copyfileobj(file.stream, f)

        extract_audio(video_path, audio_path)
        run_whisper(audio_path, transcript_path)

        return redirect(url_for("result", file_id=file_id))

    return render_template("upload.html")


@app.route("/result/<file_id>")
def result(file_id):
    transcript_path = TRANSCRIPT_DIR / f"{file_id}.json"
    if not transcript_path.exists():
        return "Transcript not found", 404

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    return render_template("result.html", transcript=transcript, file_id=file_id)



if __name__ == "__main__":
    app.run()