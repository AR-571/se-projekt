"""
Database module for managing transcription storage with SQLite and FTS5 full-text search.
"""
import aiosqlite
from pathlib import Path
from typing import List, Dict, Optional
import json


class Database:
    """
    Database manager for storing video transcriptions with FTS5 full-text search support.
    """
    
    def __init__(self, db_path: str = "transcriptions.db"):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """
        Establish connection to the database and create tables if they don't exist.
        """
        self._connection = await aiosqlite.connect(self.db_path)
        await self._create_tables()
    
    async def disconnect(self) -> None:
        """
        Close the database connection.
        """
        if self._connection:
            await self._connection.close()
    
    async def _create_tables(self) -> None:
        """
        Create the necessary tables for storing transcriptions and enabling FTS5 search.
        """
        # Main table for storing transcription data
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_filename TEXT NOT NULL,
                job_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                json_data TEXT NOT NULL
            )
        """)
        
        # FTS5 virtual table for full-text search
        await self._connection.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS transcriptions_fts 
            USING fts5(
                video_filename, 
                session_id,
                text_content,
                content='transcriptions',
                content_rowid='id'
            )
        """)
        
        # Triggers to keep FTS table in sync with main table
        await self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS transcriptions_ai 
            AFTER INSERT ON transcriptions BEGIN
                INSERT INTO transcriptions_fts(rowid, video_filename, session_id, text_content)
                VALUES (new.id, new.video_filename, new.session_id, new.json_data);
            END
        """)
        
        await self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS transcriptions_ad 
            AFTER DELETE ON transcriptions BEGIN
                DELETE FROM transcriptions_fts WHERE rowid = old.id;
            END
        """)
        
        await self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS transcriptions_au 
            AFTER UPDATE ON transcriptions BEGIN
                DELETE FROM transcriptions_fts WHERE rowid = old.id;
                INSERT INTO transcriptions_fts(rowid, video_filename, session_id, text_content)
                VALUES (new.id, new.video_filename, new.session_id, new.json_data);
            END
        """)
        
        await self._connection.commit()
    
    async def save_transcription(
        self, 
        video_filename: str, 
        job_id: str,
        session_id: str,
        transcription_data: List[Dict]
    ) -> int:
        """
        Save a transcription to the database.
        
        Args:
            video_filename: Name of the video file
            job_id: Unique identifier for the transcription job
            session_id: Session identifier for isolation
            transcription_data: List of transcription segments with timestamps and text
            
        Returns:
            The ID of the inserted record
        """
        json_data = json.dumps(transcription_data)
        
        cursor = await self._connection.execute(
            """
            INSERT INTO transcriptions (video_filename, job_id, session_id, json_data)
            VALUES (?, ?, ?, ?)
            """,
            (video_filename, job_id, session_id, json_data)
        )
        await self._connection.commit()
        
        return cursor.lastrowid
    
    async def get_transcription(self, job_id: str) -> Optional[Dict]:
        """
        Retrieve a transcription by job ID.
        
        Args:
            job_id: Unique identifier for the transcription job
            
        Returns:
            Dictionary containing transcription data or None if not found
        """
        cursor = await self._connection.execute(
            """
            SELECT id, video_filename, job_id, session_id, json_data, created_at
            FROM transcriptions
            WHERE job_id = ?
            """,
            (job_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                "id": row[0],
                "video_filename": row[1],
                "job_id": row[2],
                "session_id": row[3],
                "transcription_data": json.loads(row[4]),
                "created_at": row[5]
            }
        return None
    
    async def search_transcriptions(self, query: str, session_id: str) -> List[Dict]:
        """
        Search transcriptions using FTS5 full-text search with session isolation.
        
        Args:
            query: Search query string
            session_id: Session identifier for isolation
            
        Returns:
            List of matching transcription records
        """
        cursor = await self._connection.execute(
            """
            SELECT t.id, t.video_filename, t.job_id, t.session_id, t.json_data, t.created_at
            FROM transcriptions t
            JOIN transcriptions_fts fts ON t.id = fts.rowid
            WHERE t.session_id = ? AND transcriptions_fts MATCH ?
            ORDER BY t.created_at DESC
            """,
            (session_id, query)
        )
        rows = await cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row[0],
                "video_filename": row[1],
                "job_id": row[2],
                "session_id": row[3],
                "transcription_data": json.loads(row[4]),
                "created_at": row[5]
            })
        
        return results
    
    async def get_all_transcriptions(self, session_id: Optional[str] = None) -> List[Dict]:
        """
        Retrieve all transcriptions, optionally filtered by session.
        
        Args:
            session_id: Optional session identifier for filtering
            
        Returns:
            List of transcription records
        """
        if session_id:
            cursor = await self._connection.execute(
                """
                SELECT id, video_filename, job_id, session_id, json_data, created_at
                FROM transcriptions
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (session_id,)
            )
        else:
            cursor = await self._connection.execute(
                """
                SELECT id, video_filename, job_id, session_id, json_data, created_at
                FROM transcriptions
                ORDER BY created_at DESC
                """
            )
        rows = await cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row[0],
                "video_filename": row[1],
                "job_id": row[2],
                "session_id": row[3],
                "transcription_data": json.loads(row[4]),
                "created_at": row[5]
            })
        
        return results
