# ffmpeg_check_and_tests.py
import sys
import shutil
import subprocess
import unittest

ERROR_MSG = "Fehler: ffmpeg ist nicht installiert oder nicht lauffähig. Bitte installieren: sudo apt install ffmpeg"


def ensure_ffmpeg(timeout=3):
    """
    Prüfe:
      - ffmpeg ist im PATH (shutil.which)
      - ffmpeg lässt sich ausführen (ffmpeg -version exit code 0, stdout enthält 'ffmpeg')
    """
    exe = shutil.which("ffmpeg")
    if exe is None:
        sys.exit(ERROR_MSG)

    try:
        out = subprocess.run(
            [exe, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        sys.exit(ERROR_MSG)

    # Die Ausgabe sollte 'ffmpeg version' enthalten
    if not out.stdout or "ffmpeg" not in out.stdout.lower():
        sys.exit(ERROR_MSG)

    return True


RUN_INTEGRATION = True


@unittest.skipUnless(RUN_INTEGRATION, "Integrationstest ist standardmäßig deaktiviert.")
class TestFfmpegCheckIntegration(unittest.TestCase):
    def test_real_environment(self):
        try:
            self.assertTrue(ensure_ffmpeg())
        except SystemExit as e:
            self.fail(f"Integrierter ffmpeg-Check fehlgeschlagen: {e}")


if __name__ == "__main__":
    unittest.main()
