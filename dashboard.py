#!/usr/bin/env python3
"""
Simple launcher for the Twitter Bot Dashboard
"""

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from src.web_dashboard import run_dashboard

if __name__ == "__main__":
    run_dashboard()