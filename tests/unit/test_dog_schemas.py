"""
Unit tests for dog-related Pydantic schemas.
"""

from datetime import date, datetime

from app.schemas import (
    BreedCreate,
    BreedResponse,
    DogCreate,
    DogHealthCreate,
    DogHealthResponse,
    DogMediaCreate,
    DogMediaResponse,
    DogResponse,
    DogStatusHistoryCreate,
    DogStatusHistoryResponse,
    LitterCreate,
    LitterResponse,
)


def test_breed_schema():
    """Test Breed schema validation."""
    data = {
        "name": "Labrador Retriever",
        "description": "Friendly and outgoing breed",
        "average_weight_kg": 30.0,
        "average_height_cm": 55.0,
        "life_expectancy_years": 12,
        "temperament": "Kind, outgoing, tractable",
        "good_with_children": True,
        "good_with_other_dogs": True,
        "energy_level": "medium",
        "grooming_needs": "medium",
    }
    breed = BreedCreate(**data)
    assert breed.name == "Labrador Retriever"
    assert breed.average_weight_kg == 30.0

    # Test response schema includes id and timestamps
    response_data = data.copy()
    response_data.update(
        {
            "id": 1,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
    )
    response = BreedResponse(**response_data)
    assert response.id == 1
    assert response.name == "Labrador Retriever"


def test_litter_schema():
    """Test Litter schema validation."""
    data = {
        "name": "Litter of Champions",
        "breed_id": 1,
        "mother_id": 10,
        "father_id": 15,
        "birth_date": date(2026, 6, 10),
        "size": 6,
        "registration_number": "LOE-123456",
    }
    litter = LitterCreate(**data)
    assert litter.name == "Litter of Champions"
    assert litter.size == 6

    response_data = data.copy()
    response_data.update(
        {
            "id": 1,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
    )
    response = LitterResponse(**response_data)
    assert response.id == 1
    assert response.breed_id == 1


def test_dog_schema():
    """Test Dog schema validation."""
    data = {
        "name": "Buddy",
        "breed_id": 1,
        "litter_id": 1,
        "sex": "M",
        "birth_date": date(2026, 6, 10),
        "color": "Golden",
        "microchip": "123456789012345",
        "sire_name": "Champion Sire",
        "dam_name": "Champion Dam",
        "pedigree": "LOE123456",
        "vet_status": "healthy",
        "purchase_price": 1000.0,
        "sale_price": 2000.0,
        "associated_costs": 500.0,
        "expediente_id": 100,
    }
    dog = DogCreate(**data)
    assert dog.name == "Buddy"
    assert dog.microchip == "123456789012345"
    assert dog.sex == "M"

    response_data = data.copy()
    response_data.update(
        {
            "id": 1,
            "internal_id": "DOG-2026-00001",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "created_by": 1,
            "updated_by": 1,
        }
    )
    response = DogResponse(**response_data)
    assert response.id == 1
    assert response.internal_id == "DOG-2026-00001"
    assert response.name == "Buddy"


def test_dog_media_schema():
    """Test DogMedia schema validation."""
    data = {
        "file_path": "/data/dogs/DOG-2026-00001/original/photo1.jpg",
        "file_hash": "a" * 64,  # SHA-256
        "mime_type": "image/jpeg",
        "width": 1920,
        "height": 1080,
        "media_type": "photo",
        "purpose": "original",
        "dog_id": 1,
        "uploaded_by": 1,
    }
    media = DogMediaCreate(**data)
    assert media.file_path.startswith("/data/dogs/")
    assert len(media.file_hash) == 64
    assert media.media_type == "photo"

    response_data = data.copy()
    response_data.update(
        {
            "id": 1,
            "created_at": datetime.now(),
        }
    )
    response = DogMediaResponse(**response_data)
    assert response.id == 1
    assert response.dog_id == 1


def test_dog_health_schema():
    """Test DogHealth schema validation."""
    data = {
        "vet_check_date": date(2026, 8, 13),
        "weight_kg": 5.5,
        "temperature_celsius": 38.5,
        "heart_rate_bpm": 120,
        "respiratory_rate": 30,
        "stool_condition": "normal",
        "urine_condition": "normal",
        "appetite": "good",
        "energy_level": "medium",
        "notes": "Healthy puppy",
        "next_check_date": date(2026, 9, 13),
    }
    health = DogHealthCreate(**data)
    assert health.weight_kg == 5.5
    assert health.temperature_celsius == 38.5

    response_data = data.copy()
    response_data.update(
        {
            "id": 1,
            "dog_id": 1,
            "recorded_at": datetime.now(),
        }
    )
    response = DogHealthResponse(**response_data)
    assert response.id == 1
    assert response.dog_id == 1
    assert response.weight_kg == 5.5


def test_dog_status_history_schema():
    """Test DogStatusHistory schema validation."""
    data = {
        "status": "available",
        "changed_by": 1,
        "change_reason": "Made available for sale",
    }
    history = DogStatusHistoryCreate(**data)
    assert history.status == "available"
    assert history.changed_by == 1

    response_data = data.copy()
    response_data.update(
        {
            "id": 1,
            "dog_id": 1,
            "changed_at": datetime.now(),
        }
    )
    response = DogStatusHistoryResponse(**response_data)
    assert response.id == 1
    assert response.dog_id == 1
    assert response.status == "available"


if __name__ == "__main__":
    test_breed_schema()
    test_litter_schema()
    test_dog_schema()
    test_dog_media_schema()
    test_dog_health_schema()
    test_dog_status_history_schema()
    print("All tests passed!")
