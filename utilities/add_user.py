"""
Utility script to add a new user to config.yaml.
Usage: python add_user.py
"""
import getpass
import yaml
from pathlib import Path
import streamlit_authenticator as stauth


def add_user_to_config(username: str, email: str, name: str, password: str, config_path: str = "../config.yaml"):
    """
    Add a new user to the config.yaml file.
    
    Args:
        username: Username for the new user
        email: Email address for the new user
        name: Display name for the new user
        password: Plain text password (will be hashed)
        config_path: Path to the config.yaml file
        
    Raises:
        FileNotFoundError: If config file does not exist
        yaml.YAMLError: If config file is malformed
        ValueError: If any input field is empty
    """
    # Validate inputs
    if not username or not email or not name or not password:
        raise ValueError("All fields (username, email, name, password) are required")
    
    config_file = Path(__file__).parent / config_path
    
    # Load existing config
    try:
        with open(config_file) as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found at {config_file}")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Config file is malformed: {e}")
    
    # Generate password hash
    hasher = stauth.Hasher([password])
    hashed_password = hasher.generate()[0]
    
    # Add new user
    config['credentials']['usernames'][username] = {
        'email': email,
        'name': name,
        'password': hashed_password
    }
    
    # Save updated config
    with open(config_file, 'w') as file:
        yaml.dump(config, file)
    
    print(f"User '{username}' added successfully to config.yaml")


if __name__ == "__main__":
    username = input("Enter username: ")
    email = input("Enter email: ")
    name = input("Enter display name: ")
    password = getpass.getpass("Enter password: ")
    
    add_user_to_config(username, email, name, password)
