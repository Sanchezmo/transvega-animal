# Milanuncios Bot - Dockerfile
FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libu2f-udev \
    libvulkan1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Copy bot code
COPY bot/ ./bot/
COPY SKILL.md .

# Create storage directory
RUN mkdir -p /app/storage && chown -R botuser:botuser /app

USER botuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEADLESS=true \
    LOG_LEVEL=INFO

# Entrypoint
ENTRYPOINT ["python", "-m", "bot.renew_all"]