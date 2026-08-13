# Transvega Animal - Dog Broker System Documentation

## Overview

This system manages the lifecycle of dogs for a breeder/broker business, integrating with Telegram for intake, internal APIs for data management, media processing, content generation, listing creation, and approval workflows.

## Architecture

- **Telegram Intake**: Users send data and media via Telegram; the intake agent creates sessions, stores files locally, and creates dog records.
- **Media Storage**: Files are saved under `/data/dogs/<internal_id>/<purpose>/` with SHA-256 hashes.
- **Media Selection Agent**: Analyzes images (sharpness, exposure, framing, dog visibility) and recommends cover, listing, social media, and disposable media.
- **Content Marketing Agent**: Generates content proposals (individual, breed, litter, generic) using dog data from the internal API.
- **Listing Agent**: Creates draft listings for platforms like Milanuncios (no auto-publish).
- **Approval Workflow**: All content and listings must be approved by humans via the existing approval-agent.
- **Media Generation Agent**: Placeholders for local image, video, TTS generation (future DGX Spark integration).
- **Privacy Router**: Deterministically classifies data as LOCAL_ONLY (media, personal docs) or ONLINE_ALLOWED (non-sensitive text).

## Data Model

- Dogs, Breeds, Litters, DogMedia, DogHealth, DogStatusHistory.
- Each dog has a unique internal ID (e.g., DOG-2026-000001).

## API Endpoints (Integration API)

- `/dogs/` CRUD
- `/dogs/{id}/media`
- `/breeds/`
- `/litters/`
- `/dogs/{id}/health`
- `/dogs/{id}/status`

## Environment Variables

- `INTERNAL_API_URL`: Base URL for internal API (default http://localhost:8000)
- `TELEGRAM_BOT_TOKEN`: Token for Telegram bot
- `TELEGRAM_WEBHOOK_URL`: URL to receive Telegram updates
- `DOG_MEDIA_ROOT`: Root directory for storing media (default /data/dogs)
- `LOCAL_IMAGE_BASE_URL`, `LOCAL_VIDEO_BASE_URL`, `LOCAL_TTS_BASE_URL`: For future local generation services
- `MEDIA_SELECTION_THRESHOLDS`: JSON for sharpness, exposure, dog_visibility thresholds

## Workflow

1. Telegram → Intake Session → Dog Record + Media Storage
2. Media Selection → Scores & Recommendations
3. Content Marketing → Content Proposals
4. Listing Agent → Milanuncios Draft
5. Approval Agent → Human Review → Approved/Rejected
6. (Future) Publishing Agent → Auto-publish to platforms

## Extensibility

- Add new platforms by extending SocialPublisher and ListingAgent.
- Replace stub providers in MediaGenerationAgent with real local services.
- Enhance privacy router with more patterns.

## Testing

- Unit tests for schemas: `test_dog_schemas_standalone.py`
- Run with: `python test_dog_schemas_standalone.py`

## Deployment

- Use Docker Compose for development.
- Ensure media directory is mounted.
- Configure Telegram webhook to point to `/telegram/webhook` endpoint.
