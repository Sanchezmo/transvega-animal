"""
SQLAlchemy models for dog-related entities.
"""
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (Enum, ForeignKey, Integer, String, Text, DateTime, Float, Boolean,
                        Column, Index, CheckConstraint, UniqueConstraint)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.base import Base  # Import the Base from base.py (avoid circular import)


class Breed(Base):
    __tablename__ = "breeds"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    average_weight_kg = Column(Float, nullable=True)
    average_height_cm = Column(Float, nullable=True)
    life_expectancy_years = Column(Integer, nullable=True)
    temperament = Column(String(200), nullable=True)
    good_with_children = Column(Boolean, nullable=True)
    good_with_other_dogs = Column(Boolean, nullable=True)
    energy_level = Column(String(20), nullable=True)  # low, medium, high
    grooming_needs = Column(String(20), nullable=True)  # low, medium, high
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    dogs = relationship("Dog", back_populates="breed")
    litters = relationship("Litter", back_populates="breed")
    
    __table_args__ = (
        UniqueConstraint('name', name='uq_breed_name'),
    )


class Litter(Base):
    __tablename__ = "litters"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    breed_id = Column(Integer, ForeignKey("breeds.id"), nullable=False, index=True)
    mother_id = Column(Integer, ForeignKey("dogs.id"), nullable=False, index=True)
    father_id = Column(Integer, ForeignKey("dogs.id"), nullable=True, index=True)
    birth_date = Column(DateTime, nullable=False)
    size = Column(Integer, nullable=False)
    registration_number = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    breed = relationship("Breed", back_populates="litters")
    mother = relationship("Dog", foreign_keys=[mother_id], back_populates="litters_as_mother")
    father = relationship("Dog", foreign_keys=[father_id], back_populates="litters_as_father")
    puppies = relationship("Dog", foreign_keys="Dog.litter_id", back_populates="litter")
    
    __table_args__ = (
        UniqueConstraint('name', 'breed_id', name='uq_litter_name_breed'),
    )


class DogMedia(Base):
    __tablename__ = "dog_media"
    
    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(128), nullable=False, unique=True, index=True)  # SHA-256 or similar
    mime_type = Column(String(100), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)  # for videos
    media_type = Column(String(20), nullable=False)  # photo or video
    purpose = Column(String(20), nullable=False)  # original, processed, social, listing
    dog_id = Column(Integer, ForeignKey("dogs.id"), nullable=False, index=True)
    uploaded_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    dog = relationship("Dog", back_populates="media")
    
    __table_args__ = (
        CheckConstraint("media_type IN ('photo', 'video')", name='ck_dog_media_media_type'),
        CheckConstraint("purpose IN ('original', 'processed', 'social', 'listing')", name='ck_dog_media_purpose'),
    )


class DogHealth(Base):
    __tablename__ = "dog_health"
    
    id = Column(Integer, primary_key=True, index=True)
    dog_id = Column(Integer, ForeignKey("dogs.id"), nullable=False, index=True)
    vet_check_date = Column(DateTime, nullable=True)
    weight_kg = Column(Float, nullable=True)
    temperature_celsius = Column(Float, nullable=True)
    heart_rate_bpm = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    stool_condition = Column(String(20), nullable=True)  # normal, soft, diarrhea, constipated
    urine_condition = Column(String(20), nullable=True)  # normal, cloudy, bloody
    appetite = Column(String(20), nullable=True)  # poor, fair, good, excellent
    energy_level = Column(String(20), nullable=True)  # low, medium, high
    notes = Column(Text, nullable=True)
    next_check_date = Column(DateTime, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    dog = relationship("Dog", back_populates="health_records")


class DogStatusHistory(Base):
    __tablename__ = "dog_status_history"
    
    id = Column(Integer, primary_key=True, index=True)
    dog_id = Column(Integer, ForeignKey("dogs.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False)  # draft, available, reserved, sold, inactive
    changed_by = Column(Integer, nullable=False)
    change_reason = Column(Text, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    dog = relationship("Dog", back_populates="status_history")
    
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'available', 'reserved', 'sold', 'inactive')", name='ck_dog_status_history_status'),
    )


class Dog(Base):
    __tablename__ = "dogs"
    
    id = Column(Integer, primary_key=True, index=True)
    internal_id = Column(String(50), nullable=False, unique=True, index=True)  # e.g., DOG-2026-000001
    name = Column(String(200), nullable=False)
    breed_id = Column(Integer, ForeignKey("breeds.id"), nullable=False, index=True)
    litter_id = Column(Integer, ForeignKey("litters.id"), nullable=True, index=True)
    sex = Column(String(1), nullable=False)  # M or H
    birth_date = Column(DateTime, nullable=False)
    color = Column(String(50), nullable=False)
    microchip = Column(String(15), nullable=False, unique=True, index=True)  # ISO 11784/11785
    sire_name = Column(String(200), nullable=True)
    dam_name = Column(String(200), nullable=True)
    pedigree = Column(String(100), nullable=True)
    vet_status = Column(String(50), nullable=False, default="healthy")
    purchase_price = Column(Float, nullable=False, default=0.0)
    sale_price = Column(Float, nullable=False, default=0.0)
    associated_costs = Column(Float, nullable=False, default=0.0)
    expediente_id = Column(Integer, nullable=True, index=True)  # Reference to ExpedienteAnimal in Dolibarr (optional)
    status = Column(String(20), nullable=False, default="draft")  # draft, available, reserved, sold, inactive
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, nullable=False, default=1)
    
    # Relationships
    breed = relationship("Breed", back_populates="dogs")
    litter = relationship("Litter", foreign_keys=[litter_id], back_populates="puppies")
    litters_as_mother = relationship("Litter", foreign_keys="Litter.mother_id", back_populates="mother")
    litters_as_father = relationship("Litter", foreign_keys="Litter.father_id", back_populates="father")
    media = relationship("DogMedia", back_populates="dog")
    health_records = relationship("DogHealth", back_populates="dog")
    status_history = relationship("DogStatusHistory", back_populates="dog")
    
    __table_args__ = (
        CheckConstraint("sex IN ('M', 'H')", name='ck_dog_sex'),
        CheckConstraint("status IN ('draft', 'available', 'reserved', 'sold', 'inactive')", name='ck_dog_status'),
        CheckConstraint("purchase_price >= 0", name='ck_dog_purchase_price_nonneg'),
        CheckConstraint("sale_price >= 0", name='ck_dog_sale_price_nonneg'),
        CheckConstraint("associated_costs >= 0", name='ck_dog_associated_costs_nonneg'),
    )


class Publication(Base):
    __tablename__ = "publications"

    id = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, nullable=False, index=True)  # Reference to ExpedienteAnimal in Dolibarr
    platform = Column(String(50), nullable=False, index=True)  # milanuncios, facebook, instagram, tiktok, web
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    photos = Column(Text, nullable=True)  # JSON array of photo paths/URLs
    price = Column(Float, nullable=True)
    external_id = Column(String(100), nullable=True, index=True)  # External platform listing ID
    external_url = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="draft", index=True)  # draft, pending_approval, approved, published, expired, removed, failed
    approval_id = Column(UUID, nullable=True)  # Reference to approval workflow
    published_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    last_renewed_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_by = Column(Integer, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    unpublished_by = Column(Integer, nullable=True)
    unpublished_at = Column(DateTime, nullable=True)
    unpublish_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'pending_approval', 'approved', 'published', 'expired', 'removed', 'failed')", name='ck_publication_status'),
        CheckConstraint("platform IN ('web', 'milanuncios', 'facebook', 'instagram', 'tiktok')", name='ck_publication_platform'),
    )
