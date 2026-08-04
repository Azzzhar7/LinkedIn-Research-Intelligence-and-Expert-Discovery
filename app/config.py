from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
EXPORT_DIR = ROOT / "exports"
DB_PATH = DATA_DIR / "research.db"

for folder in (DATA_DIR, LOG_DIR, EXPORT_DIR):
    folder.mkdir(exist_ok=True)

