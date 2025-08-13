from pathlib import Path
import mimetypes
from django.utils import timezone
from django.utils.timezone import make_aware, get_default_timezone
from .models import MediaFile, Backup, Message
from datetime import datetime
import json
import zlib

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
