#!/bin/sh
# Ollama Entrypoint Script for Transvega
# Creates the single multimodal model 'transvega-local' on container startup

set -eu

# Model configuration
OLLAMA_MODEL="${OLLAMA_MODEL:-transvega-local}"
OLLAMA_BASE_MODEL="${OLLAMA_BASE_MODEL:-qwen3.5:4b-q4_K_M}"
MODELFILE_PATH="${MODELFILE_PATH:-/app/infrastructure/ollama/Modelfile}"

# Start ollama serve in background
echo "Starting Ollama server..."
ollama serve &
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for Ollama server to start..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Ollama server is ready"
        break
    fi
    sleep 2
done

# Create the single multimodal model if it doesn't exist
echo "Checking for model: $OLLAMA_MODEL"
if ollama list | grep -q "^$OLLAMA_MODEL"; then
    echo "Model $OLLAMA_MODEL already exists, skipping creation"
else
    echo "Creating model $OLLAMA_MODEL from $OLLAMA_BASE_MODEL using Modelfile: $MODELFILE_PATH"
    if [ -f "$MODELFILE_PATH" ]; then
        ollama create "$OLLAMA_MODEL" -f "$MODELFILE_PATH"
    else
        echo "Warning: Modelfile not found at $MODELFILE_PATH, creating with basic parameters"
        # Fallback inline Modelfile
        printf "FROM %s\nPARAMETER num_thread 10\nPARAMETER num_ctx 8192\nPARAMETER temperature 0.1\n" "$OLLAMA_BASE_MODEL" > /tmp/Modelfile-fallback
        ollama create "$OLLAMA_MODEL" -f /tmp/Modelfile-fallback
    fi
    echo "Model $OLLAMA_MODEL created successfully"
fi

echo "Ollama is ready with model: $OLLAMA_MODEL"
ollama list

# Wait for server process
wait $SERVER_PID