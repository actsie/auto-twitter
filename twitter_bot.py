#!/usr/bin/env python3
"""
Twitter Auto Bot CLI Wrapper
"""

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from src.main import main

if __name__ == "__main__":
    main()