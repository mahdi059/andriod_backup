from django.utils import timezone
from ..models import App
import apkutils2


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