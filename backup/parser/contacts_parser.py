from pathlib import Path
from datetime import datetime, timezone as dt_timezone
import sqlite3
import re
from typing import Dict, Iterable, List, Optional
from ..serializers import ContactParserSerializer
from ..models import Backup
import tempfile
import logging
from ..utils import minio_client, normalize_phone, parse_datetime_flexible, pick_first


BUCKET_NAME = "backups"

logger = logging.getLogger(__name__)

CONTACT_NAME_KEYS = {"name", "display_name", "full_name", "given_name", "first_name"}
CONTACT_SURNAME_KEYS = {"family_name", "last_name", "surname"}
CONTACT_PHONE_KEYS = {"phone_number", "number", "mobile", "tel", "msisdn"}
EMAIL_KEYS = {"email", "e_mail", "mail"}
GROUP_KEYS = {"group", "group_name", "label", "category"}
ADDRESS_KEYS = {"address", "addr", "street", "city", "location"}




def _detect_contact_table(columns: set) -> bool:
    return (columns & CONTACT_PHONE_KEYS) and (columns & (CONTACT_NAME_KEYS | CONTACT_SURNAME_KEYS))


def _extract_contact_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    phone = pick_first(row, CONTACT_PHONE_KEYS)
    if not phone:
        return None
    phone = normalize_phone(phone)
    created_at_raw = pick_first(row, {"created_at", "date_added"})
    created_at = parse_datetime_flexible(created_at_raw)
    return {
        "name": pick_first(row, CONTACT_NAME_KEYS) or "",
        "phone_number": phone,
        "email": pick_first(row, EMAIL_KEYS),
        "group": pick_first(row, GROUP_KEYS),
        "address": pick_first(row, ADDRESS_KEYS),
        "created_at": created_at,
    }


def scan_and_extract_contacts_minio(backup_instance: Backup) -> List[Dict]:
    prefix = f"{backup_instance.id}/databases/"
    contacts = []
    seen_contacts = set()

    logger.info("[*] Scanning Minio for contacts in prefix:", prefix)
    objects = minio_client.list_objects(BUCKET_NAME, prefix=prefix, recursive=True)

    for obj in objects:
        logger.info("[+] Found object: %s (size:%s)",obj.object_name, obj.size)

        if not obj.object_name.lower().endswith((".db", ".sqlite")):
            logger.info("[-] Skipping non-sqlite file:", obj.object_name)
            continue

        try:
            response = minio_client.get_object(BUCKET_NAME, obj.object_name)
            file_bytes = response.read()
            response.close()
            response.release_conn()
            logger.info("[+] Successfully read %s bytes from %s", len(file_bytes), obj.object_name)
        except Exception as e:
            logger.error("[!] Error reading object %s from Minio: %s", obj.object_name, e)
            continue

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            tmp_file.write(file_bytes)
            tmp_file_path = tmp_file.name
        logger.info("[+] Wrote temp sqlite file: ", tmp_file_path)

        try:
            conn = sqlite3.connect(tmp_file_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            logger.info("[+] Tables in %s : %s", obj.object_name, tables)
            for (table,) in tables:
                logger.info("[*] Checking table:", table)
                try:
                    cursor.execute(f'SELECT * FROM "{table}"')
                    col_names = [d[0].lower() for d in cursor.description]
                    rows = [dict(zip(col_names, r)) for r in cursor.fetchall()]
                    logger.info("------> Found %s rows, columns=%s", len(rows), col_names)
                except Exception as e:
                    logger.error("------> [!] Failed to read table %s : %s", table, e)
                    continue

                if not rows or not _detect_contact_table(set(col_names)):
                    logger.info("------> [-] Skipping table %s, not matching contact schema", table)
                    continue

                for row in rows:
                    data = _extract_contact_row(row)
                    logger.info("------> [+] Extracted row:", data)
                    if not data:
                        continue
                    data["backup"] = backup_instance.id
                    key = (data["name"], data["phone_number"])
                    if key in seen_contacts:
                        continue
                    seen_contacts.add(key)
                    contacts.append(data)

        except Exception as e:
            logger.error("[!] Error scanning %s : %s", obj.object_name, e)
            continue
        finally:
            try:
                conn.close()
            except:
                pass

    logger.info("[*] Finished scanning. Total contacts extracted:", len(contacts))
    return contacts


def store_contacts(backup: Backup, contacts: List[Dict]) -> int:
    serializer = ContactParserSerializer(data=contacts, many=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(backup=backup)
    return len(serializer.data)
