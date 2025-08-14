from pathlib import Path
import mimetypes
from django.utils import timezone
from django.utils.timezone import make_aware, get_default_timezone
from .models import MediaFile, Backup, Message, App
from datetime import datetime
import json
import zlib
import apkutils2



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

        with open(file_path, "rb") as f:
            data = f.read()

        MediaFile.objects.create(
            backup=backup_instance,
            file_name=file_path.name,
            file_data=data,
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
            msg_type = "sms" if sms.get("type") == "1" else "mms"

            msg = Message(
                backup=backup_instance,
                sender=sms.get("address"),
                receiver=None,
                content=sms.get("body"),
                sent_at=convert_timestamp(sms.get("date_sent")),
                received_at=convert_timestamp(sms.get("date")),
                status=sms.get("status"),
                message_type=msg_type,
            )
            msg.save()
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





DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}

def parse_documents(folder_path: Path, backup: Backup) -> int:
    saved_count = 0

    for file_path in folder_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in DOCUMENT_EXTENSIONS:
            continue
        if file_path.stat().st_size == 0:
            continue  # فایل‌های خالی رو رد کن

        mime_type, _ = mimetypes.guess_type(file_path.name)
        with open(file_path, "rb") as f:
            data = f.read()

        # تبدیل mtime به datetime
        added_at_dt = datetime.fromtimestamp(file_path.stat().st_mtime)

        MediaFile.objects.create(
            backup=backup,
            file_name=file_path.name,
            file_data=data,
            media_type="document",
            mime_type=mime_type,
            size_bytes=file_path.stat().st_size,
            added_at=added_at_dt
        )

        saved_count += 1

    return saved_count
