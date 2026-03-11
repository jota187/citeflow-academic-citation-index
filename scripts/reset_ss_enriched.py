import sqlite3
import sys
from pathlib import Path

# Allow running as a standalone script without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from citeflow.db import DB_PATH  # noqa: E402


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE citations
        SET ss_enriched = 0
        WHERE ss_enriched = 1 AND (ss_doi IS NULL OR ss_doi = '')
        """
    )
    conn.commit()
    print(f"rows_reset={cur.rowcount}")
    print(f"db={DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
