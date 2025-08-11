from pathlib import Path
from typing import Optional
from .models import Contact

def parse_contacts_vcf(extracted_dir: Path, backup_instance) -> int:
    created = 0

    vcf_files = list(extracted_dir.rglob('*.vcf')) + list(extracted_dir.rglob('*.vcard'))
    print(f"Found {len(vcf_files)} vCard files in {extracted_dir}")

    for vcf_path in vcf_files:
        print(f"Processing file: {vcf_path}")
        try:
            text = vcf_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            print(f"Error reading file {vcf_path}: {e}")
            continue

        blocks = []
        current = []
        for line in text.splitlines():
            if line.strip().upper().startswith('BEGIN:VCARD'):
                current = [line]
            elif line.strip().upper().startswith('END:VCARD'):
                current.append(line)
                blocks.append('\n'.join(current))
                current = []
            else:
                if current:
                    current.append(line)

        print(f"Found {len(blocks)} vCard blocks in file {vcf_path}")

        for blk in blocks:
            name = _extract_vcard_field(blk, 'FN') or ''
            tel = _extract_vcard_field(blk, 'TEL') or ''
            email = _extract_vcard_field(blk, 'EMAIL') or ''

            print(f"Parsed contact - Name: {name}, Tel: {tel}, Email: {email}")

            exists = False
            if tel:
                exists = Contact.objects.filter(backup=backup_instance, phone_number=tel).exists()
            elif email:
                exists = Contact.objects.filter(backup=backup_instance, email__iexact=email).exists()
            else:
                exists = Contact.objects.filter(backup=backup_instance, name__iexact=name).exists()

            if exists:
                print(f"Contact already exists, skipping: Name={name}, Tel={tel}, Email={email}")
                continue

            Contact.objects.create(
                backup=backup_instance,
                name=name or '',
                phone_number=tel or '',
                email=email or ''
            )
            created += 1
            print(f"Created new contact: Name={name}, Tel={tel}, Email={email}")

    print(f"Total contacts created: {created}")
    return created


def _extract_vcard_field(block_text: str, field: str) -> Optional[str]:
    field_upper = field.upper()
    for line in block_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith(field_upper + ':') or line.upper().startswith(field_upper + ';'):
            parts = line.split(':', 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None
