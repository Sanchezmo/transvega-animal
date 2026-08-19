# Transvega Animal - Dog Broker System Documentation

## Overview

This system manages the lifecycle of dogs for a breeder/broker business, integrating with Telegram for intake, internal APIs for data management, media processing, content generation, listing creation, approval workflows, and supplier invoice processing.

## Architecture

```text
                         � ┌──────────────────────�┐
                         │       TELEGRAM       │
                         └──────────�┬───────────�┘
                                    � ↓
                              Hermes Gateway
                                    � ↓
                              PrivacyRouter
                         � ┌──────────�┴───────────�┐
                         � ↓                      � ↓
                    LOCAL_ONLY            CLOUD_ALLOWED
                         � ↓                      � ↓
                   Ollama local          ModelRouter
                         � ↓                      � ↓
                 modelos pequeños        NVIDIA API
                         │                      │
                         └──────────�┬───────────�┘
                                    � ↓
                               Orchestrator
                                    � ↓
              � ┌─────────────────────�┼─────────────────────�┐
              � ↓                     � ↓                     � ↓
       Dolibarr Service        Media Agent         Publishing Agent
```

### Components

- **Telegram Gateway**: Receives updates from Telegram bot.
- **PrivacyRouter**: Deterministically classifies data as `LOCAL_ONLY` (private) or `CLOUD_ALLOWED` (public) before any AI call.
- **Ollama local**: Runs small language models (�≈4B‑8B parameters) for private tasks (e.g., supplier invoice OCR/extraction).
- **ModelRouter**: Routes requests to Ollama (LOCAL_ONLY) or NVIDIA API (CLOUD_ALLOWED) based on privacy scope.
- **Orchestrator**: Coordinates workflows and workers.
- **Dolibarr Service**: Accesses Dolibarr ERP via its API (source of truth for accounting, customers, suppliers).
- **Media Agent**: Generates/analyzes media for dogs using NVIDIA API (content is public).
- **Publishing Agent**: Handles assisted and automatic publishing to platforms (Milanuncios via Playwright, Facebook, Instagram, TikTok).
- **PostgreSQL**: Primary database for Hermes (users, sessions, etc.).
- **Redis**: For caching and job queues.
- **Ollama**: Local LLM service (private, no GPU required).
- **NVIDIA API**: External provider for heavy AI tasks (image generation, vision, complex reasoning) when data is non‑sensitive.
- **Playwright / Milanuncios Worker**: Automates browser for Milanuncios listings.

### Data Flow Examples

#### 1. Supplier Invoice Processing (LOCAL_ONLY)
1. User sends invoice PDF/photo via Telegram.
2. Gateway forwards to PrivacyRouter → classifies as `LOCAL_ONLY`.
3. InvoiceWorker (queued job) extracts text:
   - If PDF has text layer → extract directly.
   - If scanned → use Ollama with vision model for OCR.
4. Extracted text sent to Ollama with prompt to produce structured JSON (supplier, invoice number, lines, taxes, total).
5. JSON validated with Pydantic.
6. Deterministic checks: sum of lines, VAT, total, CIF/NIF format, duplicate search in Dolibarr.
7. Result sent to user for approval (Telegram with buttons).
8. On approval, DolibarrIntegrationService creates supplier invoice via Dolibarr API.
9. Invoice recorded; PDF stored under `/data/invoices/<supplier>/`.

#### 2. Customer Invoicing (No IA)
- User creates order via Telegram or internal workflow.
- Hermes Service retrieves structured data from Dolibarr (customer, products, prices).
- Calls DolibarrIntegrationService to create customer invoice.
- Dolibarr generates PDF; Hermes may store/share it.
- No OCR, vision, or LLM involved.

#### 3. Dog Media & Content (CLOUD_ALLOWED)
1. Intake receives dog data and media via Telegram → stored locally, marked `LOCAL_ONLY` (private raw files).
2. MediaSelectionAgent analyzes images (sharpness, exposure, dog visibility) using local heuristics (no AI needed).
3. ContentMarketingAgent requests suggested copy/media; if it needs vision or generation, uses ModelRouter → NVIDIA API (since output is public).
4. PublishingAgent creates assisted instructions or auto‑publishes to Milanuncios (Playwright) or social media (NVIDIA API for image/video generation if needed).
5. All generated content is considered public and safe for cloud processing.

### API Endpoints (Integration API)

- `/dogs/` CRUD
- `/dogs/{id}/media`
- `/breeds/`
- `/litters/`
- `/dogs/{id}/health`
- `/dogs/{id}/status`
- `/supplier-invoices/` (internal worker endpoints)
- `/telegram/webhook`

### Environment Variables

- `INTERNAL_API_URL`: Base URL for internal API (default http://localhost:8000)
- `TELEGRAM_BOT_TOKEN`: Token for Telegram bot
- `TELEGRAM_WEBHOOK_URL`: URL to receive Telegram updates
- `DOG_MEDIA_ROOT`: Root directory for storing media (default /data/dogs)
- `INVOICE_STORAGE_ROOT`: Root for supplier invoices (default /data/invoices)
- `OLLAMA_ENDPOINT`: http://ollama:11434
- `OLLAMA_MODEL`: e.g., transvega-local
- `OLLAMA_BASE_MODEL`: e.g., qwen3.5:4b-q4_K_M
- `NVIDIA_API_KEY`: Key for NVIDIA API
- `NVIDIA_BASE_URL`: https://api.nvidia.com/v1
- `MEDIA_SELECTION_THRESHOLDS`: JSON for sharpness, exposure, dog_visibility thresholds
- `PLATFORMS`: Configuration for each platform (e.g., Milanuncios credentials)
- `PRIVACY_RULES_PATH`: Path to YAML/JSON with regex patterns for LOCAL_ONLY vs CLOUD_ALLOWED

### Worker Jobs

- **InvoiceWorker**: Processes supplier invoice files (PDF/images) → uses Ollama for extraction → validation → approval → Dolibarr.
- **MediaWorker** (optional): Heavy media generation/tasks using NVIDIA API.
- **PublishingWorker**: Handles publishing queue (Milanuncios via Playwright, social media via APIs).

### Extensibility

- Add new platforms by extending `PublishingAgent` with platform‑specific adapters.
- Replace Ollama providers with other local backends (vLLM, Llama.cpp) via `ModelRouter` interface.
- Enhance `PrivacyRouter` with more patterns without changing agents.
- Add new AI tasks by defining new methods in `ModelProvider` and routing them via `ModelRouter`.

### Testing

- Unit tests for schemas: `test_dog_schemas_standalone.py`
- Integration test for intake flow: `test_integration_flow.py`
- Integration test for publishing: `test_publishing_simple.py`
- Run with: `PYTHONPATH=$(pwd):$(pwd)/services/integration-api source venv/bin/activate && python <test>`

### Deployment

- Use Docker Compose for development.
- Ensure media and invoice directories are mounted as volumes.
- Configure Telegram webhook to point to `/telegram/webhook` endpoint.
- Ollama service runs internally (no host port exposed).
- NVIDIA API is external; only API key needed.
- For Milanuncios automation via Playwright, ensure a compatible browser is available (Chromium).
