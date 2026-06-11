"""
Streamlit frontend for video transcription service.
Provides session-isolated video upload, search, and playback with timestamp seeking.
"""
import uuid
import time
import requests
import yaml
import bcrypt
from pathlib import Path
from typing import Optional, Dict, List

import streamlit as st

# Configuration
API_BASE_URL = "http://localhost:8000"


def initialize_session():
    """
    Initialize session state with a unique session_id if not already set.
    """
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.current_job_id = None
        st.session_state.uploaded_videos = []
        st.session_state.search_results = None
        st.session_state.active_video_path = None
        st.session_state.active_start_time = None
    
    # Always initialize authentication state (needed for persistence across reruns)
    if "authentication_status" not in st.session_state:
        st.session_state.authentication_status = None
    if "name" not in st.session_state:
        st.session_state.name = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "login_completed" not in st.session_state:
        st.session_state.login_completed = False


def upload_video(file, session_id: str) -> Optional[Dict]:
    """
    Upload a video file to the backend for transcription.
    
    Args:
        file: Uploaded file object
        session_id: Session identifier for isolation
        
    Returns:
        Upload response dict or None if failed
    """
    try:
        files = {"file": (file.name, file, file.type)}
        params = {"session_id": session_id}
        response = requests.post(f"{API_BASE_URL}/upload", files=files, params=params)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Upload failed: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {str(e)}")
        return None


def get_transcription(job_id: str) -> Optional[Dict]:
    """
    Retrieve a transcription by job ID.
    
    Args:
        job_id: Unique identifier for the transcription job
        
    Returns:
        Transcription data dict or None if not found
    """
    try:
        response = requests.get(f"{API_BASE_URL}/transcription/{job_id}")
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            st.error(f"Failed to retrieve transcription: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {str(e)}")
        return None


def search_transcriptions(query: str, session_id: str) -> Optional[Dict]:
    """
    Search transcriptions using full-text search with session isolation.
    
    Args:
        query: Search query string
        session_id: Session identifier for isolation
        
    Returns:
        Search response dict or None if failed
    """
    try:
        payload = {"query": query, "session_id": session_id}
        response = requests.post(f"{API_BASE_URL}/search", json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Search failed: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {str(e)}")
        return None


def get_all_transcriptions(session_id: str) -> Optional[Dict]:
    """
    Retrieve all transcriptions for the current session.
    
    Args:
        session_id: Session identifier for filtering
        
    Returns:
        Search response dict or None if failed
    """
    try:
        params = {"session_id": session_id}
        response = requests.get(f"{API_BASE_URL}/transcriptions", params=params)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to retrieve transcriptions: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {str(e)}")
        return None


def get_video_path(job_id: str, video_filename: str) -> Path:
    """
    Get the local path to a video file in the workspace.
    
    Args:
        job_id: Job identifier
        video_filename: Name of the video file
        
    Returns:
        Path to the video file
    """
    return Path("workspaces") / job_id / video_filename


def main():
    """
    Main Streamlit application.
    """
    st.set_page_config(
        page_title="Video Transcription Service",
        page_icon="🎥",
        layout="wide"
    )
    
    # Initialize session
    initialize_session()
    
    # Simple manual authentication (bypass streamlit-authenticator cookie issues)
    if st.session_state.get('login_completed') == True:
        # Already logged in, proceed to main app
        pass
    else:
        # Show manual login form
        st.subheader("Login")
        
        # Load credentials from config
        config_file = Path(__file__).parent / "config.yaml"
        with open(config_file) as file:
            config = yaml.safe_load(file)
        
        with st.form("login_form"):
            username_input = st.text_input("Username")
            password_input = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary")
            
            if submitted:
                # Check credentials
                if username_input in config['credentials']['usernames']:
                    stored_hash = config['credentials']['usernames'][username_input]['password']
                    if bcrypt.checkpw(password_input.encode('utf-8'), stored_hash.encode('utf-8')):
                        # Login successful
                        st.session_state.login_completed = True
                        st.session_state.authentication_status = True
                        st.session_state.username = username_input
                        st.session_state.name = config['credentials']['usernames'][username_input]['name']
                        st.rerun()
                    else:
                        st.error("Wrong password")
                else:
                    st.error("Username not found")
        
        # Return early if not authenticated
        if st.session_state.get('login_completed') != True:
            return
    
    # Main application
    st.title("🎥 Video Transcription Service")
    st.markdown(f"Session ID: `{st.session_state.session_id}`")
    st.markdown(f"Logged in as: `{st.session_state.get('name', 'User')}`")
    st.divider()
    
    # Sidebar for upload
    with st.sidebar:
        st.header("📤 Upload Video")
        uploaded_file = st.file_uploader(
            "Choose a video file",
            type=["mp4", "mp3", "wav", "m4a"]
        )
        
        if uploaded_file is not None:
            if st.button("Upload & Transcribe", type="primary"):
                with st.spinner("Uploading video..."):
                    result = upload_video(uploaded_file, st.session_state.session_id)
                    
                    if result:
                        st.session_state.current_job_id = result["job_id"]
                        st.success(f"Upload successful! Job ID: {result['job_id']}")
                        st.info("Transcription in progress...")
        
        st.divider()
        
        # Show current upload status
        if st.session_state.current_job_id:
            st.subheader("Current Upload")
            st.text(f"Job ID: {st.session_state.current_job_id}")
            
            # Poll for transcription completion with progress bar
            progress_bar = st.progress(0)
            for i in range(300):  # Poll for up to 15 minutes (300 * 3 seconds)
                transcription = get_transcription(st.session_state.current_job_id)
                
                if transcription:
                    if transcription.get("status") == "processing":
                        # Update progress bar
                        progress = transcription.get("progress", 0)
                        progress_bar.progress(progress / 100)
                    else:
                        # Transcription completed
                        progress_bar.progress(100)
                        st.success("Transcription completed!")
                        st.session_state.uploaded_videos.append(transcription)
                        st.session_state.current_job_id = None
                        st.rerun()
                
                time.sleep(3)
            
            progress_bar.empty()
            st.warning("Transcription is taking longer than expected. Please check manually.")
        
        st.divider()
        
        # Show uploaded videos
        if st.session_state.uploaded_videos:
            st.subheader("Your Videos")
            for video in st.session_state.uploaded_videos:
                st.text(f"📹 {video['video_filename']}")
        
        st.divider()
        
        # Logout button
        if st.button("Logout"):
            st.session_state.login_completed = False
            st.session_state.authentication_status = False
            st.session_state.name = None
            st.session_state.username = None
            st.rerun()
    
    # Main area
    tab1, tab2 = st.tabs(["🔍 Search", "📋 All Transcriptions"])
    
    with tab1:
        st.header("Search Transcriptions")
        
        with st.form("search_form"):
            search_query = st.text_input("Enter search term", placeholder="Search for words or phrases...")
            submitted = st.form_submit_button("Search", type="primary")
            
            if submitted and search_query:
                with st.spinner("Searching..."):
                    results = search_transcriptions(search_query, st.session_state.session_id)
                    st.session_state.search_results = results
        
        # Display search results from session_state
        if st.session_state.search_results:
            results = st.session_state.search_results
            if results and results["count"] > 0:
                st.success(f"Found {results['count']} result(s)")
                
                for idx, result in enumerate(results["results"]):
                    with st.expander(f"📹 {result['video_filename']}"):
                        st.caption(f"Job ID: {result['job_id']}")
                        st.caption(f"Created: {result['created_at']}")
                        
                        # Show matching segments
                        for segment in result["transcription_data"]:
                            if search_query.lower() in segment["text"].lower():
                                st.markdown(f"**{segment['start']:.2f}s - {segment['end']:.2f}s**: {segment['text']}")
                                
                                # Video player button with timestamp seeking
                                video_path = get_video_path(result["job_id"], result["video_filename"])
                                if video_path.exists():
                                    if st.button(f"▶️ Play at {segment['start']:.2f}s", key=f"play_{result['job_id']}_{idx}_{segment['start']}"):
                                        st.session_state.active_video_path = str(video_path)
                                        st.session_state.active_start_time = int(segment['start'])
                                        st.rerun()
                                else:
                                    st.warning("Video file has been cleaned up from the server.")
            else:
                st.info("No results found")
    
    with tab2:
        st.header("All Transcriptions")
        
        if st.button("Refresh", type="secondary"):
            with st.spinner("Loading..."):
                results = get_all_transcriptions(st.session_state.session_id)
                
                if results and results["count"] > 0:
                    st.session_state.uploaded_videos = results["results"]
                    st.success(f"Loaded {results['count']} transcription(s)")
                    st.rerun()
        
        if st.session_state.uploaded_videos:
            for video in st.session_state.uploaded_videos:
                with st.expander(f"📹 {video['video_filename']}"):
                    st.caption(f"Job ID: {video['job_id']}")
                    st.caption(f"Created: {video['created_at']}")
                    
                    # Show all segments
                    for segment in video["transcription_data"]:
                        st.markdown(f"**{segment['start']:.2f}s - {segment['end']:.2f}s**: {segment['text']}")
                    
                    # Video player
                    video_path = get_video_path(video["job_id"], video["video_filename"])
                    if video_path.exists():
                        st.video(str(video_path))
                    else:
                        st.warning("Video file has been cleaned up from the server.")
        else:
            st.info("No transcriptions yet. Upload a video to get started!")
    
    # Video player outside of button logic to survive reruns
    if st.session_state.active_video_path and st.session_state.active_start_time is not None:
        st.divider()
        st.subheader("🎬 Video Player")
        if Path(st.session_state.active_video_path).exists():
            st.video(st.session_state.active_video_path, start_time=st.session_state.active_start_time)
            if st.button("Close Video Player"):
                st.session_state.active_video_path = None
                st.session_state.active_start_time = None
                st.rerun()
        else:
            st.warning("Video file has been cleaned up from the server.")
            st.session_state.active_video_path = None
            st.session_state.active_start_time = None


if __name__ == "__main__":
    main()
