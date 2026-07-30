"""
Mappers para convertir entre esquemas Pydantic y formato Dolibarr.
"""
from typing import Dict, Any, Optional
from app.schemas import ThirdPartyCreate, ThirdPartyUpdate, ThirdPartyResponse


def thirdparty_to_dolibarr(tercero: ThirdPartyCreate) -> Dict[str, Any]:
    """
    Convertir ThirdPartyCreate a formato Dolibarr API.
    
    Mapeo de campos:
    - name -> name
    - name_alias -> name_alias
    - email -> email
    - phone -> phone
    - address -> address
    - zip -> zip
    - town -> town
    - country_id -> country_id
    - country_code -> country_code
    - state_id -> state_id
    - client -> client
    - supplier -> supplier
    - status -> status
    - vat_number -> tva_intra (Dolibarr usa tva_intra para NIF/CIF intracomunitario)
    - default_lang -> default_lang
    - fk_country -> fk_country (alias)
    - fk_state -> fk_state (alias)
    - fk_parent -> fk_parent
    - iban -> iban
    - bic -> bic
    - skype -> skype
    - twitter -> twitter
    - facebook -> facebook
    - linkedin -> linkedin
    - shipping_method_id -> shipping_method_id
    - payment_term_id -> payment_term_id
    - bar_code -> bar_code
    - code_client -> code_client (REQUERIDO por Dolibarr)
    """
    data = tercero.model_dump(exclude_none=True, by_alias=True)
    
    # Mapear country_code a fk_country (Dolibarr usa IDs numéricos para países)
    country_code_to_id = {
        "ES": 4,   # Spain
        "US": 223, # United States
        "FR": 69,  # France
        "DE": 58,  # Germany
        "IT": 100, # Italy
        "PT": 168, # Portugal
        "MX": 137, # Mexico
        "CO": 43,  # Colombia
        "AR": 10,  # Argentina
        "CL": 39,  # Chile
        "PE": 164, # Peru
        "EC": 63,  # Ecuador
        "PA": 159, # Panama
        "DO": 56,  # Dominican Republic
        "VE": 229, # Venezuela
    }
    
    # Mapear campos con nombres diferentes en Dolibarr
    field_mapping = {
        "country_id": "country_id",  # Dolibarr API usa country_id, no fk_country
        "state_id": "fk_state",
        "vat_number": "tva_intra",  # Dolibarr usa tva_intra para VAT
    }
    
    result = {}
    for key, value in data.items():
        dolibarr_key = field_mapping.get(key, key)
        result[dolibarr_key] = value
    
    # Si viene country_code pero no country_id, mapear automáticamente
    if "country_id" not in result and "country_code" in result:
        cc = result["country_code"].upper()
        if cc in country_code_to_id:
            result["country_id"] = country_code_to_id[cc]
    
    # Asegurar code_client si no viene (Dolibarr lo requiere)
    if "code_client" not in result and result.get("client") == 1:
        # Generar código cliente automático
        import time
        result["code_client"] = f"CLI-{int(time.time())}"
    
    return result


def thirdparty_update_to_dolibarr(tercero: ThirdPartyUpdate) -> Dict[str, Any]:
    """Convertir ThirdPartyUpdate a formato Dolibarr (solo campos no-None)."""
    data = tercero.model_dump(exclude_none=True, by_alias=True)
    
    # Mapear country_code a fk_country (Dolibarr usa IDs numéricos para países)
    country_code_to_id = {
        "ES": 4,   # Spain
        "US": 223, # United States
        "FR": 69,  # France
        "DE": 58,  # Germany
        "IT": 100, # Italy
        "PT": 168, # Portugal
        "MX": 137, # Mexico
        "CO": 43,  # Colombia
        "AR": 10,  # Argentina
        "CL": 39,  # Chile
        "PE": 164, # Peru
        "EC": 63,  # Ecuador
        "PA": 159, # Panama
        "DO": 56,  # Dominican Republic
        "VE": 229, # Venezuela
    }
    
    field_mapping = {
        "country_id": "country_id",  # Dolibarr API usa country_id
        "state_id": "fk_state",
        "vat_number": "tva_intra",  # Dolibarr usa tva_intra para VAT
    }
    
    result = {}
    for key, value in data.items():
        dolibarr_key = field_mapping.get(key, key)
        result[dolibarr_key] = value
    
    # Si viene country_code pero no country_id, mapear automáticamente
    if "country_id" not in result and "country_code" in result:
        cc = result["country_code"].upper()
        if cc in country_code_to_id:
            result["country_id"] = country_code_to_id[cc]
    
    return result


def dolibarr_to_thirdparty(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convertir respuesta Dolibarr a formato ThirdPartyResponse.
    
    Mapeo inverso:
    - fk_country -> country_id
    - fk_state -> state_id
    - rowid -> id (Dolibarr usa rowid como PK)
    - date_creation (timestamp) -> datec (datetime)
    - date_modification (timestamp) -> datem (datetime)
    - tva_intra -> vat_number
    """
    field_mapping = {
        "fk_country": "country_id",
        "fk_state": "state_id",
        "rowid": "id",
        "date_creation": "datec",
        "date_modification": "datem",
        "fk_user_creat": "fk_user_author",
        "fk_user_modif": "fk_user_modif",
        "tva_intra": "vat_number",
    }
    
    result = {}
    for key, value in data.items():
        our_key = field_mapping.get(key, key)
        
        # Convert timestamps to datetime
        if our_key in ("datec", "datem") and isinstance(value, (int, float)):
            from datetime import datetime
            result[our_key] = datetime.fromtimestamp(value)
        # Handle empty string country_code -> None
        elif our_key == "country_code" and value == "":
            result[our_key] = None
        # Handle null strings for integer fields
        elif our_key in ("fk_user_author", "fk_user_modif") and value in (None, "", "null"):
            result[our_key] = 1  # default to admin user
        # Handle status -> status mapping
        elif key == "status":
            result["status"] = int(value) if value is not None else 1
        else:
            result[our_key] = value
    
    # Asegurar campos requeridos
    if "id" not in result and "rowid" in data:
        result["id"] = data["rowid"]
    
    # Default values for required fields
    if "datec" not in result:
        from datetime import datetime
        result["datec"] = datetime.now()
    if "datem" not in result:
        from datetime import datetime
        result["datem"] = datetime.now()
    if "fk_user_author" not in result:
        result["fk_user_author"] = 1
    if "fk_user_modif" not in result:
        result["fk_user_modif"] = 1
    if "country_id" not in result:
        result["country_id"] = None
    if "state_id" not in result:
        result["state_id"] = None
    
    return result


def dolibarr_list_to_thirdparties(data: list) -> list:
    """Convertir lista de terceros Dolibarr a lista ThirdPartyResponse."""
    return [dolibarr_to_thirdparty(item) for item in data]