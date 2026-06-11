"""
Authentication module for Streamlit app using streamlit-authenticator.
"""
import yaml
import streamlit_authenticator as stauth
import streamlit as st
from pathlib import Path


def load_config(config_path: str = "config.yaml") -> dict:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to the config.yaml file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file does not exist
        yaml.YAMLError: If config file is malformed
    """
    # Get absolute path relative to this file
    config_file = Path(__file__).parent / config_path
    try:
        with open(config_file) as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found at {config_file}")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Config file is malformed: {e}")


def initialize_authenticator(config_path: str = "config.yaml") -> stauth.Authenticate:
    """
    Initialize the streamlit-authenticator.
    
    Args:
        config_path: Path to the config.yaml file
        
    Returns:
        Initialized Authenticate object
    """
    config = load_config(config_path)
    
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
        config['preauthorized']
    )
    
    return authenticator


def login(authenticator: stauth.Authenticate) -> bool:
    """
    Display login widget and return authentication status.
    
    This function manages the login process and ensures session state
    is preserved across page reloads via the cookie manager.
    
    Args:
        authenticator: Initialized Authenticate object
        
    Returns:
        True if user is authenticated, False otherwise
    """
    # Display login widget (authenticator handles cookie-based authentication)
    name, authentication_status, username = authenticator.login('Login', 'main')
    
    # Store authentication status in session state
    st.session_state['authentication_status'] = authentication_status
    st.session_state['name'] = name
    st.session_state['username'] = username
    
    # Show error message for failed authentication
    if authentication_status is False:
        st.error('Wrong password')
    
    return authentication_status


def logout(authenticator: stauth.Authenticate) -> bool:
    """
    Display logout button and clear session state.
    
    Args:
        authenticator: Initialized Authenticate object
        
    Returns:
        True if logout was successful
    """
    authenticator.logout('Logout', 'main')
    st.session_state['authentication_status'] = False
    st.session_state['name'] = None
    st.session_state['username'] = None
    st.session_state['login_completed'] = False
    # Clear cached authenticator to force fresh initialization on next login
    if 'authenticator' in st.session_state:
        del st.session_state['authenticator']
    return True
