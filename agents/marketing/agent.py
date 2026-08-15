"""
Agente de Marketing - Contenido, campañas y análisis.
"""

from datetime import date, timedelta
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class MarketingAgent:
    """
    Agente de Marketing - Contenido, campañas y análisis.

    Responsabilidades:
    - Preparar calendario editorial
    - Proponer campañas
    - Crear contenido
    - Analizar resultados
    - Calcular coste por contacto
    - Comparar canales
    - Detectar anuncios sin rendimiento
    - Proponer mejoras
    - Preparar informes semanales

    Está prohibido:
    - Utilizar mensajes como "Última oportunidad" sin justificación
    - "Regalo perfecto"
    - "Sin complicaciones"
    - "Raza sin problemas de salud"
    - "Carácter garantizado"
    - "Compra ahora y decide después"
    - Cualquier mensaje que trivialice la responsabilidad de convivir con un perro
    - Aumentar presupuestos publicitarios sin aprobación
    - Lanzar campañas pagadas sin aprobación
    """

    def __init__(self, config: dict):
        self.config = config
        self.agent_id = "marketing"
        self.agent_name = "Marketing Agent"
        self.capabilities = [
            "prepare_editorial_calendar",
            "propose_campaign",
            "create_content",
            "analyze_results",
            "calculate_cpc",
            "compare_channels",
            "detect_underperforming_ads",
            "propose_improvements",
            "prepare_weekly_report",
        ]
        self.restrictions = [
            "no_misleading_messages",
            "no_budget_increase_without_approval",
            "no_paid_campaigns_without_approval",
            "no_breed_health_guarantees",
            "no_impulse_purchase_promotion",
        ]
        self.forbidden_phrases = [
            "última oportunidad",
            "regalo perfecto",
            "sin complicaciones",
            "raza sin problemas de salud",
            "carácter garantizado",
            "compra ahora y decide después",
            "gratis",
            "oferta limitada",
            "solo hoy",
        ]

    async def start(self):
        logger.info("starting_marketing_agent")

    async def stop(self):
        pass

    async def process_task(self, task: dict) -> dict:

        handlers = {
            "prepare_editorial_calendar": self._prepare_editorial_calendar,
            "propose_campaign": self._propose_campaign,
            "create_content": self._create_content,
            "analyze_results": self._analyze_results,
            "calculate_cpc": self._calculate_cpc,
            "compare_channels": self._compare_channels,
            "detect_underperforming_ads": self._detect_underperforming_ads,
            "propose_improvements": self._propose_improvements,
            "prepare_weekly_report": self._prepare_weekly_report,
        }

        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}

        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}

    async def _prepare_editorial_calendar(self, data: dict) -> dict:
        """Preparar calendario editorial mensual/semanal."""
        month = data.get("month", date.today().month)
        year = data.get("year", date.today().year)

        # Temas base por mes
        monthly_themes = {
            1: ["Nuevo año, nuevo compañero", "Razas para principiantes", "Preparar la casa"],
            2: ["Amor perruno", "Cuidados en invierno", "San Valentín con perro"],
            3: ["Primavera: alergias y parásitos", "Paseos primaverales", "Nuevas camadas"],
            4: ["Semana Santa: viajes con perro", "Alergias estacionales", "Baño y muda"],
            5: ["Día de la madre perruna", "Ejercicio en buen tiempo", "Socialización"],
            6: ["Verano: calor y perros", "Vacaciones con perro", "Protección solar"],
            7: ["Vacaciones: transporte y alojamiento", "Golpe de calor", "Juegos de agua"],
            8: ["Vuelta al cole: rutinas", "Ansiedad por separación", "Nuevas camadas otoño"],
            9: ["Vuelta a la rutina", "Ejercicio otoñal", "Preparar invierno"],
            10: ["Halloween seguro", "Muda otoñal", "Cuidados mayores"],
            11: ["Black Friday responsable", "Preparar navidad", "Abrigos y frío"],
            12: ["Navidad con perro", "Regalos seguros", "Propósitos perrunos"],
        }

        themes = monthly_themes.get(month, ["Tema general"])

        # Generar calendario semanal
        calendar = []
        for week in range(1, 5):
            calendar.append(
                {
                    "week": week,
                    "theme": themes[(week - 1) % len(themes)],
                    "content_types": ["blog", "instagram_reel", "facebook_post", "tiktok", "newsletter"],
                    "platforms": ["instagram", "facebook", "tiktok", "youtube_shorts", "web", "newsletter"],
                    "key_dates": self._get_key_dates(month, year, week),
                }
            )

        return {
            "success": True,
            "calendar": calendar,
            "month": month,
            "year": year,
            "total_weeks": len(calendar),
        }

    def _get_key_dates(self, month: int, year: int, week: int) -> list[str]:
        """Obtener fechas clave para la semana."""
        # Simplificado - en producción usar calendario real
        key_dates_map = {
            1: ["Año Nuevo", "Día de Reyes"],
            2: ["San Valentín", "Día del Amor"],
            3: ["Día del Padre", "Equinoccio primavera"],
            4: ["Semana Santa", "Día de la Tierra"],
            5: ["Día de la Madre", "Día del Trabajo"],
            6: ["San Juan", "Inicio verano"],
            7: ["Día del Perro", "Vacaciones"],
            8: ["Vacaciones", "Vuelta al cole"],
            9: ["Vuelta al cole", "Equinoccio otoño"],
            10: ["Halloween", "Día de los Muertos"],
            11: ["Black Friday", "Día del Soltero"],
            12: ["Navidad", "Nochevieja"],
        }
        return key_dates_map.get(month, [])

    async def _propose_campaign(self, data: dict) -> dict:
        """Proponer campaña de marketing."""
        objective = data.get("objective")  # awareness, leads, sales, retention
        budget = data.get("budget", 0)
        target_audience = data.get("target_audience", {})
        channels = data.get("channels", ["facebook", "instagram", "google"])
        duration_days = data.get("duration_days", 30)

        # Validar presupuesto
        if budget > 10000:
            return {
                "success": False,
                "error": "Presupuesto superior a 10.000€ requiere aprobación de dirección",
                "requires_approval": True,
            }

        # Validar mensajes prohibidos
        messages = data.get("key_messages", [])
        for msg in messages:
            for forbidden in self.forbidden_phrases:
                if forbidden.lower() in msg.lower():
                    return {
                        "success": False,
                        "error": f"Mensaje contiene frase prohibida: '{forbidden}'",
                        "forbidden_phrase": forbidden,
                    }

        campaign = {
            "id": str(uuid4()),
            "name": data.get("name", f"Campaña {date.today().strftime('%Y%m%d')}"),
            "objective": objective,
            "budget": budget,
            "daily_budget": round(budget / duration_days, 2),
            "target_audience": target_audience,
            "channels": channels,
            "duration_days": duration_days,
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=duration_days)).isoformat(),
            "key_messages": messages,
            "kpis": self._define_kpis(objective),
            "status": "proposed",
            "requires_approval": budget > 1000 or objective in ["sales", "leads"],
        }

        return {
            "success": True,
            "campaign": campaign,
            "message": "Campaña propuesta, pendiente de aprobación"
            if campaign["requires_approval"]
            else "Campaña aprobada automáticamente",
        }

    def _define_kpis(self, objective: str) -> dict:
        """Definir KPIs según objetivo."""
        kpis_map = {
            "awareness": {"reach": 10000, "impressions": 50000, "video_views": 5000},
            "leads": {"leads": 100, "cpl": 50, "conversion_rate": 5},
            "sales": {"conversions": 10, "cpa": 200, "roas": 4},
            "retention": {"repeat_rate": 0.2, "nps": 50, "clv": 2000},
        }
        return kpis_map.get(objective, kpis_map["awareness"])

    async def _create_content(self, data: dict) -> dict:
        """Crear contenido para redes sociales/blog."""
        content_type = data.get("content_type")  # post, reel, story, blog, video
        _ = data.get("topic")
        platform = data.get("platform", "instagram")
        language = data.get("language", "es")

        templates = {
            "instagram_post": self._ig_post_template,
            "instagram_reel": self._ig_reel_template,
            "instagram_story": self._ig_story_template,
            "facebook_post": self._fb_post_template,
            "tiktok": self._tiktok_template,
            "blog": self._blog_template,
            "newsletter": self._newsletter_template,
        }

        template_func = templates.get(content_type, self._generic_template)
        content = await template_func(data)

        # Validar frases prohibidas
        full_text = f"{content.get('title', '')} {content.get('caption', '')} {content.get('body', '')}"
        for forbidden in self.forbidden_phrases:
            if forbidden.lower() in full_text.lower():
                return {
                    "success": False,
                    "error": f"Contenido contiene frase prohibida: '{forbidden}'",
                }

        return {
            "success": True,
            "content": content,
            "platform": platform,
            "language": language,
            "hashtags": self._generate_hashtags(data.get("topic", ""), platform),
        }

    async def _analyze_results(self, data: dict) -> dict:
        """Analizar resultados de campañas/contenido."""
        campaign_id = data.get("campaign_id")
        period_days = data.get("period_days", 30)

        # TODO: Obtener métricas reales de APIs
        metrics = {
            "reach": 15000,
            "impressions": 45000,
            "engagement": 2500,
            "engagement_rate": 5.5,
            "clicks": 800,
            "ctr": 1.78,
            "conversions": 12,
            "cpa": 125.00,
            "roas": 3.5,
            "spend": 1500.00,
        }

        # Análisis
        insights = []
        if metrics["engagement_rate"] > 5:
            insights.append("Buena tasa de engagement (>5%)")
        if metrics["cpa"] < 200:
            insights.append("CPA por debajo de 200€ - eficiente")
        if metrics["roas"] > 3:
            insights.append("ROAS > 3x - rentable")

        return {
            "success": True,
            "campaign_id": campaign_id,
            "period_days": period_days,
            "metrics": metrics,
            "insights": insights,
            "recommendations": [
                "Aumentar presupuesto en anuncios con mejor ROAS",
                "Probar nuevos creativos para combatir fatiga",
                "Segmentar audiencia por engagement previo",
            ],
        }

    async def _calculate_cpc(self, data: dict) -> dict:
        """Calcular coste por clic/contacto."""
        spend = data.get("spend", 0)
        clicks = data.get("clicks", 0)
        leads = data.get("leads", 0)
        sales = data.get("sales", 0)

        cpc = round(spend / clicks, 2) if clicks > 0 else 0
        cpl = round(spend / leads, 2) if leads > 0 else 0
        cpa = round(spend / sales, 2) if sales > 0 else 0
        ctr = round(clicks / data.get("impressions", 1) * 100, 2) if data.get("impressions", 0) > 0 else 0

        return {
            "success": True,
            "cpc": cpc,
            "cpl": cpl,
            "cpa": cpa,
            "ctr": ctr,
            "roas": round(data.get("revenue", 0) / spend, 2) if spend > 0 else 0,
        }

    async def _compare_channels(self, data: dict) -> dict:
        """Comparar rendimiento por canal."""
        channels_data = data.get("channels_data", {})

        comparison = {}
        for channel, metrics in channels_data.items():
            comparison[channel] = {
                "spend": metrics.get("spend", 0),
                "reach": metrics.get("reach", 0),
                "leads": metrics.get("leads", 0),
                "sales": metrics.get("sales", 0),
                "cpl": round(metrics.get("spend", 0) / max(metrics.get("leads", 1), 1), 2),
                "cpa": round(metrics.get("spend", 0) / max(metrics.get("sales", 1), 1), 2),
                "roas": round(metrics.get("revenue", 0) / max(metrics.get("spend", 1), 1), 2),
            }

        # Ordenar por ROAS
        sorted_channels = sorted(comparison.items(), key=lambda x: x[1]["roas"], reverse=True)

        return {
            "success": True,
            "comparison": dict(sorted_channels),
            "best_channel": sorted_channels[0][0] if sorted_channels else None,
            "worst_channel": sorted_channels[-1][0] if sorted_channels else None,
        }

    async def _detect_underperforming_ads(self, data: dict) -> dict:
        """Detectar anuncios con bajo rendimiento."""
        ads_data = data.get("ads_data", [])
        thresholds = data.get("thresholds", {"ctr": 1.0, "cpa": 300, "roas": 2.0})

        underperforming = []
        for ad in ads_data:
            issues = []
            if ad.get("ctr", 0) < thresholds["ctr"]:
                issues.append(f"CTR bajo: {ad.get('ctr', 0)}%")
            if ad.get("cpa", 999) > thresholds["cpa"]:
                issues.append(f"CPA alto: {ad.get('cpa', 0)}€")
            if ad.get("roas", 0) < thresholds["roas"]:
                issues.append(f"ROAS bajo: {ad.get('roas', 0)}x")

            if issues:
                underperforming.append(
                    {
                        "ad_id": ad.get("ad_id"),
                        "ad_name": ad.get("ad_name"),
                        "issues": issues,
                        "recommendation": "Pausar y revisar creativo/audiencia" if len(issues) >= 2 else "Optimizar",
                    }
                )

        return {
            "success": True,
            "underperforming": underperforming,
            "total_analyzed": len(ads_data),
            "underperforming_count": len(underperforming),
        }

    async def _propose_improvements(self, data: dict) -> dict:
        """Proponer mejoras basadas en análisis."""
        analysis = data.get("analysis", {})

        improvements = []

        # Basado en análisis de canales
        if "comparison" in analysis:
            best = analysis["comparison"].get("best_channel")
            worst = analysis["comparison"].get("worst_channel")
            if best and worst:
                improvements.append(
                    {
                        "type": "budget_reallocation",
                        "description": f"Mover 30% presupuesto de {worst} a {best}",
                        "impact": "high",
                        "effort": "low",
                    }
                )

        # Basado en anuncios bajo rendimiento
        if "underperforming" in analysis:
            for ad in analysis["underperforming"]:
                improvements.append(
                    {
                        "type": "creative_refresh",
                        "target": ad["ad_id"],
                        "description": f"Renovar creativo {ad['ad_name']}: {', '.join(ad['issues'])}",
                        "impact": "medium",
                        "effort": "medium",
                    }
                )

        # Mejoras generales
        improvements.extend(
            [
                {
                    "type": "audience_expansion",
                    "description": "Crear audiencias lookalike de compradores",
                    "impact": "high",
                    "effort": "medium",
                },
                {
                    "type": "creative_testing",
                    "description": "A/B test: video vs imagen estática",
                    "impact": "medium",
                    "effort": "low",
                },
                {
                    "type": "retargeting",
                    "description": "Implementar retargeting 7/30 días para visitantes web",
                    "impact": "high",
                    "effort": "medium",
                },
            ]
        )

        return {
            "success": True,
            "improvements": improvements,
            "priority_order": sorted(
                improvements, key=lambda x: {"high": 3, "medium": 2, "low": 1}[x["impact"]], reverse=True
            ),
        }

    async def _prepare_weekly_report(self, data: dict) -> dict:
        """Preparar informe semanal de marketing."""
        week_start = data.get("week_start", date.today() - timedelta(days=date.today().weekday()))
        week_end = week_start + timedelta(days=6)

        # Métricas semanales
        metrics = {
            "reach": 50000,
            "impressions": 120000,
            "followers_gained": 150,
            "engagement_rate": 4.8,
            "website_traffic": 2500,
            "leads_generated": 25,
            "sales_attributed": 3,
            "spend": 1200.00,
            "cpl": 48.00,
            "cpa": 400.00,
            "roas": 4.2,
        }

        # Top contenido
        top_content = [
            {"type": "reel", "topic": "Cachorro Golden Retriever", "views": 15000, "engagement": 8.5},
            {"type": "post", "topic": "Consejos primera vez", "likes": 1200, "shares": 150},
            {"type": "story", "topic": "Día en el criadero", "views": 8000, "replies": 45},
        ]

        # Alertas
        alerts = []
        if metrics["cpl"] > 60:
            alerts.append({"type": "warning", "message": "CPL superior a 60€"})
        if metrics["roas"] < 3:
            alerts.append({"type": "warning", "message": "ROAS por debajo de 3x"})

        return {
            "success": True,
            "week": f"{week_start.isoformat()} - {week_end.isoformat()}",
            "metrics": metrics,
            "top_content": top_content,
            "alerts": alerts,
            "recommendations": [
                "Aumentar presupuesto en reels (mejor engagement)",
                "Probar nuevo hook en anuncios de Facebook",
                "Crear contenido para TikTok (audiencia joven)",
            ],
        }

    # =========================================================================
    # TEMPLATES DE CONTENIDO
    # =========================================================================

    async def _ig_post_template(self, data: dict) -> dict:
        exp = data.get("expediente", {})
        return {
            "title": f"🐾 {exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')}",
            "caption": f"""{exp.get("name", "Nuestro cachorro")} busca familia responsable 🏠

✅ {exp.get("breed", "Raza")} LOE/FCI
✅ Vacunas, chip, desparasitado
✅ Padres campeones visibles
✅ Garantías: genéticas, víricas, temperamento
✅ Kit cachorro incluido
✅ Envío nacional/internacional

💰 {exp.get("sale_price", 0)}€ (reserva 30%)

📩 WhatsApp +34 XXX XX XX XX
🌐 transvega-animal.es

#perros #{exp.get("breed", "").lower().replace(" ", "")}
#cachorros #adopcionresponsable #criaderoselectivo
#pedigree #transvegaanimal""",
            "hashtags": [
                "perros",
                "cachorros",
                "adopcionresponsable",
                "criaderoselectivo",
                "pedigree",
                "transvegaanimal",
            ],
        }

    async def _ig_reel_template(self, data: dict) -> dict:
        exp = data.get("expediente", {})
        return {
            "title": f"{exp.get('name', 'Cachorro')} - {exp.get('breed', 'Raza')} 🐾",
            "caption": (
                f"{exp.get('name', 'Cachorro')} de {exp.get('breed', 'raza')} "
                f"con {exp.get('age_months', 2)} meses 🐶\n\n"
                f"Padres: {exp.get('sire_name', 'Campeón')} + {exp.get('dam_name', 'Campeona')}\n\n"
                "✅ LOE/FCI • Vacunas • Chip • Garantías\n"
                f"💰 {exp.get('sale_price', 0)}€\n"
                "📩 WhatsApp +34 XXX XX XX XX\n\n"
                "#perros #cachorros "
                f"#{exp.get('breed', '').lower().replace(' ', '')} "
                "#adopcionresponsable #transvegaanimal"
            ),
            "hashtags": ["perros", "cachorros", "reel", "viral", "adopcionresponsable", "transvegaanimal"],
            "duration": "15-30s",
            "music": "trending",
        }

    async def _ig_story_template(self, data: dict) -> dict:
        return {
            "frames": [
                {"type": "image", "content": "Cachorro jugando", "text": "¿Buscas compañero? 🐾"},
                {"type": "video", "content": "Padres jugando", "text": "Padres campeones visibles 🏆"},
                {"type": "image", "content": "Instalaciones", "text": "Criadero autorizado ✅"},
                {"type": "image", "content": "Cachorro durmiendo", "text": "¿Te lo imaginas en tu casa? 🏠"},
                {"type": "image", "content": "WhatsApp", "text": "Escríbenos 📩 +34 XXX XX XX XX"},
            ],
            "cta": "Link en bio / WhatsApp",
        }

    async def _fb_post_template(self, data: dict) -> dict:
        exp = data.get("expediente", {})
        return {
            "title": f"🐾 {exp.get('name')} - {exp.get('breed')} busca familia",
            "body": (
                f"{exp.get('name', 'Nuestro cachorro')} de {exp.get('breed', 'raza')} "
                "busca su hogar definitivo 🏠❤️\n\n"
                "✅ Pedigree LOE/FCI\n"
                "✅ Vacunas al día + desparasitado\n"
                "✅ Microchip identificado\n"
                "✅ Certificado veterinario\n"
                "✅ Contrato con garantías (genéticas, víricas, temperamento)\n"
                "✅ Kit bienvenida: pienso, juguete, manta, guía\n\n"
                "👨‍👩‍👧‍👦 Padres visibles en criadero:\n"
                f"🐕 Padre: {exp.get('sire_name', 'Campeón')}\n"
                f"🐕 Madre: {exp.get('dam_name', 'Campeona')}\n\n"
                "🚚 Entrega: Recogida en criadero O envío nacional/internacional (IATA)\n"
                f"💰 Precio: {exp.get('sale_price', 0)}€ (reserva 30%)\n\n"
                "📩 MÁS INFO: WhatsApp +34 XXX XX XX XX\n"
                "🌐 transvega-animal.es\n\n"
                "#perros #cachorros #adopcionresponsable #criaderoselectivo\n"
                f"#{exp.get('breed', '').lower().replace(' ', '')} #pedigree #LOE #FCI"
            ),
        }

    async def _tiktok_template(self, data: dict) -> dict:
        exp = data.get("expediente", {})
        return {
            "title": f"{exp.get('name', 'Cachorro')} el {exp.get('breed', 'perrito')} busca hogar 🏠❤️",
            "caption": f"""{exp.get("name", "Cachorro")} de {exp.get("breed", "raza")} busca familia 🏠

✅ LOE/FCI • Vacunas ✅ Chip ✅ Vet ✅ Garantías
👨‍👩‍👧‍👦 Padres: {exp.get("sire_name", "Campeón")} + {exp.get("dam_name", "Campeona")}
💰 {exp.get("sale_price", 0)}€ (reserva 30%)
🚚 Envío mundial ✈️

📩 WhatsApp: +34 XXX XX XX XX
🌐 transvega-animal.es

#perros #cachorros #adopcionresponsable #criaderoselectivo #transvegaanimal #fyp #perros #cachorro""",
            "hashtags": ["perros", "cachorros", "adopcionresponsable", "criaderoselectivo", "transvegaanimal", "fyp"],
            "duration": "15-60s",
            "hooks": ["Cachorro busca hogar", "Padres campeones", "Garantías de por vida"],
        }

    async def _blog_template(self, data: dict) -> dict:
        topic = data.get("topic", "Guía para elegir cachorro")
        return {
            "title": f"Guía completa: {topic} 🐾",
            "slug": topic.lower().replace(" ", "-"),
            "body": f"""# {topic}

## Introducción
Elegir un cachorro es una decisión importante que afectará a tu familia durante 10-15 años...

## Qué buscar en un criador responsable
- Núcleo zoológico autorizado
- Padres visibles y con pruebas de salud
- Pedigree LOE/FCI
- Contrato con garantías
- Socialización temprana (Puppy Culture)

## Preguntas clave antes de comprar
1. ¿Puedo ver a los padres?
2. ¿Qué pruebas de salud tienen?
3. ¿Qué garantías ofrece?
4. ¿Cómo socializan a los cachorros?

## Conclusión
Un perro bien criado es una inversión en años de compañía feliz...

---
*¿Buscas un cachorro de raza? En Transvega Animal te acompañamos en todo el proceso.*""",
            "tags": ["guía", "cachorro", "criador", "responsable", "pedigree"],
            "seo_title": f"{topic} - Guía Completa 2024 | Transvega Animal",
            "seo_description": (
                "Descubre cómo elegir un cachorro responsablemente. Consejos de expertos en cría selectiva."
            ),
        }

    async def _newsletter_template(self, data: dict) -> dict:
        return {
            "subject": f"🐾 Novedades Transvega Animal - {date.today().strftime('%d/%m/%Y')}",
            "preheader": "Nuevas camadas, consejos y ofertas exclusivas",
            "sections": [
                {
                    "type": "hero",
                    "title": "🐾 Nuevas camadas disponibles",
                    "content": "Esta semana llegan 3 nuevas camadas de Golden Retriever, Labrador y Pastor Alemán.",
                    "cta": "Ver cachorros disponibles",
                    "link": "https://transvega-animal.es/cachorros",
                },
                {
                    "type": "article",
                    "title": "📚 Artículo de la semana: Preparar la casa para tu cachorro",
                    "excerpt": "Todo lo que necesitas saber antes de que llegue tu nuevo compañero...",
                    "link": "https://transvega-animal.es/blog/preparar-casa-cachorro",
                },
                {
                    "type": "testimonial",
                    "title": "⭐ Familia García - Madrid",
                    "content": (
                        '"Luna llegó perfecta, sana y super socializada. El seguimiento post-entrega es increíble."'
                    ),
                },
                {
                    "type": "tip",
                    "title": "💡 Tip de la semana",
                    "content": (
                        "La socialización entre 3-16 semanas es CRÍTICA. "
                        "Expón a tu cachorro a sonidos, personas, superficies "
                        "y otros perros de forma positiva."
                    ),
                },
            ],
            "footer": {
                "unsubscribe": "https://transvega-animal.es/unsubscribe",
                "contact": "info@transvega-animal.es | +34 XXX XX XX XX",
                "social": ["instagram", "facebook", "tiktok", "youtube"],
            },
        }

    async def _generic_template(self, data: dict) -> dict:
        return {
            "title": data.get("title", "Contenido"),
            "body": data.get("body", "Contenido no especificado"),
        }

    def _generate_hashtags(self, topic: str, platform: str) -> list[str]:
        base = [
            "transvegaanimal",
            "perros",
            "cachorros",
            "adopcionresponsable",
            "criaderoselectivo",
            "pedigree",
            "LOE",
            "FCI",
        ]

        topic_tags = topic.lower().replace(" ", "").split(",") if topic else []

        platform_extras = {
            "instagram": ["dogs", "puppy", "dogsofinstagram", "puppylove", "doglover"],
            "facebook": ["mascotas", "perros", "familia", "adopta"],
            "tiktok": ["fyp", "viral", "perros", "cachorros", "mascotas"],
            "web": ["guia", "consejos", "criador", "salud"],
        }

        all_tags = base + topic_tags + platform_extras.get(platform, [])
        return list(set(all_tags))[:20]  # Max 20, sin duplicados
