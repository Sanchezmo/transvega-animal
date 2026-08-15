"""
Privacy Router - Deterministic routing for data based on sensitivity.
"""

from typing import Any

import structlog

logger = structlog.get_logger()


# Define what constitutes sensitive data
SENSITIVE_FIELDS: set[str] = {
    # Personal identification
    "dni",
    "nif",
    "cif",
    "nie",
    "passport",
    "id_number",
    # Financial
    "iban",
    "account_number",
    "credit_card",
    "cvc",
    "bic",
    "swift",
    # Contact
    "phone",
    "mobile",
    "fax",
    # Address
    "address",
    "street",
    "zip",
    "postcode",
    # Health
    "medical_record",
    "health_record",
    "medical_history",
    # Business
    "internal_note",
    "confidential",
    "proprietary",
    # Media that should be LOCAL_ONLY by default
    "original_photo",
    "original_video",
    "raw_media",
}

SENSITIVE_PATTERNS: list[str] = [
    r"^.*_(dni|nif|cif|nie|passport|id_number)$",
    r"^.*_(iban|account|card|cvc|bic|swift)$",
    r"^.*_(phone|mobile|fax)$",
    r"^.*_(address|street|zip|postcode)$",
    r"^.*_(medical|health)_.*",
    r"^.*_(internal|confidential|proprietary)$",
    r"^.*_(original|raw).*media$",
]


class PrivacyRouter:
    """
    Deterministic privacy router to decide if data should be treated as
    LOCAL_ONLY or can be sent to external services (ONLINE_ALLOWED).

    The decision is based on field names and patterns, not on LLM judgment.
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def is_sensitive_field(field_name: str) -> bool:
        """Check if a field name is considered sensitive."""
        if not isinstance(field_name, str):
            return False
        field_lower = field_name.lower().strip()
        if field_lower in SENSITIVE_FIELDS:
            return True
        # Check patterns
        import re

        for pattern in SENSITIVE_PATTERNS:
            if re.match(pattern, field_lower):
                return True
        return False

    @staticmethod
    def contains_sensitive_data(data: Any) -> bool:
        """
        Recursively check if the data structure contains sensitive fields.
        Returns True if any sensitive data is found.
        """
        if isinstance(data, dict):
            for key, value in data.items():
                if PrivacyRouter.is_sensitive_field(key):
                    logger.debug("sensitive_field_found", field=key)
                    return True
                # Recurse into nested structures
                if PrivacyRouter.contains_sensitive_data(value):
                    return True
        elif isinstance(data, list | tuple | set):
            for item in data:
                if PrivacyRouter.contains_sensitive_data(item):
                    return True
        # For other types (str, int, etc.) we don't consider the value itself
        # as sensitive unless the field name indicates it.
        return False

    @staticmethod
    def filter_sensitive_data(data: Any) -> Any:
        """
        Return a copy of the data with sensitive fields removed or redacted.
        This is useful for logging or sending to external services.
        """
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if PrivacyRouter.is_sensitive_field(key):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = PrivacyRouter.filter_sensitive_data(value)
            return result
        elif isinstance(data, list):
            return [PrivacyRouter.filter_sensitive_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(PrivacyRouter.filter_sensitive_data(item) for item in data)
        elif isinstance(data, set):
            return {PrivacyRouter.filter_sensitive_data(item) for item in data}
        else:
            return data

    @staticmethod
    def get_privacy_scope(data: Any) -> str:
        """
        Determine the privacy scope for the given data.
        Returns "LOCAL_ONLY" if sensitive data is present, "ONLINE_ALLOWED" otherwise.
        """
        if PrivacyRouter.contains_sensitive_data(data):
            return "LOCAL_ONLY"
        return "ONLINE_ALLOWED"


# Singleton instance for convenience
privacy_router = PrivacyRouter()
