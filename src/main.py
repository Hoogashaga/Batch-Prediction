# src/main.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import GEMINI_API_KEY

def main():
    if GEMINI_API_KEY:
        print("Successfully loaded GEMINI_API_KEY from .env!")
    else:
        print("Failed to load GEMINI_API_KEY. Check your .env file.")

if __name__ == "__main__":
    main()
