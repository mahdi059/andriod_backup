from pathlib import Path
import mimetypes
from django.utils import timezone
from ..models import Backup
import re
from ..serializers import  MediaParserSerializer
from django.core.files.base import ContentFile



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