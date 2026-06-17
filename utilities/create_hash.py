"""
Utility script to securely generate a bcrypt hash for a given password.
"""
import bcrypt
import getpass
import sys

def create_bcrypt_hash():
    """
    Securely prompts for a password and prints its bcrypt hash.
    """
    try:
        password = getpass.getpass("Enter password to hash: ")
        if not password:
            print("\nError: Password cannot be empty.", file=sys.stderr)
            sys.exit(1)

        password_bytes = password.encode('utf-8')
        hashed_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt())

        print("\n✅ BCrypt Hash generated successfully.")
        print("Copy the following line into your .env file:\n")
        print(f'ADMIN_PASSWORD_HASH="{hashed_password.decode("utf-8")}"')

    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    create_bcrypt_hash()