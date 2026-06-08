# Video Transcription Service

FastAPI backend for transcribing videos using Whisper Docker container with searchable transcriptions stored in SQLite with FTS5 full-text search.

## Features

- **Video Upload**: Upload videos via POST /upload endpoint
- **Docker Orchestration**: Uses whisper-clean Docker container for transcription
- **Async Processing**: Non-blocking background task processing
- **Full-Text Search**: FTS5-powered search across all transcriptions
- **SQLite Storage**: Efficient local database with triggers for FTS sync
- **Pydantic Validation**: Type-safe data models

## Installation

```bash
pip install -r requirements.txt
```

## Running the Application

```bash
python main.py
```

Or using uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### POST /upload
Upload a video file for transcription.

**Request**: multipart/form-data with file field
**Response**: 
```json
{
  "job_id": "uuid",
  "status": "processing",
  "message": "Video uploaded successfully. Transcription in progress."
}
```

### GET /transcription/{job_id}
Retrieve a transcription by job ID.

**Response**: Transcription data with segments

### POST /search
Search transcriptions using full-text search.

**Request Body**:
```json
{
  "query": "search term"
}
```

**Response**: List of matching transcriptions

### GET /transcriptions
Retrieve all transcriptions.

### GET /health
Health check endpoint.

## Project Structure

```
.
├── main.py              # FastAPI application
├── database.py          # SQLite database with FTS5
├── models.py            # Pydantic models
├── requirements.txt     # Python dependencies
├── workspaces/          # Temporary job directories (created at runtime)
└── transcriptions.db    # SQLite database (created at runtime)
```

## Docker Container

The application expects a Docker container named `whisper-clean` that:
- Accepts video file path as first argument
- Accepts output directory as second argument
- Accepts model size as third argument (e.g., "medium")
- Outputs JSON transcription file with same name as video

## Notes

- Ensure Docker is installed and running
- Ensure the whisper-clean container is available
- GPU support is enabled with `--gpus all` flag
- Cache directory: `~/.cache/huggingface`
