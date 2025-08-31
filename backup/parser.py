from pathlib import Path
import mimetypes
from django.utils import timezone
from django.utils.timezone import make_aware, get_default_timezone
from .models import MediaFile, Backup, Message, App, RawBackupFile, Contact, Note, CallLog, ChatMessage
from datetime import datetime
import sqlite3
import json
import zlib
import apkutils2
from django.core.files import File
import re
from typing import Dict, Iterable, List, Optional, Tuple
from .serializers import MessageParserSerializer


DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}

def parse_media_type(media_dir: Path, backup_instance: Backup, media_type_filter: str) -> int:
    if not media_dir.exists():
        raise ValueError(f"Media directory not found: {media_dir}")

    parsed_count = 0

    for file_path in media_dir.rglob("*"):
        if not file_path.is_file():
            continue

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
            django_file = File(f, name=file_path.name)
            MediaFile.objects.create(
                backup=backup_instance,
                file=django_file,
                file_name=file_path.name,
                media_type=media_type_filter,
                mime_type=mime_type,
                size_bytes=file_path.stat().st_size,
                added_at=timezone.now()
            )

        parsed_count += 1

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




SQLITE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
REALM_EXTENSIONS = {".realm"}


def is_sqlite_file(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            sig = f.read(16)
        return sig.startswith(b"SQLite format 3\x00")
    except Exception:
        return False


def detect_db_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in SQLITE_EXTENSIONS:
        return "sqlite"
    if ext in REALM_EXTENSIONS:
        return "realm"
    if is_sqlite_file(file_path):
        return "sqlite"
    return "unknown"


def scan_and_store_databases(db_dir: Path, backup) -> dict:
    if not db_dir.exists():
        raise FileNotFoundError(f"Databases folder not found: {db_dir}")

    counts = {"sqlite": 0, "realm": 0, "unknown": 0, "skipped_empty": 0}

    for file_path in db_dir.rglob("*"):
        if not file_path.is_file():
            continue

        try:
            size = file_path.stat().st_size
            if size == 0:
                counts["skipped_empty"] += 1
                continue

            db_type = detect_db_type(file_path)
            mime_type, _ = mimetypes.guess_type(file_path.name)

            RawBackupFile.objects.create(
                backup=backup,
                relative_path=str(file_path.relative_to(db_dir)),
                file_data=file_path.read_bytes(),
                size_bytes=size,
                file_type=db_type or mime_type or "unknown",
            )

            counts[db_type] = counts.get(db_type, 0) + 1

        except Exception as e:
            print(f"[DB-SCAN] Error on {file_path}: {e}")

    return counts



def parse_sqlite_db(file_path: Path, backup):
    data_summary = {"contacts": 0, "notes": 0, "call_logs": 0}

    try:
        conn = sqlite3.connect(file_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            cursor.execute(f'PRAGMA table_info("{table}")')
            columns = [row[1].lower() for row in cursor.fetchall()]

            cursor.execute(f'SELECT * FROM "{table}"')
            col_names = [desc[0].lower() for desc in cursor.description]

            rows = cursor.fetchall()
            for row in rows:
                row_dict = dict(zip(col_names, row))

                # Contacts
                if "name" in columns and "phone_number" in columns:
                    Contact.objects.create(
                        backup=backup,
                        name=row_dict.get("name", ""),
                        phone_number=row_dict.get("phone_number", ""),
                        email=row_dict.get("email"),
                        group=row_dict.get("group"),
                        address=row_dict.get("address"),
                        created_at=_parse_datetime(row_dict.get("created_at"))
                    )
                    data_summary["contacts"] += 1

                # Notes
                elif "content" in columns or "title" in columns:
                    Note.objects.create(
                        backup=backup,
                        title=row_dict.get("title"),
                        content=row_dict.get("content", ""),
                        created_at=_parse_datetime(row_dict.get("created_at"))
                    )
                    data_summary["notes"] += 1

                # CallLogs
                elif "phone_number" in columns and "call_type" in columns and "call_date" in columns:
                    CallLog.objects.create(
                        backup=backup,
                        phone_number=row_dict.get("phone_number", ""),
                        call_type=row_dict.get("call_type", "incoming"),
                        call_date=_parse_datetime(row_dict.get("call_date")),
                        duration_seconds=row_dict.get("duration_seconds", 0)
                    )
                    data_summary["call_logs"] += 1

        conn.close()

    except sqlite3.DatabaseError:
        return {"error": f"unable to read database: {file_path.name}"}

    return data_summary


def _parse_datetime(value):
    if value is None:
        return timezone.now()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return timezone.now()



def parse_json_file(file_path: Path, backup):
    summary = {"contacts": 0, "notes": 0, "call_logs": 0, "chat_messages": 0}
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"unable to read JSON: {file_path.name}, {str(e)}"}

    if isinstance(data, list):
        for item in data:
            if "phone_number" in item and "call_type" in item: 
                CallLog.objects.create(
                    backup=backup,
                    phone_number=item.get("phone_number", ""),
                    call_type=item.get("call_type", "incoming"),
                    call_date=item.get("call_date") or timezone.now(),
                    duration_seconds=item.get("duration_seconds", 0)
                )
                summary["call_logs"] += 1

            elif "phone_number" in item and "name" in item: 
                Contact.objects.create(
                    backup=backup,
                    name=item.get("name", ""),
                    phone_number=item.get("phone_number", ""),
                    email=item.get("email"),
                    group=item.get("group"),
                    address=item.get("address"),
                    created_at=item.get("created_at") or timezone.now()
                )
                summary["contacts"] += 1

            elif "message" in item and "sender" in item:  
                ChatMessage.objects.create(
                    backup=backup,
                    chat_id=item.get("chat_id"),
                    sender=item.get("sender"),
                    message=item.get("message"),
                    sent_at=item.get("sent_at") or timezone.now()
                )
                summary["chat_messages"] += 1

            elif "content" in item:
                Note.objects.create(
                    backup=backup,
                    title=item.get("title"),
                    content=item.get("content", ""),
                    created_at=item.get("created_at") or timezone.now()
                )
                summary["notes"] += 1

    elif isinstance(data, dict):
        contacts = data.get("contacts", [])
        for c in contacts:
            Contact.objects.create(
                backup=backup,
                name=c.get("name", ""),
                phone_number=c.get("phone_number", ""),
                email=c.get("email"),
                group=c.get("group"),
                address=c.get("address"),
                created_at=c.get("created_at") or timezone.now()
            )
            summary["contacts"] += 1

        notes = data.get("notes", [])
        for n in notes:
            Note.objects.create(
                backup=backup,
                title=n.get("title"),
                content=n.get("content", ""),
                created_at=n.get("created_at") or timezone.now()
            )
            summary["notes"] += 1

        call_logs = data.get("call_logs", [])
        for cl in call_logs:
            CallLog.objects.create(
                backup=backup,
                phone_number=cl.get("phone_number", ""),
                call_type=cl.get("call_type", "incoming"),
                call_date=cl.get("call_date") or timezone.now(),
                duration_seconds=cl.get("duration_seconds", 0)
            )
            summary["call_logs"] += 1

        chats = data.get("chat_messages", [])
        for ch in chats:
            ChatMessage.objects.create(
                backup=backup,
                chat_id=ch.get("chat_id"),
                sender=ch.get("sender"),
                message=ch.get("message"),
                sent_at=ch.get("sent_at") or timezone.now()
            )
            summary["chat_messages"] += 1

    else:
        return {"error": f"Unsupported JSON structure in {file_path.name}"}

    return summary



def parse_json_folder(json_folder: Path, backup):
    result = {"message": "JSON parsing complete", "details": []}
    
    for file_path in json_folder.iterdir():
        if file_path.suffix.lower() != ".json":
            continue
        file_info = {"file": file_path.name}
        stats = parse_json_file(file_path, backup)
        file_info.update(stats)
        result["details"].append(file_info)
    
    return result



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

MOBILE_REGEX = re.compile(r"^(?:\+98|0)?9\d{9}$")
GENERIC_PHONE_REGEX = re.compile(r"^\+?\d[\d\-\s\(\)]{4,}$")


def is_sqlite_file(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size < 16:
            return False
        with path.open("rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False



def normalize_phone(value: Optional[str]) -> str:
    if not value: return ""
    s = re.sub(r"[\s\-\(\)]", "", str(value).strip())
    if s.startswith("0098"): return "+98" + s[4:]
    if s.startswith("98") and not s.startswith("+"): return "+98" + s[2:]
    return s



def validate_phone_format(value: Optional[str]) -> bool:
    if not value: return False
    v = normalize_phone(value)
    return bool(MOBILE_REGEX.match(v) or GENERIC_PHONE_REGEX.match(v))



def parse_datetime_flexible(value) -> Optional[timezone.datetime]:
    if value is None: return None
    if isinstance(value, (int, float)):
        return _from_epoch_like(value)

    s = str(value).strip()
    if not s: return None

    try:
        return timezone.datetime.fromisoformat(s)
    except Exception:
        pass

    if s.isdigit():
        return _from_epoch_like(int(s))

    return None



def _from_epoch_like(num: float) -> Optional[timezone.datetime]:
    try:
        length = len(str(int(num)))
        if length <= 10:   return timezone.datetime.fromtimestamp(num, tz=timezone.utc)
        if length <= 13:   return timezone.datetime.fromtimestamp(num / 1e3, tz=timezone.utc)
        if length <= 16:   return timezone.datetime.fromtimestamp(num / 1e6, tz=timezone.utc)
        if length <= 19:   return timezone.datetime.fromtimestamp(num / 1e9, tz=timezone.utc)
    except Exception:
        return None
    return None



def pick_first(row: Dict[str, object], keys: Iterable[str]) -> Optional[object]:
    for k in keys:
        if row.get(k): return row.get(k)
    return None



def _detect_contact_table(columns: set) -> bool:
    return (columns & CONTACT_PHONE_KEYS) and (columns & (CONTACT_NAME_KEYS | CONTACT_SURNAME_KEYS))


def _detect_calllog_table(columns: set) -> bool:
    return (columns & CALLLOG_PHONE_KEYS) and (
        columns & CALLLOG_DATE_KEYS or columns & CALLLOG_TYPE_KEYS or columns & CALLLOG_DURATION_KEYS
    )



def _extract_contact_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    phone = pick_first(row, CONTACT_PHONE_KEYS)
    if not validate_phone_format(phone): return None
    return {
        "name": pick_first(row, CONTACT_NAME_KEYS) or "",
        "phone_number": normalize_phone(phone),
        "email": pick_first(row, EMAIL_KEYS),
        "group": pick_first(row, GROUP_KEYS),
        "address": pick_first(row, ADDRESS_KEYS),
        "created_at": parse_datetime_flexible(pick_first(row, {"created_at", "date_added"})),
    }



def _map_call_type(raw) -> str:
    if not raw: return "incoming"
    s = str(raw).lower()
    if s.isdigit(): return {"1":"incoming","2":"outgoing","3":"missed"}.get(s,"incoming")
    if "out" in s: return "outgoing"
    if "miss" in s: return "missed"
    return "incoming"



def _extract_calllog_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    phone = pick_first(row, CALLLOG_PHONE_KEYS)
    if not validate_phone_format(phone): return None
    dt = parse_datetime_flexible(pick_first(row, CALLLOG_DATE_KEYS))
    return {
        "phone_number": normalize_phone(phone),
        "call_type": _map_call_type(pick_first(row, CALLLOG_TYPE_KEYS)),
        "call_date": dt,   # ممکنه None باشه
        "duration_seconds": int(pick_first(row, CALLLOG_DURATION_KEYS) or 0)
    }



def scan_and_extract_data(backup: Backup, db_dir: Path) -> Tuple[List[Dict], List[Dict]]:
    contacts, calls = [], []
    seen_contacts, seen_calls = set(), set()

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
                if not rows: continue

                if _detect_contact_table(set(col_names)):
                    for row in rows:
                        data = _extract_contact_row(row)
                        if not data: continue
                        key = (data["name"], data["phone_number"])
                        if not data["phone_number"] or key in seen_contacts: continue
                        seen_contacts.add(key)
                        contacts.append(data)

                elif _detect_calllog_table(set(col_names)):
                    for row in rows:
                        data = _extract_calllog_row(row)
                        if not data: continue
                        ts = int(data["call_date"].timestamp()) if data["call_date"] else 0
                        key = (data["phone_number"], ts, data["call_type"])
                        if key in seen_calls: continue
                        seen_calls.add(key)
                        calls.append(data)
        except sqlite3.DatabaseError:
            continue
        finally:
            try: conn.close()
            except: pass

    return contacts, calls


def store_extracted_data(backup: Backup, contacts: List[Dict], calls: List[Dict]) -> Tuple[int, int]:
    valid_contacts = [c for c in contacts if validate_phone_format(c.get("phone_number"))]

    valid_calls = [
        cl for cl in calls
        if validate_phone_format(cl.get("phone_number")) and isinstance(cl.get("call_date"), timezone.datetime)
    ]

    Contact.objects.bulk_create([Contact(backup=backup, **c) for c in valid_contacts], batch_size=1000)
    CallLog.objects.bulk_create([CallLog(backup=backup, **cl) for cl in valid_calls], batch_size=1000)

    return len(valid_contacts), len(valid_calls)
