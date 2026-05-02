import sys
import os

# Ensure the repo root is on the path so `from gads.x import y` works
sys.path.insert(0, os.path.dirname(__file__))

from gads.main_dashboard import run_dashboard

run_dashboard()
