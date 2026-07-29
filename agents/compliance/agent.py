"""
Agente de Cumplimiento Documental - Validación de documentación.
"""
import asyncio
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from uuid import uuid4
import structlog

logger = structlog.get_logger()


class ComplianceAgent:
    """
    Agente de Cumplimiento Documental.
    
    Responsabilidades:
    - Comprobar microchip
    - Comprobar vacunas
    - Comprobar pasaporte
    - Comprobar pedigrí
    - Comprobar registro del criador
    - Comprobar núcleo zoológico
    - Detectar documentos caducados
    - Validar que el anuncio contiene los datos obligatorios configurados
    - Generar una lista de incidencias
    
    No debe tomar decisiones legales definitivas. Debe escalar dudas.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "compliance"
        self.agent_name = "Compliance Agent"
        self.capabilities = [
            "check_microchip",
            "check_vaccines",
            "check_passport",
            "check_pedigree",
            "check_breeder_registration",
            "check_zoological_nucleus",
            "detect_expired_docs",
            "validate_ad_content",
            "generate_incidents_list",
        ]
        self.restrictions = [
            "cannot_make_legal_decisions",
            "must_escalate_doubts",
        ]
    
    async def start(self):
        """Iniciar agente."""
        logger.info("starting_compliance_agent")
    
    async def stop(self):
        """Detener agente."""
        pass
    
    async def process_task(self, task: Dict) -> Dict:
        """Procesar tarea asignada."""
        task_type = task.get("task_type")
        
        handlers = {
            "check_microchip": self._check_microchip,
            "check_vaccines": self._check_vaccines,
            "check_passport": self._check_passport,
            "check_pedigree": self._check_pedigree,
            "check_breeder_registration": self._check_breeder_registration,
            "check_zoological_nucleus": self._check_zoological_nucleus,
            "detect_expired_docs": self._detect_expired_docs,
            "validate_ad_content": self._validate_ad_content,
            "generate_incidents_list": self._generate_incidents_list,
            "full_compliance_check": self._full_compliance_check,
        }
        
        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}
        
        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _check_microchip(self, data: Dict) -> Dict:
        """
        Comprobar microchip.
        
        Validaciones:
        - Formato ISO 11784/11785 (15 dígitos)
        - Coincide con documentos
        - Registrado en base de datos oficial (REIAC/IVIA)
        - No duplicado
        """
        expediente = data.get("expediente", {})
        microchip = expediente.get("microchip", "")
        
        checks = {
            "format_valid": False,
            "matches_documents": False,
            "registered_officially": False,
            "not_duplicated": False,
        }
        
        issues = []
        
        # 1. Formato ISO 11784/11785 (15 dígitos numéricos)
        if microchip and microchip.isdigit() and len(microchip) == 15:
            checks["format_valid"] = True
        else:
            issues.append({
                "code": "MICROCHIP_INVALID_FORMAT",
                "severity": "critical",
                "message": f"Microchip '{microchip}' no tiene formato válido (15 dígitos numéricos ISO 11784/11785)",
            })
        
        # 2. Coincide con documentos (simulado)
        # TODO: Comparar con certificado veterinario, pasaporte, factura
        checks["matches_documents"] = True  # TODO: implementar
        
        # 3. Registrado oficialmente (REIAC/IVIA)
        # TODO: Consultar API REIAC/IVIA
        checks["registered_officially"] = True  # TODO: implementar
        
        # 4. No duplicado
        # TODO: Verificar en BD propia y REIAC
        checks["not_duplicated"] = True  # TODO: implementar
        
        all_passed = all(checks.values())
        
        return {
            "success": True,
            "check": "microchip",
            "passed": all_passed,
            "checks": checks,
            "issues": issues,
            "microchip": microchip,
        }
    
    async def _check_vaccines(self, data: Dict) -> Dict:
        """
        Comprobar vacunas.
        
        Validaciones:
        - Vacunas obligatorias presentes (polivalente, rabia)
        - Fechas válidas (no caducadas)
        - Lotes registrados
        - Veterinario colegiado
        - Próximas revisiones
        """
        expediente = data.get("expediente", {})
        vaccines = expediente.get("vaccines", [])
        
        required_vaccines = {
            "polivalente": {
                "required": True,
                "components": ["moquillo", "hepatitis", "parvovirus", "parainfluenza", "leptospirosis"],
                "min_age_weeks": 8,
            },
            "rabia": {
                "required": True,
                "min_age_weeks": 12,
                "valid_months": 12,  # o 36 según vacuna
            },
            "tos_perreras": {
                "required": False,
                "recommended": True,
            },
            "leishmania": {
                "required": False,
                "recommended": True,
            },
        }
        
        checks = {}
        issues = []
        found_vaccines = {v.get("name", "").lower(): v for v in vaccines}
        
        for vaccine_key, config in required_vaccines.items():
            found = None
            for v in vaccines:
                if vaccine_key in v.get("name", "").lower():
                    found = v
                    break
            
            if found:
                checks[vaccine_key] = {
                    "present": True,
                    "date": found.get("date"),
                    "batch": found.get("batch"),
                    "vet": found.get("vet"),
                    "expired": self._is_vaccine_expired(found, config),
                }
                
                if checks[vaccine_key]["expired"]:
                    issues.append({
                        "code": f"VACCINE_{vaccine_key.upper()}_EXPIRED",
                        "severity": "high",
                        "message": f"Vacuna {vaccine_key} caducada",
                    })
            else:
                checks[vaccine_key] = {"present": False}
                if config.get("required"):
                    issues.append({
                        "code": f"VACCINE_{vaccine_key.upper()}_MISSING",
                        "severity": "critical",
                        "message": f"Vacuna obligatoria {vaccine_key} no encontrada",
                    })
                else:
                    issues.append({
                        "code": f"VACCINE_{vaccine_key.upper()}_RECOMMENDED",
                        "severity": "medium",
                        "message": f"Vacuna recomendada {vaccine_key} no registrada",
                    })
        
        # Verificar veterinario colegiado
        vet_checks = {}
        for v in vaccines:
            vet = v.get("vet", "")
            if vet:
                # TODO: Verificar colegiado
                vet_checks[v.get("name")] = {"vet": vet, "verified": True}
        
        return {
            "success": True,
            "check": "vaccines",
            "checks": checks,
            "issues": issues,
            "summary": {
                "total_vaccines": len(vaccines),
                "mandatory_present": sum(1 for k, v in required_vaccines.items() 
                                        if v.get("required") and k in [c for c in checks if checks[c].get("present")]),
                "mandatory_missing": sum(1 for k, v in required_vaccines.items() 
                                        if v.get("required") and not checks.get(k, {}).get("present")),
            },
        }
    
    def _is_vaccine_expired(self, vaccine: Dict, config: Dict) -> bool:
        """Verificar si vacuna está caducada."""
        try:
            vac_date = datetime.fromisoformat(vaccine.get("date", "")).date()
            valid_months = config.get("valid_months", 12)
            expiry = vac_date.replace(month=vac_date.month + valid_months)
            return date.today() > expiry
        except:
            return False
    
    async def _check_passport(self, data: Dict) -> Dict:
        """
        Comprobar pasaporte UE / cartilla.
        
        Validaciones:
        - Número de pasaporte válido
        - Datos coinciden con microchip
        - Propietario actual correcto
        - Sección vacunas completa
        - No caducado
        """
        expediente = data.get("expediente", {})
        passport = expediente.get("passport", "")
        
        checks = {
            "format_valid": False,
            "matches_microchip": False,
            "owner_correct": False,
            "vaccines_section_complete": False,
            "not_expired": False,
        }
        
        issues = []
        
        if passport:
            # Formato ES + 11 dígitos o similar
            checks["format_valid"] = True  # TODO: validar formato
            
            # TODO: Comparar microchip en pasaporte vs expediente
            checks["matches_microchip"] = True
            
            # TODO: Verificar propietario
            checks["owner_correct"] = True
            
            # TODO: Verificar sección vacunas
            checks["vaccines_section_complete"] = True
            
            # TODO: Verificar caducidad
            checks["not_expired"] = True
        else:
            issues.append({
                "code": "PASSPORT_MISSING",
                "severity": "critical",
                "message": "Pasaporte / Cartilla no registrada",
            })
        
        all_passed = all(checks.values())
        
        return {
            "success": True,
            "check": "passport",
            "passed": all_passed,
            "checks": checks,
            "issues": issues,
        }
    
    async def _check_pedigree(self, data: Dict) -> Dict:
        """
        Comprobar pedigrí LOE / FCI.
        
        Validaciones:
        - Número LOE válido
        - Coincide con padres
        - Emitido por RSCE / FCI
        - No anulado
        - Exportación FCI si internacional
        """
        expediente = data.get("expediente", {})
        pedigree = expediente.get("pedigree", "")
        loe_number = expediente.get("loe_number", "")
        
        checks = {
            "loe_valid": False,
            "matches_parents": False,
            "issued_by_rsce": False,
            "not_revoked": False,
            "fci_export_ready": False,
        }
        
        issues = []
        
        if loe_number:
            # TODO: Verificar formato LOE (LOE-XXXXXXX)
            checks["loe_valid"] = True
            
            # TODO: Verificar padres en RSCE
            checks["matches_parents"] = True
            
            # TODO: Verificar emisión RSCE
            checks["issued_by_rsce"] = True
            
            # TODO: Verificar no anulado
            checks["not_revoked"] = True
            
            # Exportación FCI
            checks["fci_export_ready"] = True
        else:
            issues.append({
                "code": "PEDIGREE_MISSING",
                "severity": "high",
                "message": "Número LOE / Pedigrí no registrado",
            })
        
        all_passed = all(checks.values())
        
        return {
            "success": True,
            "check": "pedigree",
            "passed": all_passed,
            "checks": checks,
            "issues": issues,
            "loe_number": loe_number,
            "pedigree": pedigree,
        }
    
    async def _check_breeder_registration(self, data: Dict) -> Dict:
        """
        Comprobar registro del criador.
        
        Validaciones:
        - Número registro criador válido
        - Núcleo zoológico autorizado
        - Licencia de cría vigente
        - Seguro RC vigente
        - Certificado formación bienestar animal
        - Declaración responsable firmada
        """
        expediente = data.get("expediente", {})
        breeder_id = expediente.get("breeder_id")
        breeder_reg = expediente.get("breeder_registration", "")
        nucleus = expediente.get("zoological_nucleus", "")
        
        checks = {
            "breeder_registered": False,
            "nucleus_authorized": False,
            "license_valid": False,
            "rc_insurance_valid": False,
            "welfare_training": False,
            "declaration_signed": False,
        }
        
        issues = []
        
        if breeder_reg:
            checks["breeder_registered"] = True  # TODO: Verificar en registro oficial
        else:
            issues.append({"code": "BREEDER_REG_MISSING", "severity": "critical", 
                          "message": "Número registro criador no registrado"})
        
        if nucleus:
            checks["nucleus_authorized"] = True  # TODO: Verificar en registro CCAA
        else:
            issues.append({"code": "NUCLEUS_MISSING", "severity": "critical",
                          "message": "Núcleo zoológico no registrado"})
        
        # TODO: Verificar licencia cría, seguro RC, formación, declaración
        checks["license_valid"] = True
        checks["rc_insurance_valid"] = True
        checks["welfare_training"] = True
        checks["declaration_signed"] = True
        
        all_passed = all(checks.values())
        
        return {
            "success": True,
            "check": "breeder_registration",
            "passed": all_passed,
            "checks": checks,
            "issues": issues,
        }
    
    async def _check_zoological_nucleus(self, data: Dict) -> Dict:
        """
        Comprobar núcleo zoológico.
        
        Validaciones:
        - Número núcleo válido
        - Autorizado por CCAA
        - Inspección veterinaria vigente
        - Capacidad adecuada
        - Condiciones bienestar
        """
        expediente = data.get("expediente", {})
        nucleus = expediente.get("zoological_nucleus", "")
        
        checks = {
            "nucleus_valid": False,
            "authorized_by_ccaa": False,
            "vet_inspection_current": False,
            "capacity_adequate": False,
            "welfare_conditions": False,
        }
        
        issues = []
        
        if nucleus:
            # TODO: Verificar en registro CCAA
            checks["nucleus_valid"] = True
            checks["authorized_by_ccaa"] = True
            checks["vet_inspection_current"] = True
            checks["capacity_adequate"] = True
            checks["welfare_conditions"] = True
        else:
            issues.append({
                "code": "NUCLEUS_MISSING",
                "severity": "critical",
                "message": "Núcleo zoológico no registrado",
            })
        
        all_passed = all(checks.values())
        
        return {
            "success": True,
            "check": "zoological_nucleus",
            "passed": all_passed,
            "checks": checks,
            "issues": issues,
        }
    
    async def _detect_expired_docs(self, data: Dict) -> Dict:
        """
        Detectar documentos caducados.
        
        Documentos a verificar:
        - Pasaporte
        - Vacunas (rabia, polivalente)
        - Certificado veterinario
        - Seguro RC criador
        - Licencia cría
        - Inspección núcleo zoológico
        - Seguro transporte
        """
        expediente = data.get("expediente", {})
        
        docs_to_check = {
            "passport": {"date_field": "passport_expiry", "label": "Pasaporte"},
            "rabies_vaccine": {"date_field": "rabies_expiry", "label": "Vacuna rabia"},
            "polyvalent_vaccine": {"date_field": "polyvalent_expiry", "label": "Vacuna polivalente"},
            "vet_certificate": {"date_field": "vet_cert_expiry", "label": "Certificado veterinario"},
            "rc_insurance": {"date_field": "rc_insurance_expiry", "label": "Seguro RC criador"},
            "breeding_license": {"date_field": "license_expiry", "label": "Licencia cría"},
            "nucleus_inspection": {"date_field": "nucleus_inspection_expiry", "label": "Inspección núcleo zoológico"},
            "transport_insurance": {"date_field": "transport_insurance_expiry", "label": "Seguro transporte"},
        }
        
        expired = []
        expiring_soon = []  # < 30 días
        valid = []
        
        for key, config in docs_to_check.items():
            doc_date_str = expediente.get(config["date_field"])
            if doc_date_str:
                try:
                    doc_date = datetime.fromisoformat(doc_date_str).date()
                    days_left = (doc_date - date.today()).days
                    
                    if days_left < 0:
                        expired.append({"document": config["label"], "expired_days": abs(days_left)})
                    elif days_left <= 30:
                        expiring_soon.append({"document": config["label"], "days_left": days_left})
                    else:
                        valid.append(config["label"])
                except:
                    expired.append({"document": config["label"], "error": "Fecha inválida"})
            else:
                expired.append({"document": config["label"], "reason": "No registrada"})
        
        return {
            "success": True,
            "expired": expired,
            "expiring_soon": expiring_soon,
            "valid": valid,
            "summary": {
                "total": len(docs_to_check),
                "expired": len(expired),
                "expiring_soon": len(expiring_soon),
                "valid": len(valid),
            },
        }
    
    async def _validate_ad_content(self, data: Dict) -> Dict:
        """
        Validar que el anuncio contiene los datos obligatorios configurados.
        
        Datos obligatorios (configurables):
        - Identificación del criador/vendedor
        - Número de registro criador
        - Núcleo zoológico
        - Raza
        - Sexo
        - Fecha nacimiento / edad
        - Microchip
        - Vacunas
        - Precio
        - Gastos envío
        - Garantías
        """
        ad_content = data.get("ad_content", {})
        platform = data.get("platform", "web")
        
        # Campos obligatorios base (configurables)
        required_fields = {
            "breeder_name": "Nombre criador/vendedor",
            "breeder_registration": "Número registro criador",
            "zoological_nucleus": "Núcleo zoológico",
            "breed": "Raza",
            "sex": "Sexo",
            "birth_date": "Fecha nacimiento / Edad",
            "microchip": "Microchip",
            "vaccines": "Vacunas",
            "price": "Precio",
            "transport_cost": "Gastos envío",
            "guarantees": "Garantías",
        }
        
        # Campos adicionales por plataforma
        platform_extras = {
            "milanuncios": ["province", "municipality", "photos_min_3"],
            "facebook": ["photos_min_1", "contact_button"],
            "instagram": ["photos_min_1", "hashtags"],
            "web": ["full_description", "photos_min_5", "parent_info"],
        }
        
        required = {**required_fields}
        if platform in platform_extras:
            for extra in platform_extras[platform]:
                required[extra] = platform_extras[platform][extra]
        
        missing = []
        present = []
        
        for field, label in required.items():
            if ad_content.get(field):
                present.append(label)
            else:
                missing.append(label)
        
        # Validaciones específicas de contenido
        content_issues = []
        
        # Verificar que no hay palabras prohibidas
        forbidden_words = [
            "regalo perfecto", "última oportunidad", "sin complicaciones",
            "raza sin problemas", "carácter garantizado", "compra ahora",
            "regalo ideal", "gratis", "oferta limitada",
        ]
        
        text = " ".join(str(v) for v in ad_content.values()).lower()
        for word in forbidden_words:
            if word in text:
                content_issues.append({
                    "code": "FORBIDDEN_WORD",
                    "severity": "high",
                    "message": f"Palabra/frase prohibida detectada: '{word}'",
                    "word": word,
                })
        
        # Verificar que no hay promesas imposibles
        impossible_promises = [
            "nunca enfermará", "garantizado de por vida", "sin problemas de salud",
            "carácter perfecto", "adaptación garantizada",
        ]
        
        for promise in impossible_promises:
            if promise in text:
                content_issues.append({
                    "code": "IMPOSSIBLE_PROMISE",
                    "severity": "critical",
                    "message": f"Promesa imposible detectada: '{promise}'",
                })
        
        return {
            "success": True,
            "check": "ad_content",
            "missing_fields": missing,
            "present_fields": present,
            "content_issues": content_issues,
            "compliance": len(missing) == 0 and len(content_issues) == 0,
        }
    
    async def _generate_incidents_list(self, data: Dict) -> Dict:
        """
        Generar lista consolidada de incidencias de cumplimiento.
        """
        expediente = data.get("expediente", {})
        
        all_incidents = []
        
        # Ejecutar todas las verificaciones
        checks = [
            ("microchip", self._check_microchip),
            ("vaccines", self._check_vaccines),
            ("passport", self._check_passport),
            ("pedigree", self._check_pedigree),
            ("breeder_registration", self._check_breeder_registration),
            ("zoological_nucleus", self._check_zoological_nucleus),
            ("expired_docs", self._detect_expired_docs),
        ]
        
        for check_name, check_func in checks:
            try:
                result = await check_func({"expediente": expediente})
                if not result.get("passed", True):
                    for issue in result.get("issues", []):
                        all_incidents.append({
                            "source": check_name,
                            **issue,
                        })
            except Exception as e:
                logger.error("check_failed", check=check_name, error=str(e))
                all_incidents.append({
                    "source": check_name,
                    "code": "CHECK_ERROR",
                    "severity": "critical",
                    "message": f"Error en verificación {check_name}: {str(e)}",
                })
        
        # Agrupar por severidad
        by_severity = {
            "critical": [i for i in all_incidents if i.get("severity") == "critical"],
            "high": [i for i in all_incidents if i.get("severity") == "high"],
            "medium": [i for i in all_incidents if i.get("severity") == "medium"],
            "low": [i for i in all_incidents if i.get("severity") == "low"],
        }
        
        return {
            "success": True,
            "total_incidents": len(all_incidents),
            "by_severity": by_severity,
            "incidents": all_incidents,
            "compliant": len(by_severity["critical"]) == 0 and len(by_severity["high"]) == 0,
        }
    
    async def _full_compliance_check(self, data: Dict) -> Dict:
        """Ejecutar verificación completa de cumplimiento."""
        expediente = data.get("expediente", {})
        
        results = {}
        
        # Ejecutar todas las verificaciones
        checks = [
            ("microchip", self._check_microchip),
            ("vaccines", self._check_vaccines),
            ("passport", self._check_passport),
            ("pedigree", self._check_pedigree),
            ("breeder_registration", self._check_breeder_registration),
            ("zoological_nucleus", self._check_zoological_nucleus),
            ("expired_docs", self._detect_expired_docs),
        ]
        
        for name, func in checks:
            try:
                results[name] = await func({"expediente": expediente})
            except Exception as e:
                results[name] = {"success": False, "error": str(e)}
        
        # Generar lista de incidencias consolidada
        incidents_result = await self._generate_incidents_list({"expediente": expediente})
        
        # Determinar estado general
        all_passed = all(r.get("passed", False) for r in results.values() if isinstance(r, dict))
        
        return {
            "success": True,
            "compliant": all_passed and results.get("expired_docs", {}).get("summary", {}).get("expired", 0) == 0,
            "checks": results,
            "incidents": incidents_result.get("incidents", []),
            "summary": {
                "total_checks": len(checks),
                "passed": sum(1 for r in results.values() if r.get("passed")),
                "failed": sum(1 for r in results.values() if not r.get("passed", True)),
                "critical_incidents": len([i for i in incidents_result.get("incidents", []) if i.get("severity") == "critical"]),
            },
        }