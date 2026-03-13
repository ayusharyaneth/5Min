#!/usr/bin/env python3
"""
5Min Trading Bot - Auto-loads .env file
"""

# ═══════════════════════════════════════════════════════════
# AUTO-LOAD .ENV FILE (MUST BE FIRST)
# ═══════════════════════════════════════════════════════════

try:
    from dotenv import load_dotenv
    load_dotenv()  # Automatically loads .env file
    print("✓ Loaded .env file")
except ImportError:
    print("⚠️  python-dotenv not installed. Run: pip install python-dotenv")
    # Fallback: try to load manually
    import os
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
        print("✓ Loaded .env (manual)")

# ═══════════════════════════════════════════════════════════
# REST OF YOUR CODE STARTS HERE
# ═══════════════════════════════════════════════════════════

import os
import sys
import time
import json
import logging
import threading
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

# ... rest of your existing main.py code ...
