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
import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from filelock import FileLock, Timeout
import shutil
import sqlite3
import mimetypes

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request, Query
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv

from database import Database
from models import (
    TranscriptionResponse,
    UploadResponse,
    ErrorResponse,
    SearchRequest,
    SearchResponse,
    TranscriptionSegment
)

# Load environment variables from .env file
load_dotenv()


# Configuration
WORKSPACE_BASE_DIR = Path(__file__).parent / "workspaces"
HOME_CACHE_PATH = Path.home() / ".cache" / "huggingface"
GPU_LOCK_PATH = WORKSPACE_BASE_DIR / ".gpu.lock"
DB_PATH = "transcriptions.db"

# Authentication Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 1 day
STREAMING_TOKEN_EXPIRE_MINUTES = 5
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


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


@app.on_event("startup")
async def startup_event():
    """
    Initialize database connection on application startup.
    """
    await db.connect()
    # Ensure workspace directory exists
    WORKSPACE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure lock file can be created by touching it
    GPU_LOCK_PATH.touch()


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


# --- AUTHENTICATION UTILS ---

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def authenticate_user(username, password):
    # 1. Admin check via .env (existing)
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH")
    
    if username == admin_username and admin_password_hash:
        try:
            if verify_password(password, admin_password_hash):
                return username
        except ValueError as e:
            print(f"Password verification error: {e}")
            
    # 2. Dynamic test user check (hashed, per user)
    test_users_str = os.getenv("TEST_USERS", "")
    if test_users_str:
        test_users = [u.strip() for u in test_users_str.split(",") if u.strip()]
        
        if username in test_users:
            # Build the variable name dynamically, e.g., TUTOR_PASSWORD_HASH
            hash_var_name = f"{username.upper()}_PASSWORD_HASH"
            user_password_hash = os.getenv(hash_var_name)
            
            if user_password_hash:
                try:
                    if verify_password(password, user_password_hash):
                        return username
                except ValueError as e:
                    print(f"Password verification error for {username}: {e}")
            
    return None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        if username is None or token_type != "access":
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    return username


async def run_docker_transcription(job_id: str, workspace_path: Path, filename: str, total_duration: float, username: str) -> bool:
    """
    Execute the Docker container for video transcription using asyncio subprocess.
    
    This function runs the Whisper Docker container asynchronously.
    It reads stdout line-by-line to track progress updates from the Docker container,
    without blocking the FastAPI event loop.
    
    Args:
        job_id: Unique identifier for the transcription job
        workspace_path: Path to the workspace directory
        filename: Name of the video file to transcribe
        total_duration: Total duration of the video in seconds
        username: The user who started the job
        
    Returns:
        True if transcription succeeded, False otherwise
    """
    try:
        # Determine the host path for Docker volume mounts, using HOST_WORKSPACE_DIR if available
        host_workspace_dir = os.getenv("HOST_WORKSPACE_DIR")
        if host_workspace_dir:
            workspace_mount_path = Path(host_workspace_dir) / job_id
        else:
            workspace_mount_path = workspace_path.resolve()

        cache_absolute = HOME_CACHE_PATH.resolve()
        
        # Construct the Docker command
        command = [
            "docker", "run", "--rm", "--gpus", "all",
            "--memory", "12g",          # Limit RAM to prevent host swap/freeze
            "--memory-swap", "12g",     # Disable swapping for the container
            # "--cpus", "4.0",          # Optional: Limit CPU cores if necessary
            "-v", f"{workspace_mount_path}:/workspace",
            "-v", f"{cache_absolute}:/root/.cache/huggingface",
            "whisper-clean",
            f"/workspace/{filename}",
            "/workspace",
            "medium"
        ]
        
        
        # Run the Docker container asynchronously
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10485760  # 10 MB buffer limit to prevent overflows with large outputs
        )
        
        async def read_stdout():
            while True:
                try:
                    line = await process.stdout.readline()
                except ValueError as e:
                    print(f"Warning: Line length exceeded buffer limit in stdout: {e}")
                    # If buffer is exceeded, read and discard chunk to unblock
                    chunk = await process.stdout.read(1048576) 
                    if not chunk:
                        break
                    continue
                
                if not line:
                    break
                    
                line_str = line.decode('utf-8', errors='replace').strip()
                
                # Check if output is from whisper_cli.py (JSON format)
                if line_str.startswith('{') and line_str.endswith('}'):
                    try:
                        data = json.loads(line_str)
                        if data.get("status") == "progress" and "progress" in data:
                            job_progress[job_id]["progress"] = min(float(data["progress"]), 100.0)
                    except json.JSONDecodeError:
                        pass
                else:
                    # Parse progress from standard text output like "[681.00s -> 692.00s] Text..."
                    match = re.search(r'\[(\d+\.?\d*)s -> (\d+\.?\d*)s\]', line_str)
                    if match and total_duration > 0:
                        current_end = float(match.group(2))
                        progress = (current_end / total_duration) * 100
                        job_progress[job_id]["progress"] = min(progress, 100.0)

        async def read_stderr():
            stderr_lines = []
            while True:
                try:
                    line = await process.stderr.readline()
                except ValueError:
                    chunk = await process.stderr.read(1048576)
                    if not chunk:
                        break
                    continue
                if not line:
                    break
                # Only keep last 100 lines to prevent memory unbounded growth from stderr
                if len(stderr_lines) > 100:
                    stderr_lines.pop(0)
                stderr_lines.append(line.decode('utf-8', errors='replace').strip())
            return "\n".join(stderr_lines)

        # Run stdout and stderr readers concurrently with a timeout
        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())
        
        # Wait for process to complete with a 4-hour timeout (14400 seconds)
        await asyncio.wait_for(process.wait(), timeout=14400)
        
        # Ensure readers finish
        await stdout_task
        stderr_output = await stderr_task
        
        # Check if the command succeeded
        if process.returncode != 0:
            print(f"Docker command failed with return code {process.returncode}")
            print(f"STDERR: {stderr_output}")
            return False
        
        return True
        
    except asyncio.TimeoutError:
        print(f"Docker container timed out after 4 hours for job {job_id}")
        try:
            process.kill()
        except OSError:
            pass
        return False
        
    except Exception as e:
        print(f"Error running Docker command: {str(e)}")
        return False


async def process_transcription(job_id: str, workspace_path: Path, filename: str, username: str) -> None:
    """
    Background task to process the transcription after file upload.
    
    This function:
    1. Gets video duration using ffprobe
    2. Sets GPU concurrency lock
    3. Runs the Docker container asynchronously
    4. Reads the generated JSON file
    5. Stores the transcription in the database
    6. Clears GPU concurrency lock
    
    Args:
        job_id: Unique identifier for the transcription job
        workspace_path: Path to the workspace directory
        filename: Name of the video file
        username: Authenticated username for isolation
    """
    # Use a file-based lock to ensure only one transcription runs at a time system-wide
    gpu_lock = FileLock(GPU_LOCK_PATH)
    
    # Initialize progress immediately so the frontend knows it's queued
    job_progress[job_id] = {"progress": 0.0, "username": username}
    
    try:
        # Acquire lock non-blocking to prevent freezing the FastAPI event loop
        while True:
            try:
                gpu_lock.acquire(timeout=0)
                break
            except Timeout:
                await asyncio.sleep(2)
                
        try:
            # Get video duration for progress tracking
            video_path = workspace_path / filename
            total_duration = get_video_duration(video_path)
            
            if total_duration is None:
                print(f"Failed to get video duration for job {job_id}, using default 0")
                total_duration = 0.0
            
            # Run Docker transcription asynchronously
            success = await run_docker_transcription(
                job_id,
                workspace_path,
                filename,
                total_duration,
                username
            )
            
            if not success:
                print(f"Transcription failed for job {job_id}")
                return
            
            # Find the generated JSON file
            json_filename = Path(filename).stem + ".json"
            json_path = workspace_path / json_filename
            
            if not json_path.exists():
                print(f"JSON file not found at {json_path}")
                return
            
            with open(json_path, 'r', encoding='utf-8') as f:
                transcription_data = json.load(f)
            
            # Extract pure text from segments for FTS indexing
            transcription_text = " ".join([segment['text'] for segment in transcription_data])
            
            # Store transcription in database
            await db.save_transcription(
                video_filename=filename,
                job_id=job_id,
                username=username,
                transcription_text=transcription_text,
                transcription_data=transcription_data
            )
            
            print(f"Transcription completed and stored for job {job_id}")
            
        finally:
            gpu_lock.release()
        
    except Exception as e:
        print(f"Error processing transcription for job {job_id}: {str(e)}")
    finally:
        # Clean up progress entry when completely done (including DB save)
        if job_id in job_progress:
            del job_progress[job_id]


# --- ENDPOINTS ---

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(
        data={"sub": user, "type": "access"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/upload", response_model=UploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
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
        
    Returns:
        UploadResponse with job_id and status
    """
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
            current_user
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
async def get_transcription(
    job_id: str,
    current_user: str = Depends(get_current_user)
):
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
        job_info = job_progress[job_id]
        if job_info["username"] != current_user:
            raise HTTPException(
                status_code=404,
                detail=f"Transcription with job_id {job_id} not found"
            )
        return {
            "status": "processing",
            "progress": job_info["progress"]
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
        username=transcription["username"],
        transcription_data=segments,
        created_at=transcription["created_at"]
    )


@app.post("/search", response_model=SearchResponse)
async def search_transcriptions(
    request: SearchRequest,
    current_user: str = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> SearchResponse:
    """
    Search transcriptions using full-text search.
    
    Args:
        request: SearchRequest containing the search query
        current_user: Authenticated user from token
        limit: Maximum number of results to return
        offset: Number of results to skip for pagination
        
    Returns:
        SearchResponse with matching transcriptions
    """
    try:
        results = await db.search_transcriptions(request.query, current_user, limit, offset)
        
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
                    username=result["username"],
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
async def get_all_transcriptions(
    current_user: str = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> SearchResponse:
    """
    Retrieve all transcriptions for the authenticated user.
    
    Args:
        current_user: User identifier from JWT
        limit: Maximum number of results to return
        offset: Number of results to skip for pagination
        
    Returns:
        SearchResponse with transcriptions
    """
    try:
        results = await db.get_all_transcriptions(current_user, limit, offset)
        
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
                    username=result["username"],
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


@app.delete("/transcriptions")
async def delete_all_transcriptions(current_user: str = Depends(get_current_user)):
    """
    Delete all transcriptions and media files for the authenticated user.
    """
    try:
        # 1. Fetch all user's transcriptions to get job_ids
        results = await db.get_all_transcriptions(current_user)
        
        # 2. Delete from database using direct sqlite3 execution 
        # (Since README says FTS sync is handled by triggers, this is sufficient)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transcriptions WHERE username = ?", (current_user,))
            conn.commit()

        # 3. Delete all physical files and directories from workspaces safely
        for result in results:
            job_id = result["job_id"]
            workspace_path = WORKSPACE_BASE_DIR / job_id
            if workspace_path.exists():
                shutil.rmtree(workspace_path, ignore_errors=True)
            
        return {"status": "success", "message": f"Deleted {len(results)} transcription(s)"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete transcriptions: {str(e)}"
        )


@app.get("/streaming-token/{job_id}")
async def get_streaming_token(job_id: str, current_user: str = Depends(get_current_user)):
    transcription = await db.get_transcription(job_id)
    if not transcription or transcription["username"] != current_user:
        raise HTTPException(status_code=404, detail="Transcription not found")
    
    token = create_access_token(
        data={"sub": current_user, "job_id": job_id, "type": "streaming"},
        expires_delta=timedelta(minutes=STREAMING_TOKEN_EXPIRE_MINUTES)
    )
    return {"streaming_token": token}


@app.get("/media/{job_id}")
async def get_media(job_id: str, token: str, request: Request):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "streaming" or payload.get("job_id") != job_id:
            raise HTTPException(status_code=403, detail="Invalid streaming token")
    except InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid streaming token")
    
    workspace_path = WORKSPACE_BASE_DIR / job_id

    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Media workspace not found")

    media_files = [f for f in workspace_path.iterdir() if f.is_file() and f.suffix != ".json"]
    if not media_files:
        raise HTTPException(status_code=404, detail="Media not found")
        
    file_path = media_files[0]
    file_size = file_path.stat().st_size
    
    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or "application/octet-stream"
    
    # Check if the browser requests a specific part (Range)
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(file_path, headers={"Accept-Ranges": "bytes"}, media_type=content_type)
        
    try:
        # Parse the Range header (e.g., "bytes=0-1023")
        byte_range = range_header.replace("bytes=", "").split("-")
        start = int(byte_range[0])
        end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
    except ValueError:
        return Response(status_code=400, content="Invalid Range header")
        
    if start >= file_size or end >= file_size:
        return Response(
            status_code=416, 
            content="Range Not Satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"}
        )
        
    chunk_size = end - start + 1
    
    # Generator function that efficiently loads the video in small 1MB chunks
    def file_iterator(path, start_byte, bytes_to_read):
        with open(path, "rb") as f:
            f.seek(start_byte)
            bytes_read = 0
            while bytes_read < bytes_to_read:
                read_size = min(1024 * 1024, bytes_to_read - bytes_read)
                chunk = f.read(read_size)
                if not chunk:
                    break
                bytes_read += len(chunk)
                yield chunk
                
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": content_type
    }
    
    return StreamingResponse(
        file_iterator(file_path, start, chunk_size),
        status_code=206,  # 206 Partial Content tells the browser that this is only a chunk
        headers=headers
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
