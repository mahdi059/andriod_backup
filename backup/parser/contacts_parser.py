from pathlib import Path
from ..models import Backup
from datetime import datetime
import sqlite3
import re
from typing import Dict, Iterable, List, Optional
from ..serializers import  ContactParserSerializer
from typing import Optional
from datetime import timezone as dt_timezone




CONTACT_NAME_KEYS = {"name", "display_name", "full_name", "given_name", "first_name"}
CONTACT_SURNAME_KEYS = {"family_name", "last_name", "surname"}
CONTACT_PHONE_KEYS = {"phone_number", "number", "mobile", "tel", "msisdn"}

EMAIL_KEYS = {"email", "e_mail", "mail"}
GROUP_KEYS = {"group", "group_name", "label", "category"}
ADDRESS_KEYS = {"address", "addr", "street", "city", "location"}



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


def _detect_contact_table(columns: set) -> bool:
    return (columns & CONTACT_PHONE_KEYS) and (columns & (CONTACT_NAME_KEYS | CONTACT_SURNAME_KEYS))


def _extract_contact_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    phone = pick_first(row, CONTACT_PHONE_KEYS)
    if not phone:
        return None
    phone = normalize_phone(phone)
    created_at_raw = pick_first(row, {"created_at", "date_added"})
    created_at = parse_datetime_flexible(created_at_raw)
    return {
        "name": pick_first(row, CONTACT_NAME_KEYS) or "",
        "phone_number": phone,
        "email": pick_first(row, EMAIL_KEYS),
        "group": pick_first(row, GROUP_KEYS),
        "address": pick_first(row, ADDRESS_KEYS),
        "created_at": created_at,
    }


def scan_and_extract_contacts(backup: "Backup", db_dir: Path) -> List[Dict]:
    contacts = []
    seen_contacts = set()
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
                if not rows or not _detect_contact_table(set(col_names)):
                    continue
                for row in rows:
                    data = _extract_contact_row(row)
                    if not data:
                        continue
                    data["backup"] = backup.id
                    key = (data["name"], data["phone_number"])
                    if key in seen_contacts:
                        continue
                    seen_contacts.add(key)
                    contacts.append(data)
        except sqlite3.DatabaseError:
            continue
        finally:
            try:
                conn.close()
            except:
                pass
    return contacts


def store_contacts(backup: "Backup", contacts: List[Dict]) -> int:
    serializer = ContactParserSerializer(data=contacts, many=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(backup=backup)
    return len(serializer.data)


