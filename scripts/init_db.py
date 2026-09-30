from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalog_db import DEFAULT_DB_PATH, initialize_database  # noqa: E402


if __name__ == "__main__":
    path = initialize_database(DEFAULT_DB_PATH)
    print(f"Initialized {path}")
