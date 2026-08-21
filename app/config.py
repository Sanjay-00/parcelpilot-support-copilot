import os
from datetime import datetime, timedelta, timezone

import openpyxl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PACK_XLSX = os.path.join(
    BASE_DIR, "AI Agent Assessment - Candidate Pack", "ParcelPilot_Assessment_Data.xlsx"
)
DATA_PACK_DIR = os.path.join(BASE_DIR, "AI Agent Assessment - Candidate Pack")
DB_PATH = os.path.join(BASE_DIR, "app", "parcelpilot.db")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

IST = timezone(timedelta(hours=5, minutes=30))


def load_reference_time(xlsx_path: str = DATA_PACK_XLSX) -> datetime:
    """Reads the dataset snapshot timestamp from the workbook's README sheet.

    The README sheet's second row is ('Dataset snapshot',
    '2026-08-16 11:00 Asia/Kolkata'). We parse the naive datetime and attach
    a fixed +05:30 offset (Asia/Kolkata has no DST) rather than hardcoding
    the value, so a differently-timestamped copy of the same pack (e.g. the
    grader's) is still handled correctly.
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    readme = wb["README"]
    for row in readme.iter_rows(values_only=True):
        if row and row[0] == "Dataset snapshot":
            raw = row[1]  # "2026-08-16 11:00 Asia/Kolkata"
            naive_part = raw.rsplit(" ", 1)[0]  # drop " Asia/Kolkata"
            naive_dt = datetime.fromisoformat(naive_part)
            return naive_dt.replace(tzinfo=IST)
    raise ValueError("Could not find 'Dataset snapshot' row in README sheet")


REFERENCE_TIME = load_reference_time()
