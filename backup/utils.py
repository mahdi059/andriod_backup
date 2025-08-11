from pathlib import Path
import subprocess
import tarfile


def ab_to_tar_with_abe(ab_path: Path, tar_path: Path, abe_jar_path: Path) -> Path:
    if not ab_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {ab_path}")
    if not abe_jar_path.is_file():
        raise FileNotFoundError(f"abe.jar not found: {abe_jar_path}")

    cmd = ['java', '-jar', str(abe_jar_path), 'unpack', str(ab_path), str(tar_path)]
    try:
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
