"""
Agente de Productos - Gestión de expedientes de animales.
"""

from datetime import datetime
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class ProductsAgent:
    """
    Agente de Productos - Gestión de expedientes de animales.

    Responsabilidades:
    - Crear y actualizar borradores de expedientes
    - Detectar campos incompletos
    - Validar coherencia de datos
    - Clasificar imágenes
    - Renombrar archivos
    - Preparar fichas comerciales
    - Detectar documentación pendiente
    - Proponer categorías y etiquetas
    - Preparar el producto para publicación

    No puede:
    - Modificar precios definitivos sin autorización
    - Eliminar expedientes
    - Marcar unilateralmente una venta como finalizada
    - Alterar datos fiscales
    """

    def __init__(self, config: dict):
        self.config = config
        self.agent_id = "products"
        self.agent_name = "Products Agent"
        self.status = "idle"
        self.capabilities = [
            "create_expediente_draft",
            "update_expediente",
            "validate_expediente_data",
            "detect_missing_fields",
            "classify_images",
            "rename_files",
            "prepare_commercial_sheet",
            "detect_pending_docs",
            "propose_categories",
            "prepare_for_publication",
        ]
        self.restrictions = [
            "cannot_modify_final_prices",
            "cannot_delete_expedientes",
            "cannot_finalize_sales",
            "cannot_modify_fiscal_data",
        ]
        self.current_tasks = []
        self.completed_tasks = 0
        self.failed_tasks = 0

    async def start(self):
        """Iniciar agente."""
        logger.info("starting_products_agent")
        # Conectar a cola de tareas, API, etc.

    async def stop(self):
        """Detener agente."""
        pass

    async def process_task(self, task: dict) -> dict:
        """Procesar tarea asignada."""

        handlers = {
            "create_expediente_draft": self._create_expediente_draft,
            "update_expediente": self._update_expediente,
            "validate_expediente": self._validate_expediente,
            "detect_missing_fields": self._detect_missing_fields,
            "classify_images": self._classify_images,
            "prepare_commercial_sheet": self._prepare_commercial_sheet,
            "detect_pending_docs": self._detect_pending_docs,
            "propose_categories": self._propose_categories,
            "prepare_for_publication": self._prepare_for_publication,
        }

        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}

        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}

    async def _create_expediente_draft(self, data: dict) -> dict:
        """Crear borrador de expediente animal."""
        # Validaciones
        for field in ["name", "breed", "sex", "birth_date", "color", "weight_kg", "microchip"]:
            if field not in data:
                return {"success": False, "error": f"Campo requerido faltante: {field}"}

        # Validar microchip (15 dígitos)
        microchip = data.get("microchip", "")
        if not microchip.isdigit() or len(microchip) != 15:
            return {"success": False, "error": "Microchip debe ser 15 dígitos numéricos"}

        # Validar sexo
        if data.get("sex") not in ["M", "H"]:
            return {"success": False, "error": "Sexo debe ser M o H"}

        # Validar peso
        weight = data.get("weight_kg", 0)
        if weight <= 0 or weight > 100:
            return {"success": False, "error": "Peso inválido"}

        # Generar ID interno
        internal_id = f"EXP-{datetime.now().year}-{uuid4().hex[:6].upper()}"

        # Crear expediente (simulado)
        expediente = {
            "id": str(uuid4()),
            "internal_id": internal_id,
            "status": "draft",
            "created_at": datetime.now().isoformat(),
            **data,
        }

        return {
            "success": True,
            "expediente": expediente,
            "message": "Borrador creado exitosamente",
        }

    async def _update_expediente(self, data: dict) -> dict:
        """Actualizar expediente existente."""
        expediente_id = data.get("expediente_id")
        if not expediente_id:
            return {"success": False, "error": "expediente_id requerido"}

        # Verificar restricciones
        updates = data.get("updates", {})

        # Verificar si intenta modificar precio final
        if "sale_price" in updates:
            return {
                "success": False,
                "error": "PRICE_CHANGE_REQUIRES_APPROVAL",
                "message": "Cambio de precio requiere aprobación humana",
            }

        # Verificar si intenta cambiar estado a vendido/entregado
        if "commercial_status" in updates:
            restricted_statuses = ["sold", "delivered", "archived"]
            if updates["commercial_status"] in restricted_statuses:
                return {
                    "success": False,
                    "error": "STATUS_CHANGE_REQUIRES_APPROVAL",
                    "message": f"Cambio a estado {updates['commercial_status']} requiere aprobación",
                }

        # Simular actualización
        return {
            "success": True,
            "message": "Expediente actualizado (borrador)",
            "expediente_id": updates.get("expediente_id"),
        }

    async def _validate_expediente(self, data: dict) -> dict:
        """Validar coherencia de datos del expediente."""
        expediente = data.get("expediente", {})

        validations = {
            "microchip_format": False,
            "age_consistency": False,
            "weight_consistency": False,
            "photos_exist": False,
            "documents_complete": False,
        }

        # Microchip
        microchip = expediente.get("microchip", "")
        validations["microchip_format"] = microchip.isdigit() and len(microchip) == 15

        # Edad vs peso
        if "birth_date" in expediente and "weight_kg" in expediente:
            # Lógica simplificada
            validations["age_consistency"] = True
            validations["weight_consistency"] = True

        # Fotos
        validations["photos_exist"] = len(expediente.get("photos", [])) > 0

        # Documentos
        required_docs = ["vaccines", "passport", "pedigree"]
        validations["documents_complete"] = all(expediente.get(doc) for doc in required_docs)

        all_valid = all(validations.values())

        return {
            "success": True,
            "valid": all_valid,
            "validations": validations,
            "missing": [k for k, v in validations.items() if not v],
        }

    async def _detect_missing_fields(self, data: dict) -> dict:
        """Detectar campos incompletos en expediente."""
        expediente = data.get("expediente", {})

        required = [
            "name",
            "breed",
            "sex",
            "birth_date",
            "color",
            "weight_kg",
            "microchip",
            "breeder_id",
            "breeder_registration",
            "zoological_nucleus",
            "country_origin",
            "sire_name",
            "dam_name",
            "pedigree",
            "vet_status",
            "vaccines",
            "deworming",
            "passport",
            "certificates",
            "photos",
            "purchase_price",
            "sale_price",
            "associated_costs",
        ]

        optional = [
            "place_origin",
            "certificates",
            "videos",
            "associated_costs",
            "reservation_id",
            "order_id",
            "invoice_id",
            "transport_id",
        ]

        missing_required = [f for f in required if not expediente.get(f)]
        missing_optional = [f for f in optional if not expediente.get(f)]

        return {
            "success": True,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "completeness": round((len(required) - len(missing_required)) / len(required) * 100, 1),
        }

    async def _classify_images(self, data: dict) -> dict:
        """Clasificar imágenes del expediente."""
        images = data.get("images", [])

        # TODO: Usar modelo de clasificación de imágenes
        # Por ahora clasificación básica por nombre/orden
        classified = {
            "stacked": [],  # Fotos en pose (stack)
            "movement": [],  # Movimiento
            "portrait": [],  # Retrato
            "details": [],  # Detalles (ojos, dientes, etc.)
            "parents": [],  # Padres
            "documents": [],  # Documentos escaneados
            "other": [],
        }

        for i, img in enumerate(images):
            name = img.get("filename", "").lower()
            if "stack" in name or "pose" in name or i == 0:
                classified["stacked"].append(img)
            elif "mov" in name or "run" in name or "walk" in name:
                classified["movement"].append(img)
            elif "portrait" in name or "face" in name:
                classified["portrait"].append(img)
            elif "detail" in name or "teeth" in name or "eye" in name:
                classified["details"].append(img)
            elif "sire" in name or "dam" in name or "parent" in name:
                classified["parents"].append(img)
            elif "doc" in name or "cert" in name or "pdf" in name:
                classified["documents"].append(img)
            else:
                classified["other"].append(img)

        return {
            "success": True,
            "classified": classified,
            "total": len(images),
        }

    async def _prepare_commercial_sheet(self, data: dict) -> dict:
        """Preparar ficha comercial para publicación."""
        expediente = data.get("expediente", {})

        # Generar título
        title = f"{expediente.get('name', 'Cachorro')} - {expediente.get('breed', 'Raza')} {expediente.get('sex', '')}"

        # Generar descripción
        description = self._generate_description(expediente)

        # Seleccionar mejores fotos
        photos = expediente.get("photos", [])[:10]  # Máx 10

        # Generar hashtags
        hashtags = self._generate_hashtags(expediente)

        return {
            "success": True,
            "commercial_sheet": {
                "title": title[:70],  # Límite Milanuncios
                "description": description,
                "photos": photos,
                "price": expediente.get("sale_price"),
                "hashtags": hashtags,
                "location": expediente.get("place_origin", ""),
                "contact_info": "WhatsApp: +34 XXX XX XX XX",
            },
        }

    def _generate_description(self, exp: dict) -> str:
        """Generar descripción comercial."""
        parts = [
            f"🐾 {exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} busca familia responsable 🇪🇸",
            "",
            "✅ ENTREGA INMEDIATA EN: " + exp.get("place_origin", "España") + " + ENVÍO NACIONAL/INTERNACIONAL",
            "",
            "📋 INCLUIDO EN EL PRECIO:",
            "• Pedigree LOE (tramitado) + FCI Export (si exportación)",
            "• Cartilla vacunal completa (edad adecuada)",
            "• Desparasitación interna/externa al día",
            "• Microchip identificado y certificado",
            "• Certificado veterinario de buena salud",
            "• Contrato de compraventa con GARANTÍAS:",
            "  - Genéticas de por vida (displasia, ojos, corazón, tests ADN)",
            "  - Víricas 14 días",
            "  - Temperamento 1 año",
            "• Kit cachorro: pienso 2kg, juguete, manta con olor madre, guía cuidados",
            "",
            "👨‍👩‍👧‍👦 PADRES VISIBLES EN NUESTRAS INSTALACIONES:",
            f"• Padre: {exp.get('sire_name', 'Campeón')} - {exp.get('sire_titles', 'Títulos')}",
            f"• Madre: {exp.get('dam_name', 'Campeona')} - {exp.get('dam_titles', 'Títulos')}",
            "",
            "🏠 NUESTRO CRIADERO:",
            "• Núcleo zoológico autorizado: " + exp.get("zoological_nucleus", ""),
            "• Licencia cría: " + exp.get("breeder_registration", ""),
            "• Puppy Culture / Avidog desde día 3",
            "• Socialización: niños, ruidos, superficies, otros perros",
            "",
            "🚚 TRANSPORTE:",
            "• Recogida en criadero (recomendado - conoces instalaciones)",
            "• Envío aéreo nacional (IATA) - puerta a puerta 24-48h",
            "• Envío internacional (LatAm/EE.UU.) - gestiones completas",
            "",
            "💰 PRECIO: " + str(exp.get("sale_price", 0)) + "€ (Reserva 30% - Resto a la entrega)",
            "",
            "📩 CONTACTO DIRECTO WHATSAPP: +34 XXX XX XX XX",
            "🌐 WEB COMPLETA: transvega-animal.es/cachorro/{slug}",
            "",
            "#perros #cachorros #"
            + exp.get("breed", "").lower().replace(" ", "")
            + " #pedigree #LOE #FCI #garantia #envio #adopcionresponsable #criaderoselectivo #transvegaanimal",
        ]

        return "\n".join(parts)

    def _generate_hashtags(self, exp: dict) -> list[str]:
        """Generar hashtags para redes sociales."""
        base = [
            "#perros",
            "#cachorros",
            "#adopcionresponsable",
            "#compraresponsable",
            "#bienestaranimal",
            "#transvegaanimal",
            "#criaderoselectivo",
        ]

        breed_tag = "#" + exp.get("breed", "").lower().replace(" ", "")
        location_tag = "#" + exp.get("place_origin", "").lower().replace(" ", "")

        return base + [breed_tag, location_tag, "#pedigree", "#garantia", "#envio"]

    async def _detect_pending_docs(self, data: dict) -> dict:
        """Detectar documentación pendiente."""
        expediente = data.get("expediente", {})

        required_docs = {
            "microchip_cert": "Certificado microchip",
            "vaccination_record": "Cartilla vacunal",
            "deworming_record": "Certificado desparasitación",
            "passport": "Pasaporte UE / Cartilla",
            "pedigree": "Pedigree LOE/FCI",
            "vet_certificate": "Certificado veterinario",
            "genetic_tests": "Tests genéticos (padres)",
            "hip_dysplasia": "Control displasia cadera (padres)",
            "elbow_dysplasia": "Control displasia codo (padres)",
            "eye_certificate": "Certificado oftalmológico (padres)",
            "heart_certificate": "Certificado cardíaco (padres)",
        }

        missing = []
        present = []

        for key, label in required_docs.items():
            if expediente.get(key):
                present.append(label)
            else:
                missing.append(label)

        return {
            "success": True,
            "present": present,
            "missing": missing,
            "completion": round(len(present) / len(required_docs) * 100, 1),
        }

    async def _propose_categories(self, data: dict) -> dict:
        """Proponer categorías y etiquetas."""
        expediente = data.get("expediente", {})

        categories = {
            "primary": "perros",
            "secondary": "cachorros",
            "breed": expediente.get("breed", "").lower().replace(" ", "-"),
            "sex": expediente.get("sex", "").lower(),
            "size": self._estimate_size(expediente.get("breed", ""), expediente.get("weight_kg", 0)),
            "age_group": "cachorro",
            "purpose": "companion",  # show, breeding, sport, companion
            "tags": ["pedigree", "LOE", "FCI", "guaranteed", "transport"],
        }

        return {"success": True, "categories": categories}

    def _estimate_size(self, breed: str, weight: float) -> str:
        """Estimar tamaño adulto."""
        if weight > 30:
            return "large"
        elif weight > 15:
            return "medium"
        elif weight > 8:
            return "small"
        return "toy"

    async def _prepare_for_publication(self, data: dict) -> dict:
        """Preparar expediente para publicación."""
        expediente_id = data.get("expediente_id")
        expediente = data.get("expediente", {})
        platforms = data.get("platforms", ["web", "milanuncios"])

        # Verificar estado
        # expediente = await get_expediente(expediente_id)
        # if expediente.commercial_status != "available":
        #     return {"success": False, "error": "Solo expedientes 'available' pueden publicarse"}

        # Verificar documentación completa
        # docs = await self._detect_pending_docs({"expediente": expediente})
        # if docs["missing"]:
        #     return {"success": False, "error": "Documentación incompleta", "missing": docs["missing"]}

        # Preparar fichas por plataforma
        sheets = {}
        for platform in platforms:
            sheets[platform] = await self._prepare_commercial_sheet(
                {
                    "expediente": expediente,
                    "platform": platform,
                }
            )

        return {
            "success": True,
            "expediente_id": expediente_id,
            "platforms": platforms,
            "sheets": sheets,
            "ready_for_approval": True,
        }


# Instancia global
_products_agent = None


def get_products_agent(config: dict | None = None):
    global _products_agent
    if _products_agent is None:
        _products_agent = ProductsAgent(config or {})
    return _products_agent


async def start_products_agent(config: dict | None = None):
    agent = get_products_agent(config)
    await agent.start()
    return agent
