"""Double-click to launch FinPilot without a terminal."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'finpilot'))
from main import main
main()
