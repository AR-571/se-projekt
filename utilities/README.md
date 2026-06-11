# Utilities

This folder contains utility scripts for managing user authentication.

## add_user.py

Add a new user to the config.yaml file.

**Usage:**
```bash
python utilities/add_user.py
```

The script will prompt for username, email, display name, and password interactively (password is not shown in terminal).

**Example:**
```
Enter username: john
Enter email: john@example.com
Enter display name: John Doe
Enter password: ********
User 'john' added successfully to config.yaml
```

This will automatically hash the password and add the user to config.yaml.

## About streamlit-authenticator

The streamlit-authenticator library provides a built-in `Hasher` class for generating bcrypt hashes. These utilities use that class to ensure compatibility with the authentication system.
