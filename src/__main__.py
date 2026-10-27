import sys
from pathlib import Path
from src.gui.app import run

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    # The project folder is added so names like "src.gui.app" can be found.
    sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == "__main__":
    run()
