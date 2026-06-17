"""
Pydantic models for data validation and serialization.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class TranscriptionSegment(BaseModel):
    """
    Represents a single segment of a transcription with timestamp and text.
    """
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    text: str = Field(..., description="Transcribed text for this segment")


class TranscriptionResponse(BaseModel):
    """
    Response model for a transcription query.
    """
    id: int
    video_filename: str
    job_id: str
    username: str
    transcription_data: List[TranscriptionSegment]
    created_at: datetime


class UploadResponse(BaseModel):
    """
    Response model for the upload endpoint.
    """
    job_id: str
    status: str
    message: str


class ErrorResponse(BaseModel):
    """
    Standard error response model.
    """
    error: str
    detail: Optional[str] = None


class SearchRequest(BaseModel):
    """
    Request model for searching transcriptions.
    """
    query: str = Field(..., min_length=1, description="Search query for full-text search")


class SearchResponse(BaseModel):
    """
    Response model for search results.
    """
    results: List[TranscriptionResponse]
    count: int
