"""
Tax ID (CIF/NIF) normalization utilities.
Centralized to ensure consistent normalization across the codebase.
"""

import re
from typing import Any


def normalize_tax_id(tax_id: str) -> str:
    """
    Normalize a tax ID (CIF/NIF) for comparison and storage.

    Rules:
    - Strip whitespace
    - Uppercase
    - Remove visual separators (spaces, dashes, dots) that don't affect meaning
    - Do NOT remove characters that could be significant (letters, digits)

    Examples:
        "B-12345678" -> "B12345678"
        "b 12 34 56 78" -> "B12345678"
        "ESA12345678" -> "ESA12345678" (EU prefix preserved)
    """
    if not tax_id:
        return ""

    # Strip whitespace and uppercase
    normalized = tax_id.strip().upper()

    # Remove visual separators: spaces, dashes, dots
    # But be careful not to remove meaningful characters
    normalized = normalized.replace(" ", "").replace("-", "").replace(".", "")

    return normalized


def extract_tax_id_from_thirdparty(thirdparty: dict[str, Any]) -> str:
    """
    Extract and normalize tax ID from a Dolibarr thirdparty object.

    Checks both 'vat_number' and 'vatnumber' fields (Dolibarr inconsistency).
    """
    vat = thirdparty.get("vat_number") or thirdparty.get("vatnumber") or ""
    return normalize_tax_id(vat)


def is_valid_spanish_cif_nif(tax_id: str) -> bool:
    """
    Basic validation for Spanish CIF/NIF format.
    Does NOT validate check digits - just format.
    """
    if not tax_id:
        return False

    normalized = normalize_tax_id(tax_id)

    # Spanish NIF (individuals): 8 digits + letter, or letter + 7 digits + letter
    # Spanish CIF (companies): Letter + 8 digits (old) or Letter + 7 digits + letter/number
    # Basic pattern: starts with letter, followed by 7-8 alphanumerics
    pattern = r"^[A-Z][0-9A-Z]{7,8}$"

    return bool(re.match(pattern, normalized))


__all__ = ["normalize_tax_id", "extract_tax_id_from_thirdparty", "is_valid_spanish_cif_nif"]

