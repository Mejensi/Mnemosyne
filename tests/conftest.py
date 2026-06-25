from pathlib import Path
import sys

# Repo root on sys.path so tests can `import mnemosyne` (the single-file script).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
