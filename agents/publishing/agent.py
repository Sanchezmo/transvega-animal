"""
Agente de Publicación - Gestión de anuncios en plataformas.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import uuid4
import structlog

logger = structlog.get_logger()


class PublishingAgent:
    """
    Agente de Publicación - Gestión de anuncios en plataformas.
    
    Responsabilidades:
    - Crear títulos y descripciones
    - Adaptar contenido por canal
    - Seleccionar fotografías autorizadas
    - Preparar borradores de anuncios
    - Publicar mediante APIs oficiales cuando estén disponibles
    - Registrar URL, ID externo, fecha y estado
    - Renovar anuncios autorizados
    - Retirar anuncios cuando el animal deje de estar disponible
    - Evitar publicaciones duplicadas
    
    Durante la fase inicial, toda publicación requiere aprobación humana.
    No automaticen navegadores ni incumplan condiciones de uso de plataformas sin autorización expresa.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "publishing"
        self.agent_name = "Publishing Agent"
        self.capabilities = [
            "create_draft",
            "adapt_content",
            "select_photos",
            "publish",
            "renew",
            "unpublish",
            "check_duplicates",
        ]
        self.restrictions = [
            "requires_human_approval_initially",
            "no_browser_automation_without_authorization",
            "respect_platform_tos",
        ]
    
    async def start(self):
        """Iniciar agente."""
        logger.info("starting_publishing_agent")
    
    async def stop(self):
        """Detener agente."""
        pass
    
    async def process_task(self, task: Dict) -> Dict:
        """Procesar tarea asignada."""
        task_type = task.get("task_type")
        
        handlers = {
            "create_draft": self._create_draft,
            "adapt_content": self._adapt_content,
            "select_photos": self._select_photos,
            "publish": self._publish,
            "renew": self._renew,
            "unpublish": self._unpublish,
            "check_duplicates": self._check_duplicates,
            "generate_content": self._generate_content,
        }
        
        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}
        
        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _create_draft(self, data: Dict) -> Dict:
        """
        Crear borrador de anuncio.
        
        Requiere: expediente_id, plataformas objetivo
        """
        expediente_id = data.get("expediente_id")
        platforms = data.get("platforms", ["web", "milanuncios"])
        
        # TODO: Obtener datos del expediente
        # expediente = await dolibarr.get_expediente(expediente_id)
        
        # Verificar estado
        # if expediente.commercial_status not in ["available", "published"]:
        #     return {"success": False, "error": "Solo expedientes 'available' pueden publicarse"}
        
        # Verificar documentación completa
        # docs = await compliance_agent._detect_pending_docs({"expediente": expediente})
        # if docs["missing"]:
        #     return {"success": False, "error": "Documentación incompleta", "missing": docs["missing"]}
        
        # Generar contenido por plataforma
        drafts = {}
        for platform in platforms:
            content = await self._generate_platform_content(data.get("expediente", {}), platform)
            drafts[platform] = {
                "title": content["title"],
                "description": content["description"],
                "photos": content["photos"],
                "price": content["price"],
                "hashtags": content["hashtags"],
                "platform_specific": content.get("platform_specific", {}),
            }
        
        # Crear borrador en BD
        # draft_id = await db.create_publication_draft({
        #     "expediente_id": expediente_id,
        #     "platforms": platforms,
        #     "drafts": drafts,
        #     "status": "draft",
        #     "created_at": datetime.now().isoformat(),
        # })
        
        return {
            "success": True,
            "draft_id": "draft_" + str(uuid4())[:8],
            "platforms": platforms,
            "drafts": drafts,
            "requires_approval": True,
            "message": "Borradores creados, pendientes de aprobación",
        }
    
    async def _generate_content(self, data: Dict) -> Dict:
        """Generar contenido para una plataforma específica."""
        expediente = data.get("expediente", {})
        platform = data.get("platform", "web")
        
        return await self._generate_platform_content(expediente, platform)
    
    async def _generate_platform_content(self, expediente: Dict, platform: str) -> Dict:
        """Generar contenido adaptado a cada plataforma."""
        
        templates = {
            "milanuncios": self._milanuncios_template,
            "facebook": self._facebook_template,
            "instagram": self._instagram_template,
            "web": self._web_template,
            "tiktok": self._tiktok_template,
        }
        
        template_func = templates.get(platform, self._web_template)
        return await template_func(expediente)
    
    async def _milanuncios_template(self, exp: Dict) -> Dict:
        """Template optimizado para Milanuncios."""
        title = f"{exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} - {exp.get('color', 'Color')} - {exp.get('province', 'Provincia')}"
        
        description = f"""🐾 {exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} busca familia responsable 🇪🇸

✅ ENTREGA INMEDIATA EN: {exp.get('province', 'España')} + ENVÍO NACIONAL/INTERNACIONAL

📋 INCLUIDO EN EL PRECIO:
• Pedigree LOE (tramitado) + FCI Export (si exportación)
• Cartilla vacunal completa (edad adecuada)
• Desparasitación interna/externa al día
• Microchip identificado y certificado
• Certificado veterinario de buena salud
• Contrato de compraventa con GARANTÍAS:
  - Genéticas de por vida (displasia, ojos, corazón, tests ADN)
  - Víricas 14 días
  - Temperamento 1 año
• Kit cachorro: pienso 2kg, juguete, manta con olor madre, guía cuidados

👨‍👩‍👧‍👦 PADRES VISIBLES EN NUESTRAS INSTALACIONES:
• Padre: {exp.get('sire_name', 'Campeón')} - {exp.get('sire_titles', 'Títulos')}
• Madre: {exp.get('dam_name', 'Campeona')} - {exp.get('dam_titles', 'Títulos')}

🏠 NUESTRO CRIADERO:
• Núcleo zoológico autorizado: {exp.get('zoological_nucleus', '')}
• Licencia cría: {exp.get('breeder_registration', '')}
• Puppy Culture / Avidog desde día 3
• Socialización: niños, ruidos, superficies, otros perros

🚚 TRANSPORTE:
• Recogida en criadero (recomendado - conoces instalaciones)
• Envío aéreo nacional (IATA) - puerta a puerta 24-48h
• Envío internacional (LatAm/EE.UU.) - gestiones completas

💰 PRECIO: {exp.get('sale_price', 0)}€ (Reserva 30% - Resto a la entrega)

📩 CONTACTO DIRECTO WHATSAPP: +34 XXX XX XX XX
🌐 WEB COMPLETA: transvega-animal.es/cachorro/{exp.get('slug', '')}

#perros #cachorros #{exp.get('breed', '').lower().replace(' ', '')} #pedigree #LOE #FCI #garantia #envio #{exp.get('breed', '').lower().replace(' ', '')} #{exp.get('province', '').lower().replace(' ', '')} #adopcionresponsable #criaderoselectivo #transvegaanimal"""

        return {
            "title": title[:70],  # Límite Milanuncios
            "description": description,
            "photos": exp.get("photos", [])[:12],  # Máx 12 fotos
            "price": exp.get("sale_price"),
            "hashtags": self._generate_hashtags(exp, "milanuncios"),
            "platform_specific": {
                "category": "perros",
                "province": exp.get("province", ""),
                "municipality": exp.get("municipality", ""),
                "renewal_days": 7,
            }
        }
    
    async def _facebook_template(self, exp: Dict) -> Dict:
        """Template para Facebook Marketplace."""
        description = f"""🐾 {exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} busca hogar 🏠

✅ Entrega en {exp.get('province', 'España')} + envío nacional/internacional
✅ Incluye: Pedigree LOE/FCI, vacunas, chip, desparasitación, certificado vet, contrato con garantías
✅ Padres visibles en criadero: {exp.get('sire_name', 'Padre')} + {exp.get('dam_name', 'Madre')}
✅ Núcleo zoo autorizado, Puppy Culture, socialización completa

💰 {exp.get('sale_price', 0)}€ (Reserva 30%)
📩 WhatsApp: +34 XXX XX XX XX
🌐 transvega-animal.es/cachorro/{exp.get('slug', '')}

#cachorros #perros #{exp.get('breed', '').lower().replace(' ', '')} #adopcionresponsable #criaderoselectivo #transvegaanimal"""
        
        return {
            "title": f"{exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} - {exp.get('price', 0)}€",
            "description": description,
            "photos": exp.get("photos", [])[:10],
            "price": exp.get("sale_price"),
            "hashtags": self._generate_hashtags(exp, "facebook"),
            "platform_specific": {
                "category": "Pets > Dogs",
                "condition": "New",
                "location": exp.get("province", ""),
            }
        }
    
    async def _instagram_template(self, exp: Dict) -> Dict:
        """Template para Instagram (post + stories)."""
        caption = f"""🐾 {exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} 🏠

{exp.get('age', '2 meses')} • {exp.get('sex', 'H/M')} • {exp.get('color', 'Color')} • {exp.get('weight_kg', 0)}kg

✅ LOE/FCI • Vacunas • Chip • Desparasitado • Cert. Vet • Contrato garantías
👨‍👩‍👧‍👦 Padres: {exp.get('sire_name', '')} + {exp.get('dam_name', '')}
🏠 Núcleo zoo autorizado • Puppy Culture • Socialización completa

💰 {exp.get('sale_price', 0)}€ (Reserva 30%)
🚚 Envío nacional/internacional disponible
📩 DM o WhatsApp +34 XXX XX XX XX
🌐 transvega-animal.es

#{exp.get('breed', '').lower().replace(' ', '')} #cachorros #perros #adopcionresponsable #criaderoselectivo #transvegaanimal #perros #{exp.get('province', '').lower()} #LOE #FCI #pedigree"""
        
        return {
            "title": f"{exp.get('name')} - {exp.get('breed')}",
            "description": caption,
            "photos": exp.get("photos", [])[:10],
            "hashtags": self._generate_hashtags(exp, "instagram"),
            "platform_specific": {
                "aspect_ratio": "4:5",
                "stories": True,
                "reel": True,
            }
        }
    
    async def _web_template(self, exp: Dict) -> Dict:
        """Template para web propia."""
        return {
            "title": f"{exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')}",
            "description": self._generate_full_web_description(exp),
            "photos": exp.get("photos", []),
            "videos": exp.get("videos", []),
            "price": exp.get("sale_price"),
            "specifications": {
                "breed": exp.get("breed"),
                "sex": exp.get("sex"),
                "birth_date": exp.get("birth_date"),
                "color": exp.get("color"),
                "weight_kg": exp.get("weight_kg"),
                "microchip": exp.get("microchip"),
                "pedigree": exp.get("pedigree"),
                "sire": exp.get("sire_name"),
                "dam": exp.get("dam_name"),
                "health_status": exp.get("vet_status"),
                "vaccines": exp.get("vaccines"),
                "deworming": exp.get("deworming"),
                "passport": exp.get("passport"),
                "certificates": exp.get("certificates"),
            },
            "parents": {
                "sire": {
                    "name": exp.get("sire_name"),
                    "titles": exp.get("sire_titles"),
                    "clearances": exp.get("sire_clearances"),
                },
                "dam": {
                    "name": exp.get("dam_name"),
                    "titles": exp.get("dam_titles"),
                    "clearances": exp.get("dam_clearances"),
                },
            },
            "guarantees": [
                "Genéticas de por vida (displasia, ojos, corazón, ADN)",
                "Víricas 14 días",
                "Temperamento 1 año",
            ],
            "delivery": {
                "pickup": True,
                "national_shipping": True,
                "international_shipping": True,
                "estimated_days": "24-48h nacional, 3-7 días internacional",
            },
        }
    
    async def _tiktok_template(self, exp: Dict) -> Dict:
        """Template para TikTok (video corto)."""
        return {
            "title": f"{exp.get('name')} el {exp.get('breed', 'cachorro')} busca hogar 🏠❤️",
            "description": f"""{exp.get('name')} el {exp.get('breed')} de {exp.get('age', '2 meses')} busca familia 🏠

✅ LOE/FCI • Vacunas ✅ Chip ✅ Desparasitado ✅ Cert. Vet ✅ Contrato garantías
👨‍👩‍👧‍👦 Padres: {exp.get('sire_name', '')} + {exp.get('dam_name', '')}
🏠 Criadero autorizado • Puppy Culture • Socialización completa

💰 {exp.get('sale_price', 0)}€ (Reserva 30%)
🚚 Envío nacional/internacional
📩 WhatsApp +34 XXX XX XX XX
🌐 transvega-animal.es

#perros #cachorros #adopcionresponsable #criaderoselectivo #transvegaanimal #{exp.get('breed', '').lower().replace(' ', '')} #fyp #foryou""",
            "photos": exp.get("photos", [])[:5],
            "video": exp.get("videos", [None])[0],
            "hashtags": self._generate_hashtags(exp, "tiktok"),
            "platform_specific": {
                "duration": "15-60s",
                "music": "trending",
                "cta": "Link en bio",
            }
        }
    
    def _generate_hashtags(self, exp: Dict, platform: str) -> List[str]:
        """Generar hashtags por plataforma."""
        base = ["adopcionresponsable", "compraresponsable", "bienestaranimal", "transvegaanimal"]
        breed = exp.get("breed", "").lower().replace(" ", "")
        province = exp.get("province", "").lower().replace(" ", "")
        
        platform_tags = {
            "milanuncios": ["perros", "cachorros", "venta", "adopcion"],
            "facebook": ["mascotas", "perros", "familia"],
            "instagram": ["dogs", "puppy", "dogsofinstagram", "adopta"],
            "tiktok": ["mascotas", "perros", "adopcion", "viral", "fyp"],
        }
        
        tags = base + [breed, province] + platform_tags.get(platform, [])
        return [f"#{t}" for t in tags if t][:20]  # Máx 20
    
    def _generate_full_web_description(self, exp: Dict) -> str:
        """Generar descripción completa para web."""
        parts = [
            f"🐾 {exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} busca familia responsable 🐾",
            "",
            f"📅 Nacido: {exp.get('birth_date', 'N/A')} | 🎨 Color: {exp.get('color', 'N/A')} | ⚖️ Peso: {exp.get('weight_kg', 'N/A')}kg",
            f"🔬 Microchip: {exp.get('microchip', 'N/A')} | 📜 Pedigree: {exp.get('pedigree', 'N/A')}",
            "",
            "✅ SALUD GARANTIZADA:",
            "• Vacunas al día (cartilla completa)",
            "• Desparasitación interna/externa (protocolo Puppy Culture)",
            "• Microchip identificado y certificado",
            "• Certificado veterinario de buena salud",
            "• Tests genéticos padres: CLEAR (displasia, ojos, corazón, ADN)",
            "• Clearances: Caderas A/A, Codos 0/0, Ojos CLEAR, Corazón CLEAR",
            "",
            "📋 CONTRATO CON GARANTÍAS:",
            "• Genéticas de por vida (displasia, ojos, corazón, ADN)",
            "• Víricas 14 días",
            "• Temperamento 1 año",
            "",
            "👨‍👩‍👧‍👦 PADRES CAMPEONES:",
            f"• Padre: {exp.get('sire_name', 'N/A')} - {exp.get('sire_titles', 'N/A')}",
            f"• Madre: {exp.get('dam_name', 'N/A')} - {exp.get('dam_titles', 'N/A')}",
            "",
            "🏠 CRIADERO RESPONSABLE:",
            f"• Núcleo zoológico: {exp.get('zoological_nucleus', 'N/A')}",
            f"• Licencia cría: {exp.get('breeder_registration', 'N/A')}",
            "• Puppy Culture / Avidog desde día 3",
            "• Socialización: niños, ruidos, superficies, otros perros",
            "",
            "🚚 ENTREGA:",
            "• Recogida en criadero (recomendado)",
            "• Transporte aéreo nacional (IATA) puerta a puerta 24-48h",
            "• Transporte internacional (LatAm/EE.UU.) - gestiones completas",
            "",
            f"💰 PRECIO: {exp.get('sale_price', 0)}€ (incluye todo: perro + transporte + docs + kit)",
            "💳 Reserva 30% - Resto a la entrega",
            "",
            "📩 CONTACTO: WhatsApp +34 XXX XX XX XX | info@transvega-animal.es",
            "🌐 FICHA COMPLETA: transvega-animal.es/cachorro/{slug}",
        ]
        return "\n".join(parts).format(slug=exp.get('slug', ''))
    
    async def _adapt_content(self, data: Dict) -> Dict:
        """Adaptar contenido existente a otra plataforma."""
        content = data.get("content", {})
        target_platform = data.get("target_platform", "web")
        
        # Reutilizar lógica de generación
        expediente = data.get("expediente", {})
        new_content = await self._generate_platform_content(data.get("expediente", {}), target_platform)
        
        return {
            "success": True,
            "original_platform": data.get("source_platform"),
            "target_platform": target_platform,
            "adapted_content": new_content,
        }
    
    async def _select_photos(self, data: Dict) -> Dict:
        """Seleccionar mejores fotos para publicación."""
        photos = data.get("photos", [])
        platform = data.get("platform", "web")
        max_photos = data.get("max_photos", 12)
        
        # Prioridad: stacked pose, movimiento, retrato, detalles, padres
        # Por ahora devolver primeras N
        selected = photos[:max_photos]
        
        return {
            "success": True,
            "selected_count": len(selected),
            "photos": selected,
            "platform": platform,
        }
    
    async def _publish(self, data: Dict) -> Dict:
        """
        Publicar anuncio en plataforma.
        
        REQUISITO: aprobación humana previa.
        """
        publicacion_id = data.get("publicacion_id")
        platform = data.get("platform")
        
        # Verificar aprobación
        # approval = await approval_service.check(publicacion_id)
        # if not approval.approved:
        #     return {"success": False, "error": "Requiere aprobación humana"}
        
        platform_publishers = {
            "milanuncios": self._publish_milanuncios,
            "facebook": self._publish_facebook,
            "instagram": self._publish_instagram,
            "web": self._publish_web,
            "tiktok": self._publish_tiktok,
        }
        
        publisher = platform_publishers.get(platform)
        if not publisher:
            return {"success": False, "error": f"Plataforma no soportada: {platform}"}
        
        try:
            result = await publisher(data.get("content", {}))
            
            # Registrar publicación
            # await db.record_publication({
            #     "publicacion_id": publicacion_id,
            #     "platform": platform,
            #     "external_id": result.get("external_id"),
            #     "url": result.get("url"),
            #     "published_at": datetime.now().isoformat(),
            #     "status": "published",
            # })
            
            return {
                "success": True,
                "platform": platform,
                "external_id": result.get("external_id"),
                "url": result.get("url"),
                "published_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("publish_failed", platform=platform, error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _publish_milanuncios(self, content: Dict) -> Dict:
        """Publicar en Milanuncios (requiere API oficial o automatización autorizada)."""
        # TODO: Implementar con API oficial Milanuncios o automatización autorizada
        logger.warning("milanuncios_publish_not_implemented")
        return {
            "external_id": "mock_milanuncios_id",
            "url": "https://milanuncios.com/anuncio/mock",
        }
    
    async def _publish_facebook(self, content: Dict) -> Dict:
        """Publicar en Facebook Marketplace (Graph API)."""
        # TODO: Implementar con Facebook Graph API
        return {
            "external_id": "mock_fb_id",
            "url": "https://facebook.com/marketplace/mock",
        }
    
    async def _publish_instagram(self, content: Dict) -> Dict:
        """Publicar en Instagram (Graph API)."""
        return {
            "external_id": "mock_ig_id",
            "url": "https://instagram.com/p/mock",
        }
    
    async def _publish_web(self, content: Dict) -> Dict:
        """Publicar en web propia."""
        # En web propia es directo a BD
        slug = f"cachorro-{uuid4().hex[:8]}"
        return {
            "external_id": slug,
            "url": f"https://transvega-animal.es/cachorro/{slug}",
        }
    
    async def _publish_tiktok(self, content: Dict) -> Dict:
        """Publicar en TikTok (API oficial)."""
        return {
            "external_id": "mock_tt_id",
            "url": "https://tiktok.com/@transvega/video/mock",
        }
    
    async def _renew(self, data: Dict) -> Dict:
        """Renovar anuncio en plataforma."""
        publicacion_id = data.get("publicacion_id")
        platform = data.get("platform")
        
        # TODO: Implementar renovación por plataforma
        # Milanuncios: renovar cada 7 días
        # Facebook: renovar cada 30 días
        
        return {
            "success": True,
            "publicacion_id": publicacion_id,
            "platform": platform,
            "renewed_at": datetime.now().isoformat(),
        }
    
    async def _unpublish(self, data: Dict) -> Dict:
        """Retirar anuncio (vendido, error, etc.)."""
        publicacion_id = data.get("publicacion_id")
        platform = data.get("platform")
        reason = data.get("reason", "Vendido")
        
        # TODO: Implementar retirada por plataforma
        
        # Actualizar estado en BD
        # await db.update_publication(publicacion_id, {"status": "unpublished", "unpublished_reason": reason})
        
        return {
            "success": True,
            "publicacion_id": publicacion_id,
            "platform": platform,
            "reason": reason,
            "unpublished_at": datetime.now().isoformat(),
        }
    
    async def _check_duplicates(self, data: Dict) -> Dict:
        """Verificar duplicados antes de publicar."""
        expediente_id = data.get("expediente_id")
        platforms = data.get("platforms", [])
        
        duplicates = []
        for platform in platforms:
            # TODO: Verificar en BD si ya existe publicación activa
            pass
        
        return {
            "success": True,
            "duplicates": duplicates,
            "can_publish": len(duplicates) == 0,
        }
    
    def _generate_hashtags(self, exp: Dict, platform: str) -> List[str]:
        """Generar hashtags por plataforma."""
        return self._generate_hashtags(exp, platform)