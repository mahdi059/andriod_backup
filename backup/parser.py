from pathlib import Path
import mimetypes
from django.utils import timezone
from django.utils.timezone import make_aware, get_default_timezone
from .models import Backup, App
from datetime import datetime
import sqlite3
import json
import zlib
import apkutils2
import re
from typing import Dict, Iterable, List, Optional
from .serializers import MessageParserSerializer, MediaParserSerializer, ContactParserSerializer, CallLogParserSerializer
from django.core.files.base import ContentFile
from django.utils import timezone
from typing import Optional
from datetime import timezone as dt_timezone



INVALID_CHARS = r'[<>:"/\\|?*]'

def sanitize_and_truncate_filename(file_path: Path, max_length: int = 100) -> str:

    safe_name = re.sub(INVALID_CHARS, "_", file_path.stem)
    ext = file_path.suffix
    allowed_length = max_length - len(ext)
    
    if len(safe_name) > allowed_length:
        safe_name = safe_name[:allowed_length]
    return safe_name + ext



DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}

def parse_media_type(media_dir: Path, backup_instance: Backup, media_type_filter: str) -> int:
    parsed_count = 0
    
    if not media_dir.exists():
        raise ValueError(f"Media directory not found: {media_dir}")

    for file_path in media_dir.rglob("*"):
        if not file_path.is_file():
            continue

        try:
            mime_type, _ = mimetypes.guess_type(file_path.name)
            mime_type = mime_type or 'application/octet-stream'

            if media_type_filter == "photo" and not mime_type.startswith("image/"):
                continue
            if media_type_filter == "video" and not mime_type.startswith("video/"):
                continue
            if media_type_filter == "audio" and not mime_type.startswith("audio/"):
                continue
            if media_type_filter == "document" and file_path.suffix.lower() not in DOCUMENT_EXTENSIONS:
                continue

            with open(file_path, "rb") as f:
                content = f.read()

            safe_name = sanitize_and_truncate_filename(file_path)
            django_file = ContentFile(content, name=safe_name)

            serializer = MediaParserSerializer(
                data={
                    "backup": backup_instance.id,
                    "file": django_file,
                    "file_name": safe_name,
                    "media_type": media_type_filter,
                    "mime_type": mime_type,
                    "size_bytes": file_path.stat().st_size,
                    "added_at": timezone.now()
                }
            )

            if serializer.is_valid():
                serializer.save()
                parsed_count += 1
            else:
                raise ValueError(f"Validation failed for {file_path}: {serializer.errors}")

        except Exception as e:
            raise  

    return parsed_count



def convert_timestamp(ts):
    try:
        ts_int = int(ts)
        if ts_int > 1e12: 
            ts_int = ts_int // 1000
        dt = datetime.utcfromtimestamp(ts_int)
        dt_aware = make_aware(dt, timezone=get_default_timezone())
        return dt_aware
    except Exception:
        return None


def parse_and_save_sms(file_path: Path, backup_instance: Backup):
    with open(file_path, "rb") as f:
        compressed_data = f.read()

    decompressed_data = zlib.decompress(compressed_data)
    json_text = decompressed_data.decode("utf-8", errors="ignore")

    try:
        sms_list = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return 0

    count = 0
    for sms in sms_list:
        try:
            if sms.get("type") == "1":  
                sender = sms.get("address")  
                receiver = None              
            else:
                sender = None               
                receiver = sms.get("address")
            msg_type = "sms" if sms.get("type") == "1" else "mms"

            serializer = MessageParserSerializer(
                data={
                    'backup' : backup_instance.id,
                    'sender':sender,
                    'receiver' : receiver,
                    'content' : sms.get("body"),
                    'sent_at' : convert_timestamp(sms.get("date_sent")),
                    'received_at' : convert_timestamp(sms.get("date")),
                    'status' : int(sms.get("status") or 0),
                    'message_type' : msg_type,
            })
            
            if serializer.is_valid():
                serializer.save()
                count += 1
        except Exception as e:
            print(f"Error saving SMS: {e}")

    return count


def parse_apks_from_dir(others_dir, backup_instance):
 
    apk_files = [f for f in others_dir.iterdir() if f.is_file() and f.suffix.lower() == ".apk"]
    count = 0

    for apk_path in apk_files:
        try:
            with open(apk_path, "rb") as f:
                apk_binary = f.read()

            apk_info = apkutils2.APK(str(apk_path))
            manifest = apk_info.get_manifest()

            package_name = manifest.get("package", "")
            app_name = apk_info.get_label() if hasattr(apk_info, 'get_label') else ""
            version_code = manifest.get("android:versionCode", "")
            version_name = manifest.get("android:versionName", "")
            permissions = []
            uses_permissions = manifest.get("uses-permission", [])
            if isinstance(uses_permissions, dict):

                permissions.append(uses_permissions.get("android:name", ""))
            elif isinstance(uses_permissions, list):
                for perm in uses_permissions:
                    permissions.append(perm.get("android:name", ""))

            App.objects.create(
                backup=backup_instance,
                package_name=package_name,
                app_name=app_name,
                version_code=version_code,
                version_name=version_name,
                apk_file=apk_binary,
                apk_file_name=apk_path.name,
                installed_at=None,
                permissions=permissions,
                created_at=timezone.now(),
            )

            count += 1
        except Exception as e:
            print(f"Error parsing APK {apk_path.name}: {e}")

    return count



CONTACT_NAME_KEYS = {"name", "display_name", "full_name", "given_name", "first_name"}
CONTACT_SURNAME_KEYS = {"family_name", "last_name", "surname"}
CONTACT_PHONE_KEYS = {"phone_number", "number", "mobile", "tel", "msisdn"}

CALLLOG_PHONE_KEYS = {"phone_number", "number", "mobile", "tel", "msisdn"}
CALLLOG_TYPE_KEYS = {"call_type", "type", "direction"}
CALLLOG_DATE_KEYS = {"call_date", "date", "timestamp", "time", "created_at"}
CALLLOG_DURATION_KEYS = {"duration_seconds", "duration", "call_duration"}

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

def _detect_calllog_table(columns: set) -> bool:
    return (columns & CALLLOG_PHONE_KEYS) and (
        columns & CALLLOG_DATE_KEYS or columns & CALLLOG_TYPE_KEYS or columns & CALLLOG_DURATION_KEYS
    )

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

def store_contacts(backup: "Backup", contacts: List[Dict]) -> int:
    serializer = ContactParserSerializer(data=contacts, many=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(backup=backup)
    return len(serializer.data)

def store_calllogs(backup: "Backup", calls: List[Dict]) -> int:
    serializer = CallLogParserSerializer(data=calls, many=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(backup=backup)
    return len(serializer.data)
