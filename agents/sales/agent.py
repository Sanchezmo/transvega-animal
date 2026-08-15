"""
Agente Comercial - Gestión de leads, oportunidades y ventas.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class SalesAgent:
    """
    Agente Comercial - Gestión de leads, oportunidades y ventas.

    Responsabilidades:
    - Registrar consultas
    - Crear clientes potenciales
    - Asociar cada consulta con un expediente
    - Clasificar el nivel de interés
    - Responder preguntas frecuentes
    - Preparar respuestas
    - Solicitar datos faltantes
    - Proponer citas
    - Crear eventos en Google Calendar
    - Preparar presupuestos
    - Realizar seguimiento
    - Registrar todas las comunicaciones

    No puede:
    - Confirmar una venta definitiva
    - Aceptar descuentos no autorizados
    - Prometer condiciones no registradas
    - Acceder a información de otros clientes sin necesidad
    """

    def __init__(self, config: dict):
        self.config = config
        self.agent_id = "sales"
        self.agent_name = "Sales Agent"
        self.capabilities = [
            "register_inquiry",
            "create_lead",
            "qualify_lead",
            "assign_lead",
            "create_opportunity",
            "create_quote",
            "create_order",
            "create_reservation",
            "schedule_appointment",
            "send_follow_up",
            "answer_faq",
            "request_missing_data",
            "track_communication",
        ]
        self.restrictions = [
            "cannot_confirm_sale",
            "cannot_apply_unauthorized_discounts",
            "cannot_promise_unregistered_conditions",
            "cannot_access_other_clients_data",
        ]

    async def start(self):
        """Iniciar agente."""
        logger.info("starting_sales_agent")

    async def stop(self):
        """Detener agente."""
        pass

    async def process_task(self, task: dict) -> dict:
        """Procesar tarea asignada."""

        handlers = {
            "register_inquiry": self._register_inquiry,
            "create_lead": self._create_lead,
            "qualify_lead": self._qualify_lead,
            "assign_lead": self._assign_lead,
            "create_opportunity": self._create_opportunity,
            "create_quote": self._create_quote,
            "create_order": self._create_order,
            "create_reservation": self._create_reservation,
            "schedule_appointment": self._schedule_appointment,
            "send_follow_up": self._send_follow_up,
            "answer_faq": self._answer_faq,
            "request_missing_data": self._request_missing_data,
            "track_communication": self._track_communication,
        }

        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}

        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}

    async def _register_inquiry(self, data: dict) -> dict:
        """Registrar consulta entrante (web, WhatsApp, email, teléfono)."""
        inquiry_data = data.get("inquiry", {})

        # Validar datos mínimos
        required = ["first_name", "last_name", "email", "phone", "country"]
        for field in required:
            if not inquiry_data.get(field):
                return {"success": False, "error": f"Campo requerido faltante: {field}"}

        # Detectar fuente
        source = inquiry_data.get("source", "web")
        valid_sources = [
            "web",
            "whatsapp",
            "email",
            "phone",
            "milanuncios",
            "facebook",
            "instagram",
            "tiktok",
            "referral",
            "show",
        ]
        if source not in valid_sources:
            source = "web"

        # Crear lead inicial
        lead = {
            "id": str(uuid4()),
            "first_name": inquiry_data["first_name"],
            "last_name": inquiry_data["last_name"],
            "email": inquiry_data["email"],
            "phone": inquiry_data["phone"],
            "country": inquiry_data["country"],
            "city": inquiry_data.get("city"),
            "language": inquiry_data.get("language", "es"),
            "source": source,
            "source_campaign": inquiry_data.get("campaign"),
            "source_keyword": inquiry_data.get("keyword"),
            "utm_params": inquiry_data.get("utm_params", {}),
            "referrer_url": inquiry_data.get("referrer_url"),
            "status": "new",
            "score": 0,
            "temperature": "cold",
            "interested_expediente_ids": inquiry_data.get("expediente_ids", []),
            "interested_litter_ids": inquiry_data.get("litter_ids", []),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        # Auto-calificar si hay expediente de interés
        if inquiry_data.get("expediente_ids"):
            lead = await self._auto_qualify_from_expediente(lead, inquiry_data["expediente_ids"][0])

        # Guardar en BD
        # lead_id = await db.create_lead(lead)

        # Asignar closer automáticamente
        assigned_closer = await self._auto_assign_closer(lead)

        # Enviar respuesta automática inicial
        await self._send_initial_response(lead)

        # Notificar al closer asignado
        await self._notify_closer(assigned_closer, lead)

        return {
            "success": True,
            "lead_id": lead["id"],
            "status": lead["status"],
            "score": lead["score"],
            "temperature": lead["temperature"],
            "assigned_closer": assigned_closer,
            "message": "Consulta registrada, lead creado y asignado",
        }

    async def _auto_qualify_from_expediente(self, lead: dict, expediente_id: str) -> dict:
        """Auto-calificar lead basado en expediente de interés."""
        # Obtener datos del expediente
        # expediente = await dolibarr.get_expediente(expediente_id)

        # Simulación
        expediente = {
            "sale_price": 1500,
            "breed": "Golden Retriever",
            "commercial_status": "available",
        }

        # Calcular score basado en expediente
        score = 30  # Base por interés en expediente específico

        if expediente.get("commercial_status") == "available":
            score += 20

        # Verificar presupuesto declarativo vs precio
        # (en real, preguntaríamos presupuesto)

        lead["interested_expediente_ids"] = [expediente_id]
        lead["score"] = min(100, score)
        lead["temperature"] = self._calculate_temperature(score)
        lead["intent"] = (
            "show_breeding" if expediente.get("breed") in ["Golden Retriever", "Pastor Alemán"] else "companion"
        )

        return lead

    def _calculate_temperature(self, score: int) -> str:
        if score >= 81:
            return "burning"
        elif score >= 61:
            return "hot"
        elif score >= 31:
            return "warm"
        return "cold"

    async def _auto_assign_closer(self, lead: dict) -> str:
        """Asignar closer automáticamente según país, score, especialidad."""
        country = lead.get("country", "ES")
        _ = lead.get("temperature", "cold")

        # Lógica de asignación
        closers_by_country = {
            "ES": ["closer_es_1", "closer_es_2"],
            "MX": ["closer_mx_1"],
            "CO": ["closer_co_1"],
            "AR": ["closer_ar_1"],
            "US": ["closer_us_1", "closer_us_2"],
            "PT": ["closer_pt_1"],
            "default": ["closer_int_1"],
        }

        closers = closers_by_country.get(country, closers_by_country["default"])

        # Priorizar closer con menos carga para leads hot/burning
        if lead.get("temperature") in ["hot", "burning"]:
            return closers[0]

        return closers[0]  # Simplificado

    async def _send_initial_response(self, lead: dict):
        """Enviar respuesta automática inicial."""
        # TODO: Enviar via WhatsApp/Email según preferencia
        logger.info("initial_response_sent", lead_id=lead["id"], channel="whatsapp")

    async def _notify_closer(self, closer_id: str, lead: dict):
        """Notificar al closer asignado."""
        # TODO: Enviar notificación por Telegram/Slack/Email
        logger.info("closer_notified", closer_id=closer_id, lead_id=lead["id"])

    async def _create_lead(self, data: dict) -> dict:
        """Crear lead manualmente (desde panel)."""
        lead_data = data.get("lead", {})

        # Validar
        required = ["first_name", "last_name", "email", "phone", "country"]
        for field in required:
            if not lead_data.get(field):
                return {"success": False, "error": f"Campo requerido: {field}"}

        lead = {
            "id": str(uuid4()),
            "status": "new",
            "score": 0,
            "temperature": "cold",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            **lead_data,
        }

        # Asignar closer
        assigned_closer = await self._auto_assign_closer(lead)
        lead["assigned_closer"] = assigned_closer

        # Guardar en BD
        # lead_id = await db.create_lead(lead)

        return {
            "success": True,
            "lead_id": lead["id"],
            "assigned_closer": assigned_closer,
            "message": "Lead creado y asignado",
        }

    async def _qualify_lead(self, data: dict) -> dict:
        """Calificar lead manualmente."""
        lead_id = data.get("lead_id")
        qualification = data.get("qualification", {})

        # Actualizar campos
        updates = {}

        if "score" in qualification:
            score = qualification["score"]
            if not 0 <= score <= 100:
                return {"success": False, "error": "Score debe estar entre 0 y 100"}
            updates["score"] = score
            updates["temperature"] = self._calculate_temperature(score)

        if "intent" in qualification:
            updates["intent"] = qualification["intent"]

        if "budget_min" in qualification:
            updates["budget_min"] = qualification["budget_min"]
        if "budget_max" in qualification:
            updates["budget_max"] = qualification["budget_max"]

        if "timeline" in qualification:
            updates["timeline"] = qualification["timeline"]

        if "status" in qualification:
            valid_statuses = [
                "new",
                "contacted",
                "qualified",
                "proposal_sent",
                "negotiation",
                "won",
                "lost",
                "nurturing",
            ]
            if qualification["status"] not in valid_statuses:
                return {"success": False, "error": "Estado inválido"}
            updates["status"] = qualification["status"]

        # Perfil hogar
        profile_fields = [
            "housing_type",
            "hours_alone",
            "has_children",
            "children_ages",
            "has_dogs",
            "current_dogs",
            "has_cats",
            "experience_level",
            "show_experience",
        ]
        for field in profile_fields:
            if field in qualification:
                updates[field] = qualification[field]

        # Recalcular score si cambió perfil
        if any(f in updates for f in ["budget_max", "timeline", "experience_level", "housing_type"]):
            updates["score"] = self._recalculate_score(updates, {})
            updates["temperature"] = self._calculate_temperature(updates["score"])

        updates["updated_at"] = datetime.now().isoformat()

        # Actualizar en BD
        # await db.update_lead(lead_id, updates)

        return {
            "success": True,
            "lead_id": lead_id,
            "updated_fields": list(updates.keys()),
            "new_score": updates.get("score"),
            "new_temperature": updates.get("temperature"),
        }

    def _recalculate_score(self, qualification: dict, existing: dict) -> int:
        """Recalcular score basado en datos de calificación."""
        score = 0

        # Presupuesto (max 25)
        if qualification.get("budget_max"):
            budget = qualification["budget_max"]
            if budget >= 8000:
                score += 25
            elif budget >= 5000:
                score += 20
            elif budget >= 3000:
                score += 15
            elif budget >= 1500:
                score += 10
            else:
                score += 5

        # Timeline (max 15)
        timeline_scores = {"inmediato": 15, "1-3_meses": 12, "3-6_meses": 8, "explorando": 3}
        score += timeline_scores.get(qualification.get("timeline", "explorando"), 3)

        # Intención (max 20)
        intent_scores = {"show_breeding": 20, "breeding_program": 18, "companion": 15, "gift": 5, "unsure": 5}
        score += intent_scores.get(qualification.get("intent", "unsure"), 5)

        # Experiencia (max 10)
        exp_scores = {"criador": 10, "handler": 10, "tenia_perro": 7, "primera_vez": 5}
        score += exp_scores.get(qualification.get("experience_level", "primera_vez"), 5)

        # Vivienda (max 10)
        housing_scores = {"finca": 10, "casa_jardin": 10, "piso": 5}
        score += housing_scores.get(qualification.get("housing_type", "piso"), 5)

        # Fuente (max 10)
        source_scores = {"referral_client": 10, "referral_show": 10, "google_search": 9, "meta_ads": 7, "organic": 8}
        score += source_scores.get(qualification.get("source", "organic"), 3)

        # Bonificaciones
        if qualification.get("show_experience"):
            score += 5
        if qualification.get("has_dogs") and qualification.get("experience_level") in ["criador", "handler"]:
            score += 3

        return min(100, score)

    async def _assign_lead(self, data: dict) -> dict:
        """Reasignar lead a otro closer."""
        lead_id = data.get("lead_id")
        new_closer_id = data.get("closer_id")
        reason = data.get("reason", "Reasignación manual")

        # Verificar que closer existe
        # closer = await db.get_closer(new_closer_id)
        # if not closer:
        #     return {"success": False, "error": "Closer no encontrado"}

        # Actualizar lead
        # await db.update_lead(lead_id, {"assigned_closer": new_closer_id, "updated_at": datetime.now().isoformat()})

        # Notificar a ambos closers
        # await self._notify_closer_transfer(old_closer, new_closer_id, lead_id, reason)

        return {
            "success": True,
            "lead_id": lead_id,
            "new_closer": new_closer_id,
            "reason": reason,
        }

    async def _create_opportunity(self, data: dict) -> dict:
        """Crear oportunidad de venta desde lead + expediente."""
        lead_id = data.get("lead_id")
        expediente_id = data.get("expediente_id")
        estimated_value = data.get("estimated_value")

        # Validar lead y expediente
        # lead = await db.get_lead(lead_id)
        # expediente = await dolibarr.get_expediente(expediente_id)

        opportunity = {
            "id": str(uuid4()),
            "lead_id": lead_id,
            "expediente_id": expediente_id,
            "estimated_value": estimated_value,
            "probability": 50,
            "stage": "proposal",
            "expected_close_date": (datetime.now() + timedelta(days=14)).date().isoformat(),
            "created_at": datetime.now().isoformat(),
        }

        # opportunity_id = await db.create_opportunity(opportunity)

        # Actualizar lead
        # await db.update_lead(lead_id, {"status": "proposal_sent", "opportunity_id": opportunity["id"]})

        # Generar presupuesto automático
        quote = await self._generate_quote(
            {
                "expediente_id": expediente_id,
                "client_id": "client_from_lead",
                "include_transport": True,
                "include_docs": True,
            }
        )

        return {
            "success": True,
            "opportunity_id": opportunity["id"],
            "quote_id": quote.get("quote_id"),
            "estimated_value": estimated_value,
        }

    async def _create_quote(self, data: dict) -> dict:
        """Generar presupuesto para cliente."""
        expediente_id = data.get("expediente_id")
        client_id = data.get("client_id")
        include_transport = data.get("include_transport", True)
        include_docs = data.get("include_docs", True)
        valid_days = data.get("valid_days", 30)

        # Obtener datos del expediente
        # expediente = await dolibarr.get_expediente(expediente_id)

        # Simulación
        expediente = {
            "sale_price": 1500,
            "breed": "Golden Retriever",
            "internal_id": "EXP-2024-000001",
        }

        lines = [
            {
                "description": f"Cachorro {expediente['breed']} LOE - {expediente['internal_id']}",
                "qty": 1,
                "unit_price": expediente["sale_price"],
                "vat_rate": 21.0,
            }
        ]

        if include_transport:
            lines.append(
                {
                    "description": "Transporte nacional (puerta a puerta)",
                    "qty": 1,
                    "unit_price": 300.00,
                    "vat_rate": 21.0,
                }
            )

        if include_docs:
            lines.append(
                {
                    "description": "Gestión documentación (LOE, FCI, certificado vet, CITES si aplica)",
                    "qty": 1,
                    "unit_price": 250.00,
                    "vat_rate": 21.0,
                }
            )

        # Calcular totales
        from decimal import Decimal

        total_ht = sum(Decimal(str(line["unit_price"])) for line in lines)
        total_tva = sum(Decimal(str(line["unit_price"])) * Decimal("0.21") for line in lines)
        total_ttc = total_ht + total_tva

        quote = {
            "id": str(uuid4()),
            "expediente_id": expediente_id,
            "client_id": client_id,
            "lines": lines,
            "total_ht": float(total_ht),
            "total_tva": float(total_tva),
            "total_ttc": float(total_ttc),
            "valid_until": (datetime.now() + timedelta(days=valid_days)).date().isoformat(),
            "status": "draft",
            "created_at": datetime.now().isoformat(),
        }

        # quote_id = await db.create_quote(quote)

        return {
            "success": True,
            "quote_id": quote["id"],
            "total_ht": float(total_ht),
            "total_tva": float(total_tva),
            "total_ttc": float(total_ttc),
            "valid_until": quote["valid_until"],
        }

    async def _create_order(self, data: dict) -> dict:
        """Crear pedido de venta confirmado."""
        expediente_id = data.get("expediente_id")
        client_id = data.get("client_id")
        lines = data.get("lines", [])

        # Validar: expediente disponible, cliente verificado

        order = {
            "id": str(uuid4()),
            "expediente_id": expediente_id,
            "client_id": client_id,
            "lines": lines,
            "status": "confirmed",
            "created_at": datetime.now().isoformat(),
        }

        # order_id = await db.create_order(order)

        # Actualizar expediente
        # await dolibarr.update_expediente(expediente_id, {"commercial_status": "paid", "client_id": client_id})

        # Crear factura automática
        # await invoicing_agent.create_invoice({...})

        return {
            "success": True,
            "order_id": order["id"],
            "message": "Pedido creado, factura generada automáticamente",
        }

    async def _create_reservation(self, data: dict) -> dict:
        """Crear reserva (requiere aprobación si > 50% o condiciones especiales)."""
        expediente_id = data.get("expediente_id")
        lead_id = data.get("lead_id")
        deposit_amount = data.get("deposit_amount")
        deposit_percent = data.get("deposit_percent", 30)

        # Validar
        if deposit_percent < 20 or deposit_percent > 50:
            return {"success": False, "error": "Porcentaje de reserva debe estar entre 20% y 50%"}

        # Verificar expediente disponible
        # expediente = await dolibarr.get_expediente(expediente_id)
        # if expediente.commercial_status != "available":
        #     return {"success": False, "error": "Expediente no disponible para reserva"}

        # Verificar lead cualificado
        # lead = await db.get_lead(lead_id)
        # if lead.temperature not in ["hot", "burning"]:
        #     return {"success": False, "error": "Lead no suficientemente calificado para reserva"}

        # Verificar si requiere aprobación
        requires_approval = deposit_percent > 50 or deposit_amount > 1000

        if requires_approval:
            # Solicitar aprobación
            # approval_id = await approval_service.request({
            #     "action": "confirm_reservation",
            #     "resource_type": "reservation",
            #     "resource_id": expediente_id,
            #     "reason": f"Reserva {deposit_percent}% ({deposit_amount}€)",
            #     "current_state": {"status": "available"},
            #     "proposed_state": {"status": "reserved", "deposit_percent": deposit_percent},
            # })
            approval_id = str(uuid4())  # Simulated

            return {
                "success": True,
                "message": "Reserva creada, pendiente de aprobación",
                "approval_id": approval_id,
                "status": "pending_approval",
            }

        # Crear reserva directamente
        reservation = {
            "id": str(uuid4()),
            "expediente_id": expediente_id,
            "lead_id": lead_id,
            "deposit_amount": deposit_amount,
            "deposit_percent": deposit_percent,
            "status": "confirmed",
            "created_at": datetime.now().isoformat(),
        }

        # reservation_id = await db.create_reservation(reservation)

        # Actualizar expediente
        # await dolibarr.update_expediente(expediente_id, {"commercial_status": "reserved"})

        return {
            "success": True,
            "reservation_id": reservation["id"],
            "status": "confirmed",
            "message": "Reserva confirmada",
        }

    async def _schedule_appointment(self, data: dict) -> dict:
        """Agendar cita (videollamada, visita criadero, recogida)."""
        lead_id = data.get("lead_id")
        appointment_type = data.get("type")  # videocall, visit, pickup
        scheduled_at = data.get("scheduled_at")
        duration_minutes = data.get("duration_minutes", 30)
        notes = data.get("notes", "")

        # Validar
        if appointment_type not in ["videocall", "visit", "pickup"]:
            return {"success": False, "error": "Tipo de cita inválido"}

        # Crear evento en Google Calendar
        # event = await google_calendar.create_event({
        #     "summary": f"Cita {appointment_type} - Lead {lead_id}",
        #     "start": scheduled_at,
        #     "duration_minutes": duration_minutes,
        #     "description": notes,
        #     "attendees": [lead_email, closer_email],
        # })

        appointment = {
            "id": str(uuid4()),
            "lead_id": lead_id,
            "type": appointment_type,
            "scheduled_at": scheduled_at,
            "duration_minutes": duration_minutes,
            "notes": notes,
            "status": "scheduled",
            "calendar_event_id": "google_event_id",
            "created_at": datetime.now().isoformat(),
        }

        # appointment_id = await db.create_appointment(appointment)

        return {
            "success": True,
            "appointment_id": appointment["id"],
            "calendar_link": "https://calendar.google.com/event/...",
            "message": f"Cita {appointment_type} agendada para {scheduled_at}",
        }

    async def _send_follow_up(self, data: dict) -> dict:
        """Enviar seguimiento a lead/cliente."""
        _ = data.get("lead_id")
        template = data.get("template", "generic")
        channel = data.get("channel", "whatsapp")
        custom_message = data.get("message")

        templates = {
            "generic": "Hola {name}, ¿sigues interesado en {breed}? Estoy aquí para ayudarte.",
            "after_quote": "Hola {name}, te envié el presupuesto para {breed}. ¿Tienes dudas?",
            "after_visit": "Hola {name}, ¡qué bien verte ayer! ¿Qué te pareció {name_dog}?",
            "post_delivery": "Hola {name}, ¿cómo se adapta {name_dog}? Aquí estoy para lo que necesites.",
            "reengagement": "Hola {name}, tenemos nueva camada de {breed}. ¿Te interesa verla?",
        }

        _ = custom_message or templates.get(template, templates["generic"])

        # Obtener datos del lead
        # lead = await db.get_lead(lead_id)

        # Formatear mensaje
        # message = message.format(
        #     name=lead.first_name,
        #     breed=lead.preferred_breeds[0] if lead.preferred_breeds else "cachorro",
        # )

        # Enviar por canal
        # if channel == "whatsapp":
        #     await whatsapp.send(lead.phone, message)
        # elif channel == "email":
        #     await email.send(lead.email, "Seguimiento Transvega", message)

        # Registrar comunicación
        # await db.track_communication(lead_id, channel, message, "outbound")

        return {
            "success": True,
            "message": "Seguimiento enviado",
            "channel": channel,
            "template": template,
        }

    async def _answer_faq(self, data: dict) -> dict:
        """Responder pregunta frecuente automáticamente."""
        _ = data.get("question", "").lower()

        faqs = {
            "precio": (
                "Los precios varían por raza, línea de sangre y servicios incluidos. "
                "Van desde 1.200€ a 3.000€ + transporte."
            ),
            "transporte": (
                "Ofrecemos transporte nacional (24-48h) e internacional (3-7 días). "
                "Vehículos IATA, conductores certificados."
            ),
            "garantia": (
                "Garantía genética de por vida (displasia, ojos, corazón, ADN), víricas 14 días, temperamento 1 año."
            ),
            "pago": "Reserva 30% al confirmar, resto a la entrega. Transferencia, tarjeta o financiación.",
            "documentacion": (
                "Entregamos: LOE/FCI, cartilla vacunal, microchip, certificado vet, contrato, guía, kit cachorro."
            ),
            "visita": (
                "¡Claro! Agendamos visita al criadero (presencial o videollamada). "
                "Verás padres, instalaciones y cachorros."
            ),
            "exportacion": (
                "Exportamos a LatAm, EE.UU., Europa. Gestionamos CITES, certificado zoosanitario, trámites aduaneros."
            ),
            "pago_fraccionado": "Ofrecemos financiación hasta 24 meses sin intereses (sujeto a aprobación).",
        }

        # Búsqueda simple por palabras clave
        for keyword, answer in faqs.items():
            if keyword in data.get("question", "").lower():
                return {"success": True, "answer": answer, "matched": keyword}

        return {
            "success": True,
            "answer": "Esa es una excelente pregunta. Un asesor te contactará en breve con todos los detalles.",
            "matched": None,
            "escalate": True,
        }

    async def _request_missing_data(self, data: dict) -> dict:
        """Solicitar datos faltantes al lead."""
        _ = data.get("lead_id")
        missing_fields = data.get("missing_fields", [])

        field_labels = {
            "budget_max": "presupuesto máximo",
            "timeline": "cuándo quieres recibirlo",
            "housing_type": "tipo de vivienda",
            "hours_alone": "horas que el perro estaría solo",
            "has_children": "si hay niños en casa",
            "experience_level": "experiencia previa con perros",
        }

        _ = "Para poder ayudarte mejor, necesito saber: " + ", ".join(field_labels.get(f, f) for f in missing_fields)

        # Enviar por WhatsApp/Email
        # await whatsapp.send(lead.phone, message)

        return {
            "success": True,
            "message": "Solicitud de datos enviada",
            "requested_fields": missing_fields,
        }

    async def _track_communication(self, data: dict) -> dict:
        """Registrar comunicación con lead/cliente."""
        lead_id = data.get("lead_id")
        channel = data.get("channel")  # whatsapp, email, phone, visit, videocall
        direction = data.get("direction", "outbound")  # inbound/outbound
        content = data.get("content", "")
        outcome = data.get("outcome")  # interested, not_interested, callback, sale, etc.

        communication = {
            "id": str(uuid4()),
            "lead_id": lead_id,
            "channel": channel,
            "direction": direction,
            "content": content[:500],  # Truncar
            "outcome": outcome,
            "timestamp": datetime.now().isoformat(),
        }

        # communication_id = await db.track_communication(communication)

        # Actualizar lead si hay outcome
        if outcome in ["interested", "qualified"]:
            # await db.update_lead(lead_id, {"last_contact": datetime.now().isoformat()})
            pass

        return {
            "success": True,
            "communication_id": communication["id"],
            "message": "Comunicación registrada",
        }
