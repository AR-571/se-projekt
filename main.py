"""
FastAPI backend for video transcription orchestration.
This application manages video uploads, orchestrates Docker-based transcription,
and stores results in a SQLite database with FTS5 full-text search.
"""
import os
import uuid
import asyncio
import subprocess
import json
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from database import Database
from models import (
    TranscriptionResponse,
    UploadResponse,
    ErrorResponse,
    SearchRequest,
    SearchResponse,
    TranscriptionSegment
)


# Configuration
WORKSPACE_BASE_DIR = Path("workspaces")
HOME_CACHE_PATH = Path.home() / ".cache" / "huggingface"
DB_PATH = "transcriptions.db"


# Initialize FastAPI app
app = FastAPI(
    title="Video Transcription Service",
    description="API for transcribing videos using Whisper and storing searchable transcriptions",
    version="1.0.0"
)


# Global database instance
db = Database(db_path=DB_PATH)

# Global job progress tracking
job_progress = {}

# GPU concurrency lock to prevent multiple simultaneous transcriptions
is_processing_active = False


@app.on_event("startup")
async def startup_event():
    """
    Initialize database connection on application startup.
    """
    await db.connect()
    # Ensure workspace directory exists
    WORKSPACE_BASE_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("shutdown")
async def shutdown_event():
    """
    Close database connection on application shutdown.
    """
    await db.disconnect()


def get_video_duration(video_path: Path) -> Optional[float]:
    """
    Get the total duration of a video file using ffprobe.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Duration in seconds as float, or None if failed
    """
    try:
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            return duration
        return None
    except (subprocess.TimeoutExpired, ValueError, Exception) as e:
        print(f"Failed to get video duration: {str(e)}")
        return None


def run_docker_transcription(job_id: str, workspace_path: Path, filename: str, total_duration: float) -> bool:
    """
    Execute the Docker container for video transcription using subprocess.
    
    This function runs the Whisper Docker container synchronously.
    It should be called in a separate thread/process to avoid blocking the async event loop.
    Reads stdout line-by-line to track progress updates from the Docker container.
    
    Args:
        job_id: Unique identifier for the transcription job
        workspace_path: Path to the workspace directory
        filename: Name of the video file to transcribe
        total_duration: Total duration of the video in seconds
        
    Returns:
        True if transcription succeeded, False otherwise
    """
    try:
        # Convert paths to absolute paths (required by Docker for host directory mounts)
        workspace_absolute = workspace_path.resolve()
        cache_absolute = HOME_CACHE_PATH.resolve()
        
        # Construct the Docker command
        command = [
            "docker", "run", "--rm", "--gpus", "all",
            f"-v {workspace_absolute}:/workspace",
            f"-v {cache_absolute}:/root/.cache/huggingface",
            "whisper-clean",
            f"/workspace/{filename}",
            "/workspace",
            "large-v3-turbo"
        ]
        
        # Initialize progress for this job
        job_progress[job_id] = 0.0
        
        # Run the Docker container with Popen to read stdout line-by-line
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Read stdout line-by-line to track progress
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                line = line.strip()
                # Parse progress from text output like "[681.00s -> 692.00s] Text..."
                match = re.search(r'\[(\d+\.?\d*)s -> (\d+\.?\d*)s\]', line)
                if match and total_duration > 0:
                    current_end = float(match.group(2))
                    progress = (current_end / total_duration) * 100
                    job_progress[job_id] = min(progress, 100.0)
                    print(f"Job {job_id} progress: {progress:.2f}%")
        
        # Wait for process to complete
        return_code = process.wait()
        
        # Check if the command succeeded
        if return_code != 0:
            stderr = process.stderr.read()
            print(f"Docker command failed with return code {return_code}")
            print(f"STDERR: {stderr}")
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        print("Docker command timed out after 1 hour")
        return False
    except Exception as e:
        print(f"Error running Docker command: {str(e)}")
        return False
    finally:
        # Clean up progress entry when done
        if job_id in job_progress:
            del job_progress[job_id]


async def process_transcription(job_id: str, workspace_path: Path, filename: str, session_id: str) -> None:
    """
    Background task to process the transcription after file upload.
    
    This function:
    1. Gets video duration using ffprobe
    2. Sets GPU concurrency lock
    3. Runs the Docker container in a thread pool to avoid blocking
    4. Reads the generated JSON file
    5. Stores the transcription in the database
    6. Clears GPU concurrency lock
    
    Args:
        job_id: Unique identifier for the transcription job
        workspace_path: Path to the workspace directory
        filename: Name of the video file
        session_id: Session identifier for isolation
    """
    global is_processing_active
    try:
        # Set GPU concurrency lock
        is_processing_active = True
        
        # Get video duration for progress tracking
        video_path = workspace_path / filename
        total_duration = get_video_duration(video_path)
        
        if total_duration is None:
            print(f"Failed to get video duration for job {job_id}, using default 0")
            total_duration = 0.0
        
        # Run Docker transcription in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None,
            run_docker_transcription,
            job_id,
            workspace_path,
            filename,
            total_duration
        )
        
        if not success:
            print(f"Transcription failed for job {job_id}")
            return
        
        # Find the generated JSON file (expected to have same name as video but .json extension)
        json_filename = Path(filename).stem + ".json"
        json_path = workspace_path / json_filename
        
        if not json_path.exists():
            print(f"JSON file not found at {json_path}")
            return
        
        # Read and parse the JSON file
        with open(json_path, 'r', encoding='utf-8') as f:
            transcription_data = json.load(f)
        
        # Store transcription in database
        await db.save_transcription(
            video_filename=filename,
            job_id=job_id,
            session_id=session_id,
            transcription_data=transcription_data
        )
        
        print(f"Transcription completed and stored for job {job_id}")
        
    except Exception as e:
        print(f"Error processing transcription for job {job_id}: {str(e)}")
    finally:
        # Always clear GPU concurrency lock
        is_processing_active = False


@app.post("/upload", response_model=UploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session_id: str = None
) -> UploadResponse:
    """
    Upload a video file for transcription.
    
    This endpoint:
    1. Accepts a video file upload
    2. Creates a unique workspace directory
    3. Saves the file to the workspace
    4. Initiates background transcription using Docker
    
    Args:
        background_tasks: FastAPI BackgroundTasks for async processing
        file: Uploaded video file
        session_id: Session identifier for isolation (required)
        
    Returns:
        UploadResponse with job_id and status
    """
    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="session_id is required"
        )
    
    # Check GPU concurrency lock
    global is_processing_active
    if is_processing_active:
        raise HTTPException(
            status_code=429,
            detail="GPU is currently busy processing another video. Please wait."
        )
    
    # Validate file extension
    allowed_extensions = {".mp4", ".mp3", ".wav", ".m4a"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file format. Allowed formats: {', '.join(allowed_extensions)}"
        )
    
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create workspace directory for this job
        workspace_path = WORKSPACE_BASE_DIR / job_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded file to workspace
        file_path = workspace_path / file.filename
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Add background task for transcription processing
        background_tasks.add_task(
            process_transcription,
            job_id,
            workspace_path,
            file.filename,
            session_id
        )
        
        return UploadResponse(
            job_id=job_id,
            status="processing",
            message="Video uploaded successfully. Transcription in progress."
        )
        
    except Exception as e:
        # Clean up workspace if error occurred
        if 'workspace_path' in locals() and workspace_path.exists():
            import shutil
            shutil.rmtree(workspace_path)
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload video: {str(e)}"
        )


@app.get("/transcription/{job_id}")
async def get_transcription(job_id: str):
    """
    Retrieve a transcription by job ID or return progress status if still processing.
    
    Args:
        job_id: Unique identifier for the transcription job
        
    Returns:
        TranscriptionResponse with transcription data, or progress status if processing
        
    Raises:
        HTTPException: If transcription not found
    """
    # Check if job is still processing
    if job_id in job_progress:
        return {
            "status": "processing",
            "progress": job_progress[job_id]
        }
    
    # Check if transcription is completed in database
    transcription = await db.get_transcription(job_id)
    
    if not transcription:
        raise HTTPException(
            status_code=404,
            detail=f"Transcription with job_id {job_id} not found"
        )
    
    # Convert transcription data to Pydantic models
    segments = [
        TranscriptionSegment(**segment)
        for segment in transcription["transcription_data"]
    ]
    
    return TranscriptionResponse(
        id=transcription["id"],
        video_filename=transcription["video_filename"],
        job_id=transcription["job_id"],
        session_id=transcription["session_id"],
        transcription_data=segments,
        created_at=transcription["created_at"]
    )


@app.post("/search", response_model=SearchResponse)
async def search_transcriptions(request: SearchRequest) -> SearchResponse:
    """
    Search transcriptions using full-text search.
    
    Args:
        request: SearchRequest containing the search query
        
    Returns:
        SearchResponse with matching transcriptions
    """
    try:
        results = await db.search_transcriptions(request.query, request.session_id)
        
        # Convert results to Pydantic models and count matching text segments
        transcription_responses = []
        total_matching_segments = 0
        for result in results:
            segments = [
                TranscriptionSegment(**segment)
                for segment in result["transcription_data"]
            ]
            # Count only segments that match the search query
            matching_segments = [
                segment for segment in segments
                if request.query.lower() in segment.text.lower()
            ]
            total_matching_segments += len(matching_segments)
            transcription_responses.append(
                TranscriptionResponse(
                    id=result["id"],
                    video_filename=result["video_filename"],
                    job_id=result["job_id"],
                    session_id=result["session_id"],
                    transcription_data=segments,
                    created_at=result["created_at"]
                )
            )
        
        return SearchResponse(
            results=transcription_responses,
            count=total_matching_segments
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@app.get("/transcriptions", response_model=SearchResponse)
async def get_all_transcriptions(session_id: Optional[str] = None) -> SearchResponse:
    """
    Retrieve all transcriptions, optionally filtered by session.
    
    Args:
        session_id: Optional session identifier for filtering
        
    Returns:
        SearchResponse with transcriptions
    """
    try:
        results = await db.get_all_transcriptions(session_id)
        
        # Convert results to Pydantic models
        transcription_responses = []
        for result in results:
            segments = [
                TranscriptionSegment(**segment)
                for segment in result["transcription_data"]
            ]
            transcription_responses.append(
                TranscriptionResponse(
                    id=result["id"],
                    video_filename=result["video_filename"],
                    job_id=result["job_id"],
                    session_id=result["session_id"],
                    transcription_data=segments,
                    created_at=result["created_at"]
                )
            )
        
        return SearchResponse(
            results=transcription_responses,
            count=len(transcription_responses)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve transcriptions: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Status of the service
    """
    return {"status": "healthy", "service": "video-transcription-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
