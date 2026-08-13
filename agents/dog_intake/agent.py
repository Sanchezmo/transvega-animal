"""Agente de Intake de Perros - Recepción y registro de animales mediante Telegram y otras fuentes."""
import asyncio
import os
from datetime import date, datetime
from typing import Dict, List, Optional, Any
import structlog
import httpx

from app.services.intake_session import intake_session_store
from app.services.media_storage import save_uploaded_file
from app.core.privacy_router import privacy_router

logger = structlog.get_logger()


class DogIntakeAgent:
    """
    Agente de Intake de Perros

    Responsabilidades:
    - Crear ficha del perro
    - Modificar ficha
    - Asociar fotografías
    - Asociar vídeos
    - Asociar padre
    - Asociar madre
    - Relacionar hermanos/camada
    - Identificar raza
    - Almacenar datos sanitarios
    - Cambiar disponibilidad
    - Mantener historial de modificaciones

    Cada perro tiene un identificador interno único (ej: DOG-2026-000001).
    """

    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "dog_intake"
        self.agent_name = "Dog Intake Agent"
        # Base URL for internal API (same service)
        self.api_base = config.get("INTERNAL_API_URL", "http://localhost:8000")
        self.client = httpx.AsyncClient(base_url=self.api_base, timeout=30.0)
        self.capabilities = [
            "create_dog",
            "update_dog",
            "add_media",
            "set_parents",
            "set_litter",
            "update_health",
            "change_status",
            "get_dog",
            "list_dogs",
        ]
        self.restrictions = [
            "no_direct_db_access",  # No acceso directo a Dolibarr DB
            "media_must_be_local_first",  # Media se considera LOCAL_ONLY por defecto
            "privacy_scope_aware",  # Debe respetar el ámbito de privacidad
        ]

    async def start(self):
        logger.info("starting_dog_intake_agent")

    async def stop(self):
        await self.client.aclose()

    async def process_task(self, task: Dict) -> Dict:
        task_type = task.get("task_type")

        handlers = {
            "create_dog": self._create_dog,
            "update_dog": self._update_dog,
            "add_media": self._add_media,
            "set_parents": self._set_parents,
            "set_litter": self._set_litter,
            "update_health": self._update_health,
            "change_status": self._change_status,
            "get_dog": self._get_dog,
            "list_dogs": self._list_dogs,
        }

        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}

        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}

    # =========================================================================
    # DOG CRUD OPERATIONS (now calling internal API)
    # =========================================================================

    async def _create_dog(self, data: Dict) -> Dict:
        """Crear nuevo perro via API."""
        # Validate required fields
        required = ["name", "breed_id", "sex", "birth_date", "color", "microchip"]
        for field in required:
            if field not in data:
                return {"success": False, "error": f"Missing required field: {field}"}

        # Prepare payload for API (matches DogCreate schema)
        payload = {
            "name": data["name"],
            "breed_id": data["breed_id"],
            "litter_id": data.get("litter_id"),
            "sex": data["sex"],
            "birth_date": data["birth_date"],
            "color": data["color"],
            "microchip": data["microchip"],
            "sire_name": data.get("sire_name"),
            "dam_name": data.get("dam_name"),
            "pedigree": data.get("pedigree"),
            "vet_status": data.get("vet_status", "healthy"),
            "purchase_price": data.get("purchase_price", 0.0),
            "sale_price": data.get("sale_price", 0.0),
            "associated_costs": data.get("associated_costs", 0.0),
            "expediente_id": data.get("expediente_id"),
        }

        try:
            resp = await self.client.post("/dogs/", json=payload)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        logger.info("dog_created_via_api", dog_id=result.get("id"), internal_id=result.get("internal_id"))

        return {
            "success": True,
            "dog": result,
            "message": f"Perro creado con ID interno {result.get('internal_id')}"
        }

    async def _update_dog(self, data: Dict) -> Dict:
        """Actualizar perro existente via API."""
        dog_id = data.get("dog_id")
        if not dog_id:
            return {"success": False, "error": "Dog ID required"}

        # Build payload with only provided fields
        payload = {}
        updatable_fields = [
            "name", "breed_id", "litter_id", "sex", "birth_date", "color",
            "microchip", "sire_name", "dam_name", "pedigree", "vet_status",
            "purchase_price", "sale_price", "associated_costs", "expediente_id", "status"
        ]
        for field in updatable_fields:
            if field in data:
                payload[field] = data[field]

        if not payload:
            return {"success": False, "error": "No fields to update"}

        try:
            resp = await self.client.put(f"/dogs/{dog_id}", json=payload)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        logger.info("dog_updated_via_api", dog_id=dog_id)

        return {
            "success": True,
            "dog": result,
            "message": "Perro actualizado"
        }

    async def _add_media(self, data: Dict) -> Dict:
        """Asociar media (foto/video) a un perro via API."""
        dog_id = data.get("dog_id")
        if not dog_id:
            return {"success": False, "error": "Dog ID required"}

        # Validate media data
        required_media = ["file_content", "filename", "purpose", "uploaded_by"]
        for field in required_media:
            if field not in data:
                return {"success": False, "error": f"Missing required media field: {field}"}

        file_content = data["file_content"]  # expect bytes
        filename = data["filename"]
        purpose = data["purpose"]
        uploaded_by = data["uploaded_by"]

        # Validate purpose
        if purpose not in ["original", "processed", "social", "listing"]:
            return {"success": False, "error": "purpose must be one of: original, processed, social, listing"}

        # First, we need to know the dog's internal_id to store files correctly.
        # Get dog info from API
        try:
            dog_resp = await self.client.get(f"/dogs/{dog_id}")
            dog_resp.raise_for_status()
            dog_info = dog_resp.json()
        except Exception as e:
            logger.error("failed_to_fetch_dog", error=str(e))
            return {"success": False, "error": "Could not retrieve dog info"}

        internal_id = dog_info.get("internal_id")
        if not internal_id:
            return {"success": False, "error": "Dog internal ID missing"}

        # Save file to storage
        try:
            media_metadata = save_uploaded_file(
                file_content=file_content,
                filename=filename,
                dog_internal_id=internal_id,
                purpose=purpose,
                uploaded_by=uploaded_by,
            )
        except Exception as e:
            logger.error("media_save_failed", error=str(e))
            return {"success": False, "error": f"Failed to save media: {e}"}

        # Set the dog_id in metadata (the storage function left it as 0)
        media_metadata["dog_id"] = dog_id

        # Now call API to create DogMedia record
        try:
            media_resp = await self.client.post(f"/dogs/{dog_id}/media", json=media_metadata)
            media_resp.raise_for_status()
            media_record = media_resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_media_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error creating media: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        logger.info("media_added_via_api", dog_id=dog_id, media_id=media_record.get("id"))

        return {
            "success": True,
            "media": media_record,
            "message": f"Media asociado al perro {internal_id}"
        }

    async def _set_parents(self, data: Dict) -> Dict:
        """Asociar padre y/o madre a un perro via API."""
        dog_id = data.get("dog_id")
        if not dog_id:
            return {"success": False, "error": "Dog ID required"}

        payload = {}
        if "sire_name" in data:
            payload["sire_name"] = data["sire_name"]
        if "dam_name" in data:
            payload["dam_name"] = data["dam_name"]

        if not payload:
            return {"success": False, "error": "No parent fields provided"}

        try:
            resp = await self.client.put(f"/dogs/{dog_id}", json=payload)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        logger.info("parents_set_via_api", dog_id=dog_id)

        return {
            "success": True,
            "dog": result,
            "message": "Padres actualizados"
        }

    async def _set_litter(self, data: Dict) -> Dict:
        """Asociar perro a una camada via API."""
        dog_id = data.get("dog_id")
        if not dog_id:
            return {"success": False, "error": "Dog ID required"}

        litter_id = data.get("litter_id")
        if not litter_id:
            return {"success": False, "error": "litter_id required"}

        payload = {"litter_id": litter_id}

        try:
            resp = await self.client.put(f"/dogs/{dog_id}", json=payload)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        logger.info("litter_set_via_api", dog_id=dog_id, litter_id=litter_id)

        return {
            "success": True,
            "dog": result,
            "message": "Perro asociado a camada"
        }

    async def _update_health(self, data: Dict) -> Dict:
        """Actualizar o agregar registro de salud via API."""
        dog_id = data.get("dog_id")
        if not dog_id:
            return {"success": False, "error": "Dog ID required"}

        # Build health record payload
        payload = {}
        health_fields = [
            "vet_check_date", "weight_kg", "temperature_celsius", "heart_rate_bpm",
            "respiratory_rate", "stool_condition", "urine_condition", "appetite",
            "energy_level", "notes", "next_check_date"
        ]
        for field in health_fields:
            if field in data:
                payload[field] = data[field]

        if not payload:
            return {"success": False, "error": "No health fields provided"}

        try:
            resp = await self.client.post(f"/dogs/{dog_id}/health", json=payload)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        logger.info("health_record_added_via_api", dog_id=dog_id)

        return {
            "success": True,
            "health_record": result,
            "message": "Registro de salud añadido"
        }

    async def _change_status(self, data: Dict) -> Dict:
        """Cambiar el estado de disponibilidad del perro via API."""
        dog_id = data.get("dog_id")
        if not dog_id:
            return {"success": False, "error": "Dog ID required"}

        new_status = data.get("status")
        if not new_status or new_status not in ["draft", "available", "reserved", "sold", "inactive"]:
            return {"success": False, "error": "Invalid status"}

        payload = {"status": new_status}

        try:
            resp = await self.client.put(f"/dogs/{dog_id}", json=payload)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        logger.info("dog_status_changed_via_api", dog_id=dog_id, new_status=new_status)

        return {
            "success": True,
            "dog": result,
            "message": f"Estado cambiado a {new_status}"
        }

    async def _get_dog(self, data: Dict) -> Dict:
        """Obtener un perro por ID via API."""
        dog_id = data.get("dog_id")
        if not dog_id:
            return {"success": False, "error": "Dog ID required"}

        try:
            resp = await self.client.get(f"/dogs/{dog_id}")
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        return {
            "success": True,
            "dog": result,
        }

    async def _list_dogs(self, data: Dict) -> Dict:
        """Listar perros con filtros opcionales via API."""
        # Build query params
        params = {}
        if data.get("breed_id") is not None:
            params["breed_id"] = data["breed_id"]
        if data.get("litter_id") is not None:
            params["litter_id"] = data["litter_id"]
        if data.get("status") is not None:
            params["status"] = data["status"]
        limit = data.get("limit")
        if limit is not None:
            params["limit"] = limit
        offset = data.get("offset")
        if offset is not None:
            params["offset"] = offset

        try:
            resp = await self.client.get("/dogs/", params=params)
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("api_error", status=e.response.status_code, text=e.response.text)
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error("unexpected_error", error=str(e))
            return {"success": False, "error": str(e)}

        return {
            "success": True,
            "dogs": result.get("data", []),
            "total": result.get("total", 0),
            "limit": result.get("limit", 0),
            "offset": result.get("offset", 0),
        }

    # =========================================================================
    # INTAKE SESSION HANDLERS (to be used by webhook)
    # =========================================================================

    async def handle_telegram_update(self, update: Dict) -> Dict:
        """Process a Telegram update (message or callback) and manage intake session."""
        # Extract basic info
        message = update.get("message") or update.get("edited_message")
        if not message:
            return {"success": False, "error": "No message in update"}

        user_id = message.get("from", {}).get("id")
        chat_id = message.get("chat", {}).get("id")
        if user_id is None or chat_id is None:
            return {"success": False, "error": "Could not extract user/chat ID"}

        # Get or create session
        session = intake_session_store.get_or_create(user_id, chat_id)

        # Reset privacy scope evaluation each time we get new data
        session.update_privacy_scope()

        # Handle text
        if "text" in message:
            text = message["text"]
            session.data["raw_text"] = text
            session.touch()
            # TODO: parse structured data (e.g., lines like "Raza: Pomerania")
            # For now, we just acknowledge.
            return {
                "success": True,
                "message": "Texto recibido. Continúa enviando datos o archivos.",
                "session_id": session.session_id,
                "privacy_scope": session.privacy_scope,
            }

        # Handle photo ( Telegram sends array of sizes, we take the largest )
        if "photo" in message:
            # In a real implementation, we would download the file via bot API.
            # For now, we simulate by expecting the file content to be provided elsewhere.
            # This handler would be called by the webhook after the file has been downloaded
            # by the bot and passed as file_content.
            # Since we cannot download directly here (need bot token), we assume the webhook
            # will have already downloaded and placed the content in update under a custom field.
            # We'll look for 'file_content' and 'filename' added by the webhook processor.
            file_content = message.get("file_content")  # bytes, to be set by webhook preprocessor
            filename = message.get("filename", f"photo_{int(session.updated_at)}.jpg")
            if file_content and isinstance(file_content, bytes):
                # Determine purpose based on user intent? For now default to original.
                purpose = "original"
                # Use session data to guess if user said it's parent, etc.
                # For simplicity, we store as original and later user can reassign via another command.
                media_data = {
                    "file_content": file_content,
                    "filename": filename,
                    "purpose": purpose,
                    "uploaded_by": user_id,
                }
                # Delegate to _add_media but we need dog_id first.
                # If we don't have a dog yet, we store media in session and associate later.
                # For now, we just acknowledge receipt and store in session.
                session.media_files.append({
                    "content": file_content,
                    "filename": filename,
                    "purpose": purpose,
                    "uploaded_by": user_id,
                })
                session.touch()
                session.update_privacy_scope()
                return {
                    "success": True,
                    "message": f"Foto recibida y almacenada en sesión. Propósito: {purpose}",
                    "session_id": session.session_id,
                    "privacy_scope": session.privacy_scope,
                }
            else:
                return {"success": False, "error": "No file content provided"}

        # Handle video (similar)
        if "video" in message:
            file_content = message.get("file_content")
            filename = message.get("filename", f"video_{int(session.updated_at)}.mp4")
            if file_content and isinstance(file_content, bytes):
                purpose = "original"
                session.media_files.append({
                    "content": file_content,
                    "filename": filename,
                    "purpose": purpose,
                    "uploaded_by": user_id,
                })
                session.touch()
                session.update_privacy_scope()
                return {
                    "success": True,
                    "message": f"Video recibido y almacenado en sesión. Propósito: {purpose}",
                    "session_id": session.session_id,
                    "privacy_scope": session.privacy_scope,
                }
            else:
                return {"success": False, "error": "No file content provided"}

        # If we reach here, unhandled content type
        return {"success": False, "error": "Tipo de contenido no soportado"}

    async def finalize_intake(self, user_id: int, chat_id: int) -> Dict:
        """When user signals completion, create dog with accumulated data."""
        session = intake_session_store.get(user_id, chat_id)
        if not session:
            return {"success": False, "error": "No active intake session"}

        # Expect that session.data contains parsed fields for dog creation.
        # For simplicity, we assume the user has sent a structured message that we parsed elsewhere.
        # We'll just take the raw_text and attempt to parse naive key: value.
        raw = session.data.get("raw_text", "")
        parsed = {}
        for line in raw.split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                parsed[k.strip().lower()] = v.strip()

        # Map common keys to our fields (very basic)
        mapping = {
            "nombre": "name",
            "name": "name",
            "raza": "breed_id",  # we would need to look up breed by name; for now skip
            "sexo": "sex",
            "fecha de nacimiento": "birth_date",
            "color": "color",
            "microchip": "microchip",
            "precio": "purchase_price",
            "precio de venta": "sale_price",
        }
        dog_data = {}
        for k, v in parsed.items():
            if k in mapping:
                dog_data[mapping[k]] = v
            else:
                # keep as is; may be ignored
                pass

        # Validate required fields
        required = ["name", "sex", "birth_date", "color", "microchip"]
        for field in required:
            if field not in dog_data:
                intake_session_store.delete(user_id, chat_id)
                return {"success": False, "error": f"Missing required field after parsing: {field}"}

        # Breed lookup: if breed name given, we need to find or create breed.
        # We'll skip for now and assume breed_id is provided numerically.

        # Create dog
        create_result = await self._create_dog(dog_data)
        if not create_result.get("success"):
            intake_session_store.delete(user_id, chat_id)
            return create_result

        dog_id = create_result["dog"]["id"]
        internal_id = create_result["dog"]["internal_id"]

        # TODO: associate media files from session to this dog
        # For each media in session.media_files, call save_uploaded_file and then POST to /dogs/{dog_id}/media
        # We'll implement a simple loop.
        media_success = []
        for mf in session.media_files:
            try:
                meta = save_uploaded_file(
                    file_content=mf["content"],
                    filename=mf["filename"],
                    dog_internal_id=internal_id,
                    purpose=mf["purpose"],
                    uploaded_by=mf["uploaded_by"],
                )
                meta["dog_id"] = dog_id
                media_resp = await self.client.post(f"/dogs/{dog_id}/media", json=meta)
                media_resp.raise_for_status()
                media_success.append(media_resp.json())
            except Exception as e:
                logger.error("failed_to_assoc_media", error=str(e))
                # continue with others

        # Clear session
        intake_session_store.delete(user_id, chat_id)

        logger.info("intake_finalized", user_id=user_id, chat_id=chat_id, dog_id=dog_id)

        return {
            "success": True,
            "dog": create_result["dog"],
            "media_associated": len(media_success),
            "message": f"Perro {internal_id} creado. {len(media_success)} archivos de media asociados."
        }