from pathlib import Path
import subprocess
import tarfile
import mimetypes
import re
from minio import Minio
from minio.error import S3Error
import tempfile
import shutil
import libarchive.public


minio_client = Minio(
    "minio:9000", 
    access_key="minio",
    secret_key="minio123",
    secure=False
)

BUCKET_NAME = "backups"

def ensure_bucket():
    if not minio_client.bucket_exists(BUCKET_NAME):
        minio_client.make_bucket(BUCKET_NAME)

INVALID_CHARS = r'[<>:"/\\|?*]'

def sanitize_filename(name: str) -> str:
    return re.sub(INVALID_CHARS, "_", name)

MEDIA_CATEGORIES = {
    "photos": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"},
    "videos": {".mp4", ".mov", ".avi", ".mkv", ".flv"},
    "audios": {".mp3", ".wav", ".aac", ".ogg", ".amr", ".m4a"},
    "documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"},
    "databases": {".db", ".sqlite", ".sqlite3", ".realm"},
    "archives": {".zip", ".rar", ".tar", ".gz", ".7z"},
    "configs": {".xml", ".json", ".ini", ".cfg", ".yaml", ".yml"},
}

def categorize_media_file(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    for category, extensions in MEDIA_CATEGORIES.items():
        if ext in extensions:
            return category
    mime_type, _ = mimetypes.guess_type(file_path.name)
    if mime_type:
        if mime_type.startswith("image/"):
            return "photos"
        elif mime_type.startswith("video/"):
            return "videos"
        elif mime_type.startswith("audio/"):
            return "audios"
        elif mime_type in {"application/pdf", "text/plain"}:
            return "documents"
    return "others"

def ab_to_tar_with_hoardy(ab_file_path: str) -> Path:
    temp_tar = Path(tempfile.mktemp(suffix=".tar"))
    cmd = ["hoardy-adb", "unwrap", ab_file_path, str(temp_tar)]
    subprocess.run(cmd, check=True)
    return temp_tar


def extract_tar_to_temp(tar_path: Path) -> Path:
    temp_dir = Path(tempfile.mkdtemp())
    try:
        with libarchive.public.file_reader(str(tar_path)) as archive:
            for entry in archive:
                try:

                    safe_name = "/".join(sanitize_filename(part) for part in entry.pathname.split("/"))
                    dest_path = temp_dir / safe_name
                    dest_path.parent.mkdir(parents=True, exist_ok=True)


                    if entry.size > 0:
                        with open(dest_path, "wb") as f:
                            for block in entry.get_blocks():
                                f.write(block)

                except Exception as e:
                    print(f"⚠️ Failed to extract {entry.pathname}: {e}")

    except Exception as e:
        print(f"❌ Failed to open archive: {e}")

    return temp_dir




def organize_extracted_files_to_minio(extracted_dir: Path, backup_id: int) -> dict:
    ensure_bucket()
    stats = {cat: 0 for cat in MEDIA_CATEGORIES.keys()}
    stats["others"] = 0
    for file_path in extracted_dir.rglob("*"):
        if not file_path.is_file():
            continue
        category = categorize_media_file(file_path)
        object_name = f"{backup_id}/{category}/{file_path.name}"
        try:
            minio_client.fput_object(BUCKET_NAME, object_name, str(file_path))
            stats[category] += 1
            file_path.unlink()  
        except S3Error as e:
            print(f"Failed to upload {file_path} -> {e}")
    return stats

def process_ab_file(ab_file_path: str, backup_id: int) -> dict:

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ab") as tmp_ab:
        shutil.copyfile(ab_file_path, tmp_ab.name)
        tmp_ab_path = Path(tmp_ab.name)

    tar_path = ab_to_tar_with_hoardy(str(tmp_ab_path))
    extracted_dir = extract_tar_to_temp(tar_path)
    stats = organize_extracted_files_to_minio(extracted_dir, backup_id)


    tmp_ab_path.unlink(missing_ok=True)
    tar_path.unlink(missing_ok=True)
    shutil.rmtree(extracted_dir, ignore_errors=True)

    return stats
