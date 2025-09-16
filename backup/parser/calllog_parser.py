from ..models import Backup
from ..serializers import CallLogParserSerializer
from datetime import datetime, timezone as dt_timezone
import sqlite3
import tempfile
import re
from typing import Dict, Iterable, List, Optional
from ..utils import minio_client, normalize_phone, parse_datetime_flexible, pick_first

BUCKET_NAME = "backups"

CALLLOG_PHONE_KEYS = {"phone_number", "number", "mobile", "tel", "msisdn"}
CALLLOG_TYPE_KEYS = {"call_type", "type", "direction"}
CALLLOG_DATE_KEYS = {"call_date", "date", "timestamp", "time", "created_at"}
CALLLOG_DURATION_KEYS = {"duration_seconds", "duration", "call_duration"}




def _detect_calllog_table(columns: set) -> bool:
    has_phone = bool(columns & CALLLOG_PHONE_KEYS)
    has_date = bool(columns & CALLLOG_DATE_KEYS)
    has_type_or_duration = bool(columns & (CALLLOG_TYPE_KEYS | CALLLOG_DURATION_KEYS))
    return has_phone and has_date and has_type_or_duration


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
    if dt is None:
        return None

    dur_raw = pick_first(row, CALLLOG_DURATION_KEYS)
    try:
        duration_seconds = int(dur_raw) if dur_raw is not None and str(dur_raw).isdigit() else 0
    except Exception:
        duration_seconds = 0

    return {
        "phone_number": phone,
        "call_type": _map_call_type(pick_first(row, CALLLOG_TYPE_KEYS)),
        "call_date": dt,
        "duration_seconds": duration_seconds
    }


def scan_and_extract_calllogs_minio(backup: Backup) -> List[Dict]:
    prefix = f"{backup.id}/databases/"
    calls: List[Dict] = []
    seen_calls = set()

    objects = minio_client.list_objects(BUCKET_NAME, prefix=prefix, recursive=True)

    for obj in objects:
        if not obj.object_name.lower().endswith((".db", ".sqlite")):
            continue

        try:
            response = minio_client.get_object(BUCKET_NAME, obj.object_name)
            file_bytes = response.read()
            response.close()
            response.release_conn()
        except Exception:
            continue

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            tmp_file.write(file_bytes)
            tmp_file_path = tmp_file.name

        try:
            conn = sqlite3.connect(tmp_file_path, check_same_thread=False)
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
            except Exception:
                tables = []

            for (table,) in tables:
                try:
                    cursor.execute(f'SELECT * FROM "{table}" LIMIT 1000')
                    if cursor.description is None:
                        continue
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
                    key = (data["phone_number"], ts, data["call_type"], data["duration_seconds"])
                    if key in seen_calls:
                        continue
                    seen_calls.add(key)
                    calls.append(data)

        finally:
            try:
                conn.close()
            except:
                pass

    return calls


def store_calllogs(backup: Backup, calls: List[Dict]) -> int:
    serializer = CallLogParserSerializer(data=calls, many=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(backup=backup)
    return len(serializer.data)
