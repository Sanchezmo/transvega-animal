"""
Adaptador Google Workspace - Integración con Gmail, Drive, Calendar.
"""

from datetime import datetime, timedelta

import httpx
import structlog

logger = structlog.get_logger()


class GoogleWorkspaceClient:
    """Cliente para Google Workspace APIs."""

    def __init__(self, config: dict):
        self.config = config
        self.client_id = config.get("GOOGLE_CLIENT_ID")
        self.client_secret = config.get("GOOGLE_CLIENT_SECRET")
        self.workspace_domain = config.get("GOOGLE_WORKSPACE_DOMAIN", "empresa.es")
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None

    async def authenticate(self) -> bool:
        """Autenticar con OAuth2."""
        # TODO: Implementar flujo OAuth2 completo
        # 1. Si hay refresh_token válido, usarlo
        # 2. Si no, iniciar flujo OAuth2
        return True

    async def _get_access_token(self) -> str:
        """Obtener access token válido."""
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token

        # Refresh token
        # TODO: Implementar refresh
        return self.access_token or ""

    # =========================================================================
    # GMAIL
    # =========================================================================

    async def gmail_list_messages(
        self, query: str = "", max_results: int = 100, label_ids: list[str] = None
    ) -> list[dict]:
        """Listar mensajes de Gmail."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            params = {"q": query, "maxResults": max_results}
            if label_ids:
                params["labelIds"] = label_ids

            resp = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("messages", [])

    async def gmail_get_message(self, message_id: str, format: str = "full") -> dict:
        """Obtener mensaje completo."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": format},
            )
            resp.raise_for_status()
            return resp.json()

    async def gmail_get_attachments(self, message_id: str) -> list[dict]:
        """Obtener adjuntos de un mensaje."""
        await self.gmail_get_message(message_id)

        attachments = []
        # Extraer adjuntos del payload
        # TODO: Implementar extracción de partes MIME

        return attachments

    async def gmail_send_message(self, to: str, subject: str, body: str, attachments: list[dict] = None) -> dict:
        """Enviar email."""
        # TODO: Implementar envío
        return {"success": True, "message_id": "mock"}

    # =========================================================================
    # GOOGLE DRIVE
    # =========================================================================

    async def drive_list_files(self, folder_id: str = "root", query: str = "", max_results: int = 100) -> list[dict]:
        """Listar archivos en Drive."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            params = {"q": f"'{folder_id}' in parents and trashed=false"}
            if query:
                params["q"] += f" and {query}"
            params["pageSize"] = max_results
            params["fields"] = "files(id,name,mimeType,size,modifiedTime,parents,webViewLink)"

            resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("files", [])

    async def drive_upload_file(
        self, file_content: bytes, filename: str, folder_id: str = "root", mime_type: str = None
    ) -> dict:
        """Subir archivo a Drive."""
        # TODO: Implementar upload multipart
        return {"success": True, "file_id": "mock"}

    async def drive_download_file(self, file_id: str) -> bytes:
        """Descargar archivo de Drive."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.content

    async def drive_create_folder(self, name: str, parent_id: str = "root") -> dict:
        """Crear carpeta en Drive."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "name": name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_id],
                },
            )
            resp.raise_for_status()
            return resp.json()

    # =========================================================================
    # GOOGLE CALENDAR
    # =========================================================================

    async def calendar_list_events(
        self, calendar_id: str = "primary", time_min: str = None, time_max: str = None, max_results: int = 100
    ) -> list[dict]:
        """Listar eventos de Calendar."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            params = {"maxResults": max_results, "singleEvents": True, "orderBy": "startTime"}
            if time_min:
                params["timeMin"] = time_min
            if time_max:
                params["timeMax"] = time_max

            resp = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("items", [])

    async def calendar_create_event(self, calendar_id: str = "primary", event_data: dict = None) -> dict:
        """Crear evento en Calendar."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=event_data,
            )
            resp.raise_for_status()
            return resp.json()

    async def calendar_update_event(
        self, calendar_id: str = "primary", event_id: str = None, event_data: dict = None
    ) -> dict:
        """Actualizar evento."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=event_data,
            )
            resp.raise_for_status()
            return resp.json()

    async def calendar_delete_event(self, calendar_id: str = "primary", event_id: str = None) -> bool:
        """Eliminar evento."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code == 204

    # =========================================================================
    # USERS / DIRECTORY
    # =========================================================================

    async def directory_list_users(self, max_results: int = 100) -> list[dict]:
        """Listar usuarios del dominio."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/admin/directory/v1/users",
                headers={"Authorization": f"Bearer {token}"},
                params={"domain": self.workspace_domain, "maxResults": max_results},
            )
            resp.raise_for_status()
            return resp.json().get("users", [])

    async def directory_get_user(self, user_key: str) -> dict:
        """Obtener usuario."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://www.googleapis.com/admin/directory/v1/users/{user_key}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()


class GoogleWorkspaceAdapter:
    """Adaptador de alto nivel para Google Workspace."""

    def __init__(self, config: dict):
        self.client = GoogleWorkspaceClient(config)

    async def process_invoice_emails(self, label: str = "FACTURAS_PROVEEDORES") -> list[dict]:
        """Procesar emails de facturas de proveedores."""
        # 1. Buscar emails con label
        messages = await self.client.gmail_list_messages(label_ids=[label], max_results=50)

        for msg in messages:
            await self.client.gmail_get_message(msg["id"])
            # TODO: Parsear factura
            # attachments = await self.client.gmail_get_attachments(msg["id"])

        return []

    async def backup_dolibarr_documents(self, folder_name: str = "Dolibarr Backups") -> dict:
        """Backup de documentos Dolibarr a Drive."""
        # 1. Buscar/crear carpeta
        folders = await self.client.drive_list_files(
            query=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
        )
        folder_id = folders[0]["id"] if folders else (await self.client.drive_create_folder(folder_name))["id"]

        # 2. Subir archivos
        # TODO: Iterar documentos Dolibarr y subir

        return {"success": True, "folder_id": folder_id, "uploaded": 0}

    async def sync_calendar_appointments(self, appointments: list[dict]) -> dict:
        """Sincronizar citas con Google Calendar."""
        created = 0
        for appt in appointments:
            event = {
                "summary": f"Cita {appt.get('type', 'Cita')} - {appt.get('lead_name', 'Cliente')}",
                "description": appt.get("notes", ""),
                "start": {"dateTime": appt.get("scheduled_at"), "timeZone": "Europe/Madrid"},
                "end": {
                    "dateTime": (
                        datetime.fromisoformat(appt["scheduled_at"])
                        + timedelta(minutes=appt.get("duration_minutes", 30))
                    ).isoformat(),
                    "timeZone": "Europe/Madrid",
                },
                "attendees": [{"email": appt.get("client_email")}, {"email": appt.get("closer_email")}],
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "email", "minutes": 24 * 60}, {"method": "popup", "minutes": 30}],
                },
            }
            await self.client.calendar_create_event(event_data=event)
            created += 1

        return {"success": True, "created": created}
