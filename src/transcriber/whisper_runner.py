from pathlib import Path
import subprocess
import shutil

WHISPER_IMAGE = "whisper-cli-with-cached-medium"  # an image with float32 + cached model
DEFAULT_MODEL = "medium"  # "small" | "medium" | "large-v3" <- depends on the image


class WhisperError(RuntimeError):
    pass


def run_whisper(audio_path: Path, output_path: Path, model: str = DEFAULT_MODEL, timeout: int = 36000) -> Path:
    """
    Call the whisper container and write JSON file neben output_path
    Expects the image to have an ENTRYPOINT with whisper_cli.py <- satisfied with our image
    """
    if shutil.which("docker") is None:
        raise WhisperError("Docker nicht gefunden. Ist Docker installiert/gestartet?")

    audio_path = Path(audio_path).resolve()
    output_path = Path(output_path).resolve()

    audio_dir = audio_path.parent
    out_dir = output_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Container-Pfade
    c_audio = f"/audio/{audio_path.name}"
    c_out = "/output"

    cmd = [
        "docker", "run", "--rm",
        "--gpus", "all",
        "-v", f"{audio_dir}:/audio",
        "-v", f"{out_dir}:/output",
        WHISPER_IMAGE,
        c_audio, c_out, model,  # bc of the ENTRYPOINT this argument list is sufficient
    ]

    try:
        res = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise WhisperError(f"Whisper-Container-Fehler: {e.stderr}") from e
    except subprocess.TimeoutExpired:
        raise WhisperError(f"Whisper-Transkription Timeout nach {timeout}s")
    except FileNotFoundError:
        raise WhisperError("Docker-Binary nicht gefunden (PATH)")

    # the CLI writes <stem>.json into /output –> we expect:
    produced = out_dir / (audio_path.stem + ".json")
    if not produced.exists():
        raise WhisperError(f"Erwarte Transkript {produced} – wurde nicht erzeugt.")
    return produced
