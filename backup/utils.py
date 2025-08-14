from pathlib import Path
import subprocess
import tarfile
import mimetypes
import shutil


def ab_to_tar_with_abe(ab_path: Path, tar_path: Path, abe_jar_path: Path) -> Path:
    if not ab_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {ab_path}")
    if not abe_jar_path.is_file():
        raise FileNotFoundError(f"abe.jar not found: {abe_jar_path}")

    java_path = Path(r"C:\Program Files\Java\jdk-21\bin\java.exe")  

    if not java_path.is_file():
        raise FileNotFoundError(f"Java executable not found: {java_path}")

    cmd = [str(java_path), '-jar', str(abe_jar_path), 'unpack', str(ab_path), str(tar_path)]
    try:
        print(f"Running ABE jar from: {abe_jar_path} using Java at {java_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"ABE output:\n{result.stdout}")
        if result.stderr:
            print(f"ABE error output:\n{result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f"ABE command failed with exit code {e.returncode}")
        print(f"Output:\n{e.output}")
        print(f"Error:\n{e.stderr}")
        raise RuntimeError(f"ABE unpack command failed: {e.stderr.strip() or 'Unknown error'}") from e

    return tar_path



def extract_tar(tar_path: Path, output_dir: Path) -> None:
    if not tar_path.is_file():
        raise FileNotFoundError(f"Tar file not found: {tar_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, 'r:*') as tar:
        for member in tar.getmembers():
            member_path = output_dir / member.name
            abs_output_dir = output_dir.resolve()
            abs_member_path = member_path.resolve()
            
            if not str(abs_member_path).startswith(str(abs_output_dir)):
                raise Exception(f"Path traversal attempt detected in tar file: {member.name}")

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
