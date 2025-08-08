import subprocess


def extract_audio(video_path, audio_path):
    """Extract audio as .wav from video file, according to whispers needs
    :param str video_path: full path to video file
    :param str audio_path: full path to audio file"""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(video_path),  # Eingabedatei
                "-vn",  # kein Video
                "-acodec", "pcm_s16le",  # unkomprimiertes WAV
                "-ar", "16000",  # 16 kHz Samplerate
                "-ac", "1",  # Mono
                str(audio_path)
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Fehler: ffmpeg nicht gefunden. Bitte installieren"
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Fehler beim Extrahieren von Audio: {e.stderr.decode()}")
