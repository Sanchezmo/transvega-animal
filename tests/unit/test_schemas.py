"""
Tests unitarios para esquemas y validaciones.
"""
import pytest
from pydantic import ValidationError

from app.schemas import (
    ThirdPartyCreate,
    ThirdPartyUpdate,
    ProductCreate,
    ProductUpdate,
    ExpedienteAnimalCreate,
    ExpedienteAnimalUpdate,
    VaccineRecord,
    DewormingRecord,
    CertificateRecord,
    InvoiceCreate,
    InvoiceLineCreate,
    LeadCreate,
    LeadUpdate,
    PublicationCreate,
    ApprovalRequestCreate,
    TaskCreate,
)


class TestThirdPartySchemas:
    """Tests para esquemas de terceros."""
    
    def test_create_tercero_valido(self):
        """Crear tercero válido."""
        data = {
            "name": "Juan Pérez",
            "email": "juan@test.es",
            "phone": "+34 600 123 456",
            "client": 1,
            "supplier": 0,
        }
        tercero = ThirdPartyCreate(**data)
        assert tercero.name == "Juan Pérez"
        assert tercero.client == 1
        assert tercero.supplier == 0
    
    def test_create_tercero_email_invalido(self):
        """Email inválido debe fallar."""
        with pytest.raises(ValidationError):
            ThirdPartyCreate(
                name="Test",
                email="email-invalido",
                client=1,
            )
    
    def test_create_tercero_campos_obligatorios(self):
        """Nombre es obligatorio."""
        with pytest.raises(ValidationError):
            ThirdPartyCreate(
                email="test@test.es",
            )
    
    def test_update_tercero_parcial(self):
        """Actualización parcial válida."""
        update = ThirdPartyUpdate(
            phone="+34 600 999 888",
            address="Nueva dirección",
        )
        assert update.phone == "+34 600 999 888"
        assert update.address == "Nueva dirección"
        assert update.name is None


class TestProductSchemas:
    """Tests para esquemas de productos."""
    
    def test_create_producto_valido(self):
        """Crear producto válido."""
        data = {
            "ref": "DOG-GOLDEN-001",
            "label": "Golden Retriever LOE",
            "price": 1500.00,
            "tva_tx": 21.0,
            "type": 0,
        }
        producto = ProductCreate(**data)
        assert producto.ref == "DOG-GOLDEN-001"
        assert producto.price == 1500.00
        assert producto.tva_tx == 21.0
    
    def test_create_producto_precio_negativo_falla(self):
        """Precio negativo debe fallar."""
        with pytest.raises(ValidationError):
            ProductCreate(
                ref="TEST-001",
                label="Test",
                price=-100.0,
            )
    
    def test_update_producto_parcial(self):
        """Actualización parcial."""
        update = ProductUpdate(
            price=1600.00,
            tva_tx=10.0,
        )
        assert update.price == 1600.00
        assert update.tva_tx == 10.0
        assert update.ref is None


class TestExpedienteAnimalSchemas:
    """Tests para esquemas de expedientes animales."""
    
    def test_create_expediente_valido(self):
        """Crear expediente válido con todos los campos requeridos."""
        data = {
            "name": "Luna",
            "species": "perro",
            "breed": "Golden Retriever",
            "sex": "H",
            "birth_date": "2024-01-15",
            "color": "Dorado",
            "weight_kg": 12.5,
            "microchip": "941000012345678",
            "breed": "Golden Retriever",
            "color": "Dorado",
            "purchase_price": 800.00,
            "sale_price": 1500.00,
            "commercial_status": "draft",
        }
        exp = ExpedienteAnimalCreate(**data)
        assert exp.name == "Luna"
        assert exp.breed == "Golden Retriever"
        assert exp.microchip == "941000012345678"
        assert exp.sex == "H"
    
    def test_microchip_invalido_corta(self):
        """Microchip demasiado corto debe fallar."""
        with pytest.raises(ValidationError):
            ExpedienteAnimalCreate(
                name="Test",
                breed="Golden",
                sex="H",
                birth_date="2024-01-15",
                color="Dorado",
                weight_kg=10.0,
                microchip="12345",  # Muy corto
            )
    
    def test_microchip_invalido_letras(self):
        """Microchip con letras debe fallar."""
        with pytest.raises(ValidationError):
            ExpedienteAnimalCreate(
                name="Test",
                breed="Golden",
                sex="H",
                birth_date="2024-01-15",
                color="Dorado",
                weight_kg=10.0,
                microchip="94100001234567A",  # Con letra
            )
    
    def test_sexo_invalido(self):
        """Sexo inválido debe fallar."""
        with pytest.raises(ValidationError):
            ExpedienteAnimalCreate(
                name="Test",
                breed="Golden",
                sex="X",  # Inválido
                birth_date="2024-01-15",
                color="Dorado",
                weight_kg=10.0,
                microchip="941000012345678",
            )
    
    def test_vaccine_record_valido(self):
        """Registro de vacuna válido."""
        vaccine = VaccineRecord(
            name="Polivalente",
            date="2024-01-10",
            batch="L24001",
            vet="Dr. Gómez",
        )
        assert vaccine.name == "Polivalente"
        assert vaccine.batch == "L24001"
    
    def test_certificate_record_valido(self):
        """Registro de certificado válido."""
        cert = CertificateRecord(
            type="veterinary_health",
            date="2024-01-20",
            issuer="Dr. Gómez",
            expires_at="2024-07-20",
        )
        assert cert.type == "veterinary_health"
        assert cert.issuer == "Dr. Gómez"
    
    def test_estado_comercial_invalido(self):
        """Estado comercial inválido debe fallar."""
        with pytest.raises(ValidationError):
            ExpedienteAnimalCreate(
                name="Test",
                breed="Golden",
                sex="H",
                birth_date="2024-01-15",
                color="Dorado",
                weight_kg=10.0,
                microchip="941000012345678",
                commercial_status="estado_inexistente",
            )
    
    def test_update_expediente_parcial(self):
        """Actualización parcial de expediente."""
        update = ExpedienteAnimalUpdate(
            sale_price=1600.00,
            commercial_status="available",
            weight_kg=13.0,
        )
        assert update.sale_price == 1600.00
        assert update.commercial_status == "available"
        assert update.weight_kg == 13.0
        assert update.name is None


class TestInvoiceSchemas:
    """Tests para esquemas de facturas."""
    
    def test_create_invoice_valida(self):
        """Crear factura válida con líneas."""
        data = {
            "thirdparty_id": 1,
            "date": "2024-02-20",
            "lines": [
                {
                    "description": "Cachorro Golden Retriever",
                    "qty": 1,
                    "unit_price": 1500.00,
                    "vat_rate": 21.0,
                }
            ],
        }
        invoice = InvoiceCreate(**data)
        assert invoice.thirdparty_id == 1
        assert len(invoice.lines) == 1
        assert invoice.lines[0].unit_price == 1500.00
    
    def test_invoice_sin_lineas_falla(self):
        """Factura sin líneas debe fallar."""
        with pytest.raises(ValidationError):
            InvoiceCreate(
                thirdparty_id=1,
                lines=[],
            )
    
    def test_linea_con_descuento(self):
        """Línea con descuento válido."""
        line = InvoiceLineCreate(
            description="Producto test",
            qty=2,
            unit_price=100.00,
            vat_rate=21.0,
            discount_percent=10.0,
        )
        assert line.discount_percent == 10.0
        assert line.qty == 2


class TestLeadSchemas:
    """Tests para esquemas de leads."""
    
    def test_create_lead_valido(self):
        """Crear lead válido."""
        data = {
            "first_name": "Juan",
            "last_name": "Pérez",
            "email": "juan@test.es",
            "phone": "+34 600 123 456",
            "country": "ES",
            "source": "web",
        }
        lead = LeadCreate(**data)
        assert lead.first_name == "Juan"
        assert lead.email == "juan@test.es"
        assert lead.country == "ES"
    
    def test_lead_email_invalido(self):
        """Email inválido debe fallar."""
        with pytest.raises(ValidationError):
            LeadCreate(
                first_name="Test",
                last_name="Test",
                email="email-invalido",
                phone="+34 600 123 456",
                country="ES",
                source="web",
            )
    
    def test_lead_pais_codigo_invalido(self):
        """Código de país inválido debe fallar."""
        with pytest.raises(ValidationError):
            LeadCreate(
                first_name="Test",
                last_name="Test",
                email="test@test.es",
                phone="+34 600 123 456",
                country="ESPAÑA",  # Debe ser código ISO
                source="web",
            )
    
    def test_update_lead_parcial(self):
        """Actualización parcial de lead."""
        update = LeadUpdate(
            status="qualified",
            score=85,
            budget_min=1500,
            budget_max=2500,
        )
        assert update.status == "qualified"
        assert update.score == 85
        assert update.budget_min == 1500
        assert update.budget_max == 2500


class TestPublicationSchemas:
    """Tests para esquemas de publicaciones."""
    
    def test_create_publicacion_valida(self):
        """Crear publicación válida."""
        data = {
            "expediente_id": 1,
            "platform": "milanuncios",
            "title": "Cachorro Golden Retriever LOE",
            "description": "Precioso cachorro...",
            "price": 1500.00,
        }
        pub = PublicationCreate(**data)
        assert pub.expediente_id == 1
        assert pub.platform == "milanuncios"
        assert pub.price == 1500.00
    
    def test_platform_invalida(self):
        """Plataforma inválida debe fallar."""
        with pytest.raises(ValidationError):
            PublicationCreate(
                expediente_id=1,
                platform="plataforma_inexistente",
                title="Test",
                description="Desc",
            )
    
    def test_titulo_muy_corto(self):
        """Título muy corto debe fallar."""
        with pytest.raises(ValidationError):
            PublicationCreate(
                expediente_id=1,
                platform="web",
                title="Ab",  # Muy corto
                description="Descripción suficiente larga para test",
            )


class TestApprovalSchemas:
    """Tests para esquemas de aprobaciones."""
    
    def test_create_aprobacion_valida(self):
        """Crear solicitud de aprobación válida."""
        data = {
            "action": "validate_invoice",
            "resource_type": "invoice",
            "resource_id": "1",
            "reason": "Factura lista para validar",
            "current_state": {"status": 0},
            "proposed_state": {"status": 1},
        }
        approval = ApprovalRequestCreate(**data)
        assert approval.action == "validate_invoice"
        assert approval.resource_type == "invoice"
        assert approval.resource_id == "1"
    
    def test_aprobacion_sin_razon_falla(self):
        """Aprobación sin razón debe fallar."""
        with pytest.raises(ValidationError):
            ApprovalRequestCreate(
                action="validate_invoice",
                resource_type="invoice",
                resource_id="1",
                reason="",  # Vacío
                current_state={},
                proposed_state={},
            )


class TestTaskSchemas:
    """Tests para esquemas de tareas."""
    
    def test_create_tarea_valida(self):
        """Crear tarea válida."""
        data = {
            "task_type": "publish_announcement",
            "priority": 5,
            "agent_id": "agent_publishing",
            "input_data": {"expediente_id": 1, "platform": "milanuncios"},
            "timeout_seconds": 3600,
        }
        task = TaskCreate(**data)
        assert task.task_type == "publish_announcement"
        assert task.priority == 5
        assert task.agent_id == "agent_publishing"
    
    def test_tarea_prioridad_invalida(self):
        """Prioridad fuera de rango debe fallar."""
        with pytest.raises(ValidationError):
            TaskCreate(
                task_type="test",
                priority=15,  # Max 10
            )
    
    def test_tarea_timeout_invalido(self):
        """Timeout fuera de rango debe fallar."""
        with pytest.raises(ValidationError):
            TaskCreate(
                task_type="test",
                timeout_seconds=30,  # Min 60
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])