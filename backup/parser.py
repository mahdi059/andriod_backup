from pathlib import Path
import mimetypes
from django.utils import timezone
from .models import MediaFile, Backup

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
