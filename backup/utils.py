from pathlib import Path
import subprocess
import tarfile
import mimetypes
import shutil
import re

def ab_to_tar_with_hoardy(ab_path: Path, tar_path: Path) -> Path:
    if not ab_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {ab_path}")

    cmd = ["hoardy-adb", "unwrap", str(ab_path), str(tar_path)]

    try:
        print(f"Running hoardy-adb unwrap for: {ab_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"hoardy-adb output:\n{result.stdout}")
        if result.stderr:
            print(f"hoardy-adb error output:\n{result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f"hoardy-adb command failed with exit code {e.returncode}")
        print(f"Output:\n{e.output}")
        print(f"Error:\n{e.stderr}")
        raise RuntimeError(f"hoardy-adb unwrap command failed: {e.stderr.strip() or 'Unknown error'}") from e

    return tar_path


INVALID_CHARS = r'[<>:"/\\|?*]'

def sanitize_filename(name: str) -> str:
    return re.sub(INVALID_CHARS, "_", name)

def extract_tar(tar_path: Path, output_dir: Path) -> None:
    if not tar_path.is_file():
        raise FileNotFoundError(f"Tar file not found: {tar_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, 'r:*') as tar:
        for member in tar.getmembers():
            safe_name = "/".join(sanitize_filename(part) for part in member.name.split("/"))
            member_path = output_dir / safe_name

            abs_output_dir = output_dir.resolve()
            abs_member_path = member_path.resolve()
            
            if not str(abs_member_path).startswith(str(abs_output_dir)):
                raise Exception(f"Path traversal attempt detected in tar file: {member.name}")

            member.name = safe_name
            tar.extract(member, path=output_dir)



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

def organize_extracted_files(extracted_dir: Path) -> dict:
    if not extracted_dir.exists():
        raise FileNotFoundError(f"Extracted directory not found: {extracted_dir}")

    stats = {cat: 0 for cat in MEDIA_CATEGORIES.keys()}
    stats["others"] = 0

    for file_path in extracted_dir.rglob("*"):
        if not file_path.is_file():
            continue

        category = categorize_media_file(file_path)
        category_dir = extracted_dir / category
        category_dir.mkdir(exist_ok=True)

        target_path = category_dir / file_path.name
        if file_path != target_path:
            shutil.move(str(file_path), str(target_path))

        stats[category] += 1

    return stats
