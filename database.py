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
                username TEXT NOT NULL,
                transcription_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                json_data TEXT NOT NULL
            )
        """)
        
        # --- Schema Migration ---
        # 1. Add transcription_text column to main table if it doesn't exist
        cursor = await self._connection.execute("PRAGMA table_info(transcriptions)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'transcription_text' not in columns:
            await self._connection.execute("ALTER TABLE transcriptions ADD COLUMN transcription_text TEXT DEFAULT '' NOT NULL")

        # 2. Check for old FTS5 table schema (with 'text_content' or indexing json_data) and drop if necessary
        cursor = await self._connection.execute("PRAGMA table_info(transcriptions_fts)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'text_content' in columns:
            await self._connection.execute("DROP TABLE IF EXISTS transcriptions_fts")

        # Alte Trigger immer löschen, um sie frisch anzulegen
        await self._connection.execute("DROP TRIGGER IF EXISTS transcriptions_ai")
        await self._connection.execute("DROP TRIGGER IF EXISTS transcriptions_ad")
        await self._connection.execute("DROP TRIGGER IF EXISTS transcriptions_au")

        # FTS5 virtual table for full-text search
        await self._connection.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS transcriptions_fts 
            USING fts5(
                video_filename, 
                username,
                transcription_text,
                content='transcriptions',
                content_rowid='id'
            )
        """)
        
        # Falls wir die alte Tabelle gelöscht haben, Index aus der Haupttabelle neu aufbauen
        if 'text_content' in columns:
            await self._connection.execute("INSERT INTO transcriptions_fts(transcriptions_fts) VALUES('rebuild')")

        # Triggers to keep FTS table in sync with main table
        await self._connection.execute("""
            CREATE TRIGGER transcriptions_ai 
            AFTER INSERT ON transcriptions BEGIN
                INSERT INTO transcriptions_fts(rowid, video_filename, username, transcription_text)
                VALUES (new.id, new.video_filename, new.username, new.transcription_text);
            END
        """)
        
        await self._connection.execute("""
            CREATE TRIGGER transcriptions_ad 
            AFTER DELETE ON transcriptions BEGIN
                INSERT INTO transcriptions_fts(transcriptions_fts, rowid, video_filename, username, transcription_text)
                VALUES ('delete', old.id, old.video_filename, old.username, old.transcription_text);
            END
        """)
        
        await self._connection.execute("""
            CREATE TRIGGER transcriptions_au 
            AFTER UPDATE ON transcriptions BEGIN
                INSERT INTO transcriptions_fts(transcriptions_fts, rowid, video_filename, username, transcription_text)
                VALUES ('delete', old.id, old.video_filename, old.username, old.transcription_text);
                INSERT INTO transcriptions_fts(rowid, video_filename, username, transcription_text)
                VALUES (new.id, new.video_filename, new.username, new.transcription_text);
            END
        """)
        
        await self._connection.commit()
    
    async def save_transcription(
        self, 
        video_filename: str, 
        job_id: str,
        username: str,
        transcription_text: str,
        transcription_data: List[Dict]
    ) -> int:
        """
        Save a transcription to the database.
        
        Args:
            video_filename: Name of the video file
            job_id: Unique identifier for the transcription job
            username: Authenticated username for isolation
            transcription_text: The full concatenated text of the transcription
            transcription_data: List of transcription segments with timestamps and text
            
        Returns:
            The ID of the inserted record
        """
        json_data = json.dumps(transcription_data)
        
        cursor = await self._connection.execute(
            """
            INSERT INTO transcriptions (video_filename, job_id, username, transcription_text, json_data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (video_filename, job_id, username, transcription_text, json_data)
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
            SELECT id, video_filename, job_id, username, json_data, created_at, transcription_text
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
                "username": row[3],
                "transcription_data": json.loads(row[4]), # json_data
                "created_at": row[5],
                "transcription_text": row[6]
            }
        return None
    
    async def search_transcriptions(
        self, 
        query: str, 
        username: str,
        limit: int,
        offset: int
    ) -> List[Dict]:
        """
        Search transcriptions using FTS5 full-text search with user isolation.
        
        Args:
            query: Search query string
            username: User identifier for isolation
            limit: Max number of records to return
            offset: Number of records to skip for pagination
            
        Returns:
            List of matching transcription records
        """
        # Sanitize query for FTS5 to prevent syntax errors and crashes
        # Replace double quotes with escaped double quotes and wrap in quotes
        safe_query = query.replace('"', '""')
        safe_query = f'"{safe_query}"'
        
        cursor = await self._connection.execute(
            """
            SELECT t.id, t.video_filename, t.job_id, t.username, t.json_data, t.created_at
            FROM transcriptions t
            JOIN transcriptions_fts fts ON t.id = fts.rowid
            WHERE t.username = ? AND transcriptions_fts MATCH ?
            ORDER BY rank
            LIMIT ? OFFSET ?
            """,
            (username, safe_query, limit, offset)
        )
        rows = await cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row[0],
                "video_filename": row[1],
                "job_id": row[2],
                "username": row[3],
                "transcription_data": json.loads(row[4]),
                "created_at": row[5]
            })
        
        return results
    
    async def get_all_transcriptions(
        self, 
        username: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """
        Retrieve all transcriptions, optionally filtered by username.
        
        Args:
            username: Optional user identifier for filtering
            limit: Max number of records to return
            offset: Number of records to skip for pagination

        Returns:
            List of transcription records
        """
        if username:
            cursor = await self._connection.execute(
                """
                SELECT id, video_filename, job_id, username, json_data, created_at
                FROM transcriptions
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (username, limit, offset)
            )
        else:
            cursor = await self._connection.execute(
                """
                SELECT id, video_filename, job_id, username, json_data, created_at
                FROM transcriptions
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """, (limit, offset)
            )
        rows = await cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "id": row[0],
                "video_filename": row[1],
                "job_id": row[2],
                "username": row[3],
                "transcription_data": json.loads(row[4]),
                "created_at": row[5]
            })
        
        return results
