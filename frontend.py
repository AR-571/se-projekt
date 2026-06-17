"""
Streamlit frontend for video transcription service.
Provides session-isolated video upload, search, and playback with timestamp seeking.
"""
import time
import requests
from pathlib import Path
from typing import Optional, Dict, List

import streamlit as st
import streamlit.components.v1 as components

# Configuration
API_BASE_URL = "http://localhost:8000"


def initialize_session():
    """
    Initialize session state with a unique session_id if not already set.
    """
    # Initialize all session state variables at once to avoid SessionInfo errors
    session_vars = {
        "access_token": None,
        "current_job_id": None,
        "uploaded_videos": [],
        "search_results": None,
        "active_media_url": None,
        "active_start_time": None,
        "active_file_type": None,
        "authentication_status": None,
        "name": None,
        "username": None,
        "login_completed": False,
        "progress_bar_created": False,
        "initial_data_loaded": False
    }
    
    for key, default_value in session_vars.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def upload_video(file) -> Optional[Dict]:
    """
    Upload a video file to the backend for transcription.
    
    Args:
        file: Uploaded file object
        
    Returns:
        Upload response dict or None if failed
    """
    try:
        files = {"file": (file.name, file, file.type)}
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        response = requests.post(f"{API_BASE_URL}/upload", files=files, headers=headers)
        
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
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        response = requests.get(f"{API_BASE_URL}/transcription/{job_id}", headers=headers)
        
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


def search_transcriptions(query: str) -> Optional[Dict]:
    """
    Search transcriptions using full-text search with user isolation.
    
    Args:
        query: Search query string
        
    Returns:
        Search response dict or None if failed
    """
    try:
        payload = {"query": query}
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        response = requests.post(f"{API_BASE_URL}/search", json=payload, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Search failed: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {str(e)}")
        return None


def get_all_transcriptions() -> Optional[Dict]:
    """
    Retrieve all transcriptions for the current session.
    
    Returns:
        Search response dict or None if failed
    """
    try:
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        response = requests.get(f"{API_BASE_URL}/transcriptions", headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to retrieve transcriptions: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {str(e)}")
        return None


def get_streaming_url(job_id: str) -> Optional[str]:
    """
    Get a secure streaming URL for a job's media by fetching a short-lived token.
    
    Args:
        job_id: Job identifier
        
    Returns:
        URL string ready for streaming, or None if failed
    """
    headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
    try:
        response = requests.get(f"{API_BASE_URL}/streaming-token/{job_id}", headers=headers)
        if response.status_code == 200:
            token = response.json().get("streaming_token")
            return f"{API_BASE_URL}/media/{job_id}?token={token}"
    except requests.exceptions.RequestException:
        pass
    return None


def delete_all_user_data() -> bool:
    """
    Delete all transcriptions and files for the current user.
    """
    try:
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        response = requests.delete(f"{API_BASE_URL}/transcriptions", headers=headers)
        
        if response.status_code == 200:
            return True
        else:
            st.error(f"Failed to delete data: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {str(e)}")
        return False


def main():
    """
    Main Streamlit application.
    """
    # Initialize session BEFORE set_page_config to avoid SessionInfo errors
    initialize_session()
    
    st.set_page_config(
        page_title="Video Transcription Service",
        page_icon="🎥",
        layout="wide"
    )
    
    # Simple manual authentication (bypass streamlit-authenticator cookie issues)
    if st.session_state.get('login_completed') == True:
        # Already logged in, proceed to main app
        pass
    else:
        # Show manual login form
        st.subheader("Login")
        
        with st.form("login_form"):
            username_input = st.text_input("Username")
            password_input = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary")
            
            if submitted:
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/token",
                        data={"username": username_input, "password": password_input}
                    )
                    if response.status_code == 200:
                        token_data = response.json()
                        st.session_state.access_token = token_data.get("access_token")
                        st.session_state.login_completed = True
                        st.session_state.authentication_status = True
                        st.session_state.username = username_input
                        st.session_state.name = username_input
                        st.rerun()
                    else:
                        st.error("Wrong username or password")
                except requests.exceptions.RequestException as e:
                    st.error(f"Failed to connect to backend: {str(e)}")
        
        # Return early if not authenticated
        if st.session_state.get('login_completed') != True:
            return
    
    # Main application
    st.title("🎥 Video Transcription Service")
    st.markdown(f"Logged in as: `{st.session_state.get('name', 'User')}`")
    st.divider()
    
    # Load all historical transcriptions for the user upon first render after login
    if not st.session_state.get("initial_data_loaded"):
        with st.spinner("Loading your historical transcriptions..."):
            results = get_all_transcriptions()
            if results is not None:
                st.session_state.uploaded_videos = results.get("results", [])
            st.session_state.initial_data_loaded = True

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
                    result = upload_video(uploaded_file)
                    
                    if result:
                        st.session_state.current_job_id = result["job_id"]
                        st.success(f"Upload successful! Job ID: {result['job_id']}")
                        st.info("Transcription in progress...")
        
        st.divider()
        
        # Show current upload status
        if st.session_state.current_job_id:
            st.subheader("Current Upload")
            st.text(f"Job ID: {st.session_state.current_job_id}")
            
            # Only create progress bar if not already created
            if not st.session_state.progress_bar_created:
                progress_bar = st.progress(0)
                st.session_state.progress_bar_created = True
            else:
                progress_bar = st.empty()
                progress_bar.progress(st.session_state.get("current_progress", 0))
            
            # Fetch current status
            transcription = get_transcription(st.session_state.current_job_id)
            
            if transcription:
                if transcription.get("status") == "processing":
                    # Update progress bar
                    progress = transcription.get("progress", 0)
                    progress_bar.progress(progress / 100)
                    st.session_state.current_progress = progress / 100
                    
                    # Sleep briefly, then completely rerun the app
                    # This prevents freezing the Streamlit UI thread for minutes!
                    time.sleep(3)
                    st.rerun()
                else:
                    # Transcription completed
                    progress_bar.progress(100)
                    st.success("Transcription completed!")
                    # Insert at the beginning so the newest video shows at the top
                    st.session_state.uploaded_videos.insert(0, transcription)
                    st.session_state.current_job_id = None
                    st.session_state.progress_bar_created = False
                    st.session_state.current_progress = 0
                    progress_bar.empty()
                    st.rerun()
            else:
                # If API fails temporarily, wait and try again
                time.sleep(3)
                st.rerun()
        
        st.divider()
        
        # Show uploaded videos
        if st.session_state.uploaded_videos:
            st.subheader("Your Videos")
            for video in st.session_state.uploaded_videos:
                st.text(f"📹 {video['video_filename']}")
        
        st.divider()
        
        st.subheader("⚙️ Data Management")
        if st.button("🗑️ Delete All My Data", type="secondary", use_container_width=True):
            with st.spinner("Deleting all your data..."):
                if delete_all_user_data():
                    st.session_state.uploaded_videos = []
                    st.session_state.search_results = None
                    st.session_state.active_media_url = None
                    st.session_state.active_start_time = None
                    st.success("All data successfully deleted!")
                    time.sleep(1)
                    st.rerun()
        
        # Logout button
        if st.button("Logout"):
            st.session_state.login_completed = False
            st.session_state.authentication_status = False
            st.session_state.name = None
            st.session_state.username = None
            st.session_state.access_token = None
            st.session_state.uploaded_videos = []
            st.session_state.initial_data_loaded = False
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
                    results = search_transcriptions(search_query)
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
                                
                                # Video/Audio player button with timestamp seeking
                                if st.button(f"▶️ Play at {segment['start']:.2f}s", key=f"play_{result['job_id']}_{idx}_{segment['start']}"):
                                    stream_url = get_streaming_url(result["job_id"])
                                    if stream_url:
                                        file_type = "video" if Path(result["video_filename"]).suffix.lower() in [".mp4", ".mov", ".avi", ".mkv"] else "audio"
                                        st.session_state.active_media_url = stream_url
                                        st.session_state.active_start_time = segment['start']
                                        st.session_state.active_file_type = file_type
                                        st.rerun()
                                    else:
                                        st.error("Failed to retrieve media stream.")
            else:
                st.info("No results found")
    
    with tab2:
        st.header("All Transcriptions")
        
        if st.button("Refresh", type="secondary"):
            with st.spinner("Loading..."):
                results = get_all_transcriptions()
                
                if results is not None:
                    st.session_state.uploaded_videos = results.get("results", [])
                    st.success(f"Loaded {results.get('count', 0)} transcription(s)")
                    st.rerun()
        
        if st.session_state.uploaded_videos:
            for video in st.session_state.uploaded_videos:
                with st.expander(f"📹 {video['video_filename']}"):
                    st.caption(f"Job ID: {video['job_id']}")
                    st.caption(f"Created: {video['created_at']}")
                    
                    # Show all segments
                    for segment in video["transcription_data"]:
                        st.markdown(f"**{segment['start']:.2f}s - {segment['end']:.2f}s**: {segment['text']}")
                    
                    # Video/Audio player
                    stream_url = get_streaming_url(video["job_id"])
                    if stream_url:
                        if Path(video["video_filename"]).suffix.lower() in [".mp4", ".mov", ".avi", ".mkv"]:
                            html_code = f'''
                            <style>
                                body {{ margin: 0; }}
                                .player-wrapper {{
                                    width: 100%; height: 100%; background-color: black;
                                }}
                                .player-wrapper video {{
                                    width: 100%; height: 100%;
                                    object-fit: contain;
                                }}
                            </style>
                            <div class="player-wrapper">
                                <video controls autocomplete="off" src="{stream_url}">Ihr Browser unterstützt dieses Video nicht.</video>
                            </div>
                            '''
                            components.html(html_code, height=600)
                        else:
                            html_code = f'''<audio style="width: 100%;" controls src="{stream_url}">Ihr Browser unterstützt dieses Audio nicht.</audio>'''
                            components.html(html_code, height=80)
                    else:
                        st.warning("Media stream not available.")
        else:
            st.info("No transcriptions yet. Upload a video to get started!")
    
    # Video/Audio player outside of button logic to survive reruns
    if st.session_state.active_media_url and st.session_state.active_start_time is not None:
        st.divider()
        file_type = st.session_state.get("active_file_type", "video")
        st.subheader(f"🎬 {'Video' if file_type == 'video' else 'Audio'} Player")
        
        start_time = st.session_state.active_start_time
        media_url = st.session_state.active_media_url
        
        if file_type == "video":
            html_code = f'''
            <style>
                body {{ margin: 0; }}
                .player-wrapper {{
                    width: 100%; height: 100%; background-color: black;
                }}
                .player-wrapper video {{
                    width: 100%; height: 100%;
                    object-fit: contain;
                }}
            </style>
            <div class="player-wrapper">
                <video id="mediaPlayer" controls autoplay autocomplete="off" src="{media_url}">Ihr Browser unterstützt dieses Video nicht.</video>
            </div>
            <script>
                var player = document.getElementById("mediaPlayer");
                player.addEventListener('loadedmetadata', function() {{
                    player.currentTime = {start_time};
                }});
                if (player.readyState >= 1) {{ player.currentTime = {start_time}; }}
            </script>
            '''
            components.html(html_code, height=600)
        else:
            html_code = f'''
            <audio id="mediaPlayer" style="width: 100%;" controls autoplay src="{media_url}">
                Ihr Browser unterstützt dieses Audio nicht.
            </audio>
            <script>
                var player = document.getElementById("mediaPlayer");
                player.addEventListener('loadedmetadata', function() {{
                    player.currentTime = {start_time};
                }});
                if (player.readyState >= 1) {{ player.currentTime = {start_time}; }}
            </script>
            '''
            components.html(html_code, height=80)
            
        if st.button("Close Player"):
            st.session_state.active_media_url = None
            st.session_state.active_start_time = None
            st.session_state.active_file_type = None
            st.rerun()


if __name__ == "__main__":
    main()
