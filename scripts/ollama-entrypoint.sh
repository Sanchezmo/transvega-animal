#!/bin/sh
# Ollama Entrypoint Script
# Handles model pulling and custom model creation on container startup

set -e

# Start ollama serve in background
echo "Starting Ollama server..."
ollama serve &
SERVER_PID=$!

# Wait for server to be ready
echo 'Waiting for Ollama server to start...'
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo 'Ollama server is ready'
        break
    fi
    sleep 2
done

# Function to split semicolon-separated string (POSIX compatible)
split_semicolon() {
    echo "$1" | tr ';' '\n'
}

# Function to split comma-separated string (POSIX compatible)
split_comma() {
    echo "$1" | tr ',' '\n'
}

# Pull base models from OLLAMA_MODELS env var
if [ -n "$OLLAMA_MODELS" ]; then
    echo "Pulling base models: $OLLAMA_MODELS"
    for model in $(split_comma "$OLLAMA_MODELS"); do
        model=$(echo "$model" | xargs)  # trim whitespace
        if [ -n "$model" ]; then
            echo "Pulling base model: $model"
            ollama pull "$model" || echo "Warning: Failed to pull $model"
        fi
    done
    echo 'All base models pulled'
else
    echo 'No OLLAMA_MODELS specified, skipping model pull'
fi

# Create custom models with optimized parameters from OLLAMA_CUSTOM_MODELS
# Format: "model-name:base-model,param1=val1,param2=val2;model2:base2,param1=val1"
# Multiple custom models separated by semicolon (;)
if [ -n "$OLLAMA_CUSTOM_MODELS" ]; then
    echo "Creating custom models: $OLLAMA_CUSTOM_MODELS"
    for custom in $(split_semicolon "$OLLAMA_CUSTOM_MODELS"); do
        custom=$(echo "$custom" | xargs)
        if [ -n "$custom" ]; then
            # Parse: name:base,param1=val1,param2=val2
            name=$(echo "$custom" | cut -d':' -f1)
            rest=$(echo "$custom" | cut -d':' -f2-)
            
            # base is everything before first comma in rest
            base=$(echo "$rest" | cut -d',' -f1)
            # params is everything after first comma in rest
            params=$(echo "$rest" | cut -d',' -f2-)
            
            echo "Creating custom model: $name from $base with params: $params"
            
            # Create Modelfile using printf
            printf "FROM %s\n" "$base" > /tmp/Modelfile-$name
            
            # Add parameters
            for param in $(split_comma "$params"); do
                param=$(echo "$param" | xargs)
                if [ -n "$param" ]; then
                    key=$(echo "$param" | cut -d'=' -f1)
                    val=$(echo "$param" | cut -d'=' -f2-)
                    printf "PARAMETER %s %s\n" "$key" "$val" >> /tmp/Modelfile-$name
                fi
            done
            
            # Create the custom model
            ollama create "$name" -f /tmp/Modelfile-$name || echo "Warning: Failed to create $name"
        fi
    done
    echo 'All custom models created'
else
    echo 'No OLLAMA_CUSTOM_MODELS specified, skipping custom model creation'
fi

# Wait for server process
wait $SERVER_PID
