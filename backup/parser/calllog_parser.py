from pathlib import Path
from ..models import Backup
from datetime import datetime
import sqlite3
import re
from typing import Dict, Iterable, List, Optional
from ..serializers import CallLogParserSerializer
from typing import Optional
from datetime import timezone as dt_timezone


CALLLOG_PHONE_KEYS = {"phone_number", "number", "mobile", "tel", "msisdn"}
CALLLOG_TYPE_KEYS = {"call_type", "type", "direction"}
CALLLOG_DATE_KEYS = {"call_date", "date", "timestamp", "time", "created_at"}
CALLLOG_DURATION_KEYS = {"duration_seconds", "duration", "call_duration"}


def normalize_phone(value: str) -> str:
    if not value:
        return ""
    s = re.sub(r"[\s\-\(\)]", "", str(value).strip())
    if s.startswith("0098"):
        return "+98" + s[4:]
    if s.startswith("98") and not s.startswith("+"):
        return "+98" + s[2:]
    return s


def is_sqlite_file(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size < 16:
            return False
        with path.open("rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False



def _from_epoch_like(num: float) -> Optional[datetime]:
    try:
        length = len(str(int(num)))
        if length <= 10:
            return datetime.fromtimestamp(num, tz=dt_timezone.utc)
        if length <= 13:
            return datetime.fromtimestamp(num / 1_000, tz=dt_timezone.utc)
        if length <= 16:
            return datetime.fromtimestamp(num / 1_000_000, tz=dt_timezone.utc)
        if length <= 19:
            return datetime.fromtimestamp(num / 1_000_000_000, tz=dt_timezone.utc)
    except Exception:
        return None
    return None



def parse_datetime_flexible(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _from_epoch_like(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt
    except Exception:
        pass
    if s.isdigit():
        try:
            return _from_epoch_like(int(float(s)))
        except Exception:
            return None
    return None


def pick_first(row: Dict[str, object], keys: Iterable[str]) -> Optional[object]:
    for k in keys:
        if row.get(k):
            return row.get(k)
    return None


def _detect_calllog_table(columns: set) -> bool:
    return (columns & CALLLOG_PHONE_KEYS) and (
        columns & CALLLOG_DATE_KEYS or columns & CALLLOG_TYPE_KEYS or columns & CALLLOG_DURATION_KEYS
    )


def _map_call_type(raw) -> str:
    if not raw:
        return "incoming"
    s = str(raw).lower()
    if s.isdigit():
        return {"1": "incoming", "2": "outgoing", "3": "missed"}.get(s, "incoming")
    if "out" in s:
        return "outgoing"
    if "miss" in s:
        return "missed"
    return "incoming"


def _extract_calllog_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    phone = pick_first(row, CALLLOG_PHONE_KEYS)
    if not phone:
        return None
    phone = normalize_phone(phone)
    dt_raw = pick_first(row, CALLLOG_DATE_KEYS)
    dt = parse_datetime_flexible(dt_raw)
    return {
        "phone_number": phone,
        "call_type": _map_call_type(pick_first(row, CALLLOG_TYPE_KEYS)),
        "call_date": dt,
        "duration_seconds": int(pick_first(row, CALLLOG_DURATION_KEYS) or 0)
    }


def scan_and_extract_calllogs(backup: "Backup", db_dir: Path) -> List[Dict]:
    calls = []
    seen_calls = set()
    for db_file in db_dir.rglob("*"):
        if not db_file.is_file() or not is_sqlite_file(db_file):
            continue
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for (table,) in cursor.fetchall():
                try:
                    cursor.execute(f'SELECT * FROM "{table}" LIMIT 200')
                    col_names = [d[0].lower() for d in cursor.description]
                    rows = [dict(zip(col_names, r)) for r in cursor.fetchall()]
                except Exception:
                    continue
                if not rows or not _detect_calllog_table(set(col_names)):
                    continue
                for row in rows:
                    data = _extract_calllog_row(row)
                    if not data:
                        continue
                    data["backup"] = backup.id
                    ts = int(data["call_date"].timestamp()) if data["call_date"] else 0
                    key = (data["phone_number"], ts, data["call_type"])
                    if key in seen_calls:
                        continue
                    seen_calls.add(key)
                    calls.append(data)
        except sqlite3.DatabaseError:
            continue
        finally:
            try:
                conn.close()
            except:
                pass
    return calls


def store_calllogs(backup: "Backup", calls: List[Dict]) -> int:
    serializer = CallLogParserSerializer(data=calls, many=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(backup=backup)
    return len(serializer.data)