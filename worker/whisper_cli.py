import sys
import json
import argparse
from pathlib import Path
from faster_whisper import WhisperModel

def transcribe(audio_path, output_dir, model_name, language):
    # Pfade zu Path-Objekten machen und absolutieren
    audio_file = Path(audio_path).resolve()
    out_dir = Path(output_dir).resolve()
    
    print(json.dumps({"status": "starting", "model": model_name}), flush=True)
    
    model = WhisperModel(model_name, device="cuda", compute_type="int8_float32")
    
    lang_param = language if language else None
    
    print(json.dumps({"status": "transcribing"}), flush=True)
    
    # Transkription auf dem absoluten Pfad ausführen
    segments, info = model.transcribe(str(audio_file), language=lang_param, beam_size=1)
    
    print(json.dumps({"status": "language_detected", "language": info.language}), flush=True)

    result = []
    for segment in segments:
        progress = (segment.end / info.duration) * 100 if info.duration > 0 else 0
        
        print(json.dumps({
            "status": "progress", 
            "progress": round(progress, 2), 
            "text": segment.text
        }), flush=True)
        
        result.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip()
        })

    # Die JSON-Datei landet jetzt sauber im angegebenen Ordner
    output_path = out_dir / (audio_file.stem + ".json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        
    print(json.dumps({"status": "finished", "output": str(output_path)}), flush=True)
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Whisper CLI Worker")
    parser.add_argument("audio_path", help="Pfad zur Audiodatei")
    parser.add_argument("output_dir", help="Verzeichnis für die JSON-Ausgabe")
    parser.add_argument("--model", default="medium", help="Modellgröße (default: medium)")
    parser.add_argument("--language", default=None, help="Sprache (z.B. 'de' oder 'en'). Leer für Auto-Detect.")
    
    args = parser.parse_args()
    
    try:
        transcribe(args.audio_path, args.output_dir, args.model, args.language)
    except Exception as e:
        # Fange Fehler ab und sende sie strukturiert an FastAPI
        print(json.dumps({"status": "error", "message": str(e)}), flush=True)
        sys.exit(1)
