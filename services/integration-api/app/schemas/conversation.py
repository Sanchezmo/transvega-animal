"""
Esquemas para gestión de conversaciones de Telegram.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowType(StrEnum):
    """Tipo de workflow activo."""

    NONE = "none"
    SUPPLIER_INVOICE = "supplier_invoice"
    DOG_MANAGEMENT = "dog_management"
    # Future workflows (not active yet)
    DOLIBARR_QUERY = "dolibarr_query"
    TRANSPORT = "transport"
    PUBLICATION = "publication"


class WorkflowStep(StrEnum):
    """Pasos del workflow según el tipo."""

    # Pasos genéricos
    NONE = "none"
    AWAITING_WORKFLOW_SELECTION = "awaiting_workflow_selection"

    # Supplier Invoice workflow
    INVOICE_AWAITING_DOCUMENT = "invoice_awaiting_document"
    INVOICE_PROCESSING = "invoice_processing"
    INVOICE_AWAITING_SUPPLIER_CONFIRMATION = "invoice_awaiting_supplier_confirmation"
    INVOICE_AWAITING_APPROVAL = "invoice_awaiting_approval"
    INVOICE_AWAITING_CORRECTION = "invoice_awaiting_correction"
    INVOICE_CREATING_DOLIBARR = "invoice_creating_dolibarr"
    INVOICE_COMPLETED = "invoice_completed"
    INVOICE_CANCELLED = "invoice_cancelled"
    INVOICE_FAILED = "invoice_failed"

    # Dog Management workflow
    DOG_INTAKE = "dog_intake"
    DOG_AWAITING_NAME = "dog_awaiting_name"
    DOG_AWAITING_BREED = "dog_awaiting_breed"
    DOG_AWAITING_SEX = "dog_awaiting_sex"
    DOG_AWAITING_BIRTH_DATE = "dog_awaiting_birth_date"
    DOG_AWAITING_COLOR = "dog_awaiting_color"
    DOG_AWAITING_MICROCHIP = "dog_awaiting_microchip"
    DOG_AWAITING_PURCHASE_PRICE = "dog_awaiting_purchase_price"
    DOG_AWAITING_SALE_PRICE = "dog_awaiting_sale_price"
    DOG_AWAITING_MEDIA = "dog_awaiting_media"
    DOG_COMPLETED = "dog_completed"
    DOG_CANCELLED = "dog_cancelled"

    # Future workflows
    DOLIBARR_QUERY_AWAITING_QUERY = "dolibarr_query_awaiting_query"


class ConversationSession(BaseModel):
    """Estado de una conversación de Telegram."""

    model_config = ConfigDict(from_attributes=True)

    # Identificación
    session_id: UUID
    telegram_user_id: int
    telegram_chat_id: int

    # Workflow actual
    workflow_type: WorkflowType = WorkflowType.NONE
    workflow_step: WorkflowStep = WorkflowStep.AWAITING_WORKFLOW_SELECTION

    # Contexto del workflow (datos específicos)
    context: dict[str, Any] = Field(default_factory=dict)

    # Metadatos
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    # Metadatos de Telegram
    last_update_id: int | None = None
    last_message_id: int | None = None


class ConversationSessionCreate(BaseModel):
    """Para crear una nueva sesión."""

    telegram_user_id: int
    telegram_chat_id: int
    workflow_type: WorkflowType = WorkflowType.NONE
    workflow_step: WorkflowStep = WorkflowStep.AWAITING_WORKFLOW_SELECTION
    context: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


class ConversationSessionUpdate(BaseModel):
    """Para actualizar una sesión existente."""

    workflow_type: WorkflowType | None = None
    workflow_step: WorkflowStep | None = None
    context: dict[str, Any] | None = None
    expires_at: datetime | None = None
    last_update_id: int | None = None
    last_message_id: int | None = None


class ConversationSessionResponse(ConversationSession):
    """Respuesta con sesión completa."""

    pass


# =============================================================================
# Teclados inline para Telegram
# =============================================================================


class InlineKeyboardButton(BaseModel):
    """Botón de teclado inline de Telegram."""

    text: str
    callback_data: str
    url: str | None = None


class InlineKeyboardMarkup(BaseModel):
    """Teclado inline de Telegram."""

    inline_keyboard: list[list[InlineKeyboardButton]]


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Teclado del menú principal."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📄 Introducir factura de gasto",
                    callback_data="workflow:supplier_invoice",
                ),
                InlineKeyboardButton(
                    text="🐶 Gestionar perro",
                    callback_data="workflow:dog_management",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❓ Ayuda",
                    callback_data="action:help",
                ),
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data="action:cancel",
                ),
            ],
        ]
    )


def get_invoice_approval_keyboard() -> InlineKeyboardMarkup:
    """Teclado para aprobación de factura."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ APROBAR",
                    callback_data="invoice:approve",
                ),
                InlineKeyboardButton(
                    text="✏️ CORREGIR",
                    callback_data="invoice:correct",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ CANCELAR",
                    callback_data="invoice:cancel",
                ),
            ],
        ]
    )


def get_correction_keyboard() -> InlineKeyboardMarkup:
    """Teclado para correcciones comunes."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Total",
                    callback_data="correct:total",
                ),
                InlineKeyboardButton(
                    text="📦 Categoría",
                    callback_data="correct:category",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📋 Número factura",
                    callback_data="correct:invoice_number",
                ),
                InlineKeyboardButton(
                    text="🏢 Proveedor",
                    callback_data="correct:supplier",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 IVA",
                    callback_data="correct:vat",
                ),
                InlineKeyboardButton(
                    text="↩️ Volver",
                    callback_data="invoice:back_to_approval",
                ),
            ],
        ]
    )


def get_supplier_not_found_keyboard() -> InlineKeyboardMarkup:
    """Teclado cuando no se encuentra el proveedor."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ CREAR PROVEEDOR",
                    callback_data="supplier:create",
                ),
                InlineKeyboardButton(
                    text="✏️ CORREGIR",
                    callback_data="supplier:correct",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ CANCELAR",
                    callback_data="supplier:cancel",
                ),
            ],
        ]
    )


def get_dog_management_keyboard() -> InlineKeyboardMarkup:
    """Teclado para gestión de perros."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Nuevo perro",
                    callback_data="dog:new",
                ),
                InlineKeyboardButton(
                    text="📋 Listar perros",
                    callback_data="dog:list",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Volver al menú",
                    callback_data="action:menu",
                ),
            ],
        ]
    )


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Teclado simple de cancelar."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data="action:cancel",
                ),
            ],
        ]
    )


def get_help_text() -> str:
    """Texto de ayuda."""
    return (
        "🤖 <b>Hermes - Asistente Transvega</b>\n\n"
        "Comandos disponibles:\n"
        "• <code>/start</code> - Iniciar / Menú principal\n"
        "• <code>/menu</code> - Mostrar menú principal\n"
        "• <code>/cancel</code> - Cancelar operación actual\n"
        "• <code>/status</code> - Ver estado actual\n\n"
        "Workflows disponibles:\n"
        "• 📄 <b>Factura de gasto</b> - Procesar factura de proveedor\n"
        "• 🐶 <b>Gestionar perro</b> - Registrar/gestionar perros\n\n"
        "Envía un documento o foto para iniciar el workflow correspondiente, "
        "o usa el menú para elegir."
    )


def get_workflow_selection_text() -> str:
    """Texto para selección de workflow."""
    return "🤖 <b>Hermes - Asistente Transvega</b>\n\n¿Qué quieres hacer?\n\nSelecciona una opción:"


def get_invoice_approval_text(summary: dict) -> str:
    """Texto para aprobación de factura."""
    validation_status = summary.get("validation_status", "OK")
    return (
        f"📄 <b>FACTURA PROVEEDOR</b>\n\n"
        f"Proveedor: {summary.get('supplier_name', 'N/A')}\n"
        f"CIF/NIF: {summary.get('supplier_tax_id', 'N/A')}\n"
        f"Factura: {summary.get('invoice_number', 'N/A')}\n"
        f"Fecha: {summary.get('invoice_date', 'N/A')}\n"
        f"Categoría: {summary.get('expense_category', 'pendiente')}\n"
        f"Base: {summary.get('subtotal', 0):.2f} {summary.get('currency', 'EUR')}\n"
        f"IVA: {summary.get('tax_total', 0):.2f} {summary.get('currency', 'EUR')}\n"
        f"Retención: {summary.get('withholding_total', 0):.2f} {summary.get('currency', 'EUR')}\n"
        f"TOTAL: {summary.get('total', 0):.2f} {summary.get('currency', 'EUR')}\n\n"
        f"Validación: {validation_status}\n\n"
        f"Opciones:"
    )


def get_supplier_not_found_text(tax_id: str) -> str:
    """Texto cuando no se encuentra proveedor."""
    return (
        f"⚠️ <b>Proveedor no encontrado</b>\n\n"
        f"No existe proveedor con CIF/NIF: <code>{tax_id}</code> en Dolibarr.\n\n"
        f"Opciones:"
    )


def get_correction_prompt_text() -> str:
    """Texto para pedir corrección."""
    return (
        "✏️ <b>Indica la corrección</b>\n\n"
        "Ejemplos:\n"
        "• <code>El total son 125,40</code>\n"
        "• <code>Es combustible</code>\n"
        "• <code>El IVA es 10%</code>\n"
        "• <code>El proveedor es Distribuciones X</code>\n"
        "• <code>El número es FAC-2024-002</code>\n\n"
        "O usa los botones para correcciones comunes:"
    )


def get_cancelled_text() -> str:
    """Texto de operación cancelada."""
    return "❌ Operación cancelada."


def get_help_message() -> str:
    """Mensaje de ayuda completo."""
    return get_help_text()
