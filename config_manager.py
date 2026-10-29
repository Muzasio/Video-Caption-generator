#!/usr/bin/env python3
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

def load_config():
    """Load config.json once. Returns dict. Exits if missing or invalid."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"config.json not found at {CONFIG_PATH}")
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print("✓ Loaded configuration from config.json")
        return config
    except Exception as e:
        raise RuntimeError(f"Error reading config.json: {e}")

# Load once at module import
CONFIG = load_config()