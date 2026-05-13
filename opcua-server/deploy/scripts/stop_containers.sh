#!/bin/bash

# Configure paths
IMAGE_NAME="opcua-server:latest"
ENV_DIR="../envs"
LOG_FILE="../logs/report.log"
LOG_DIR=$(dirname $LOG_FILE)

# Ensure the log folder exists
mkdir -p "$LOG_DIR"

# TODO: comment this function
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

echo > $LOG_FILE
log_message "--- Report start: $(date) ---"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    log_message "ERROR: Docker not installed or not in PATH."
    exit 1
fi

# Check if ENV_DIR extists
if [ ! -d "$ENV_DIR" ]; then
    log_message "ERROR: folder $ENV_DIR does not extist."
    exit 1
fi

# Stop and remove containers
for env_file in "$ENV_DIR"/*.env; do
    # Check if some .env file actually exist
    [ -e "$env_file" ] || continue
    
    log_message "Processing file: $env_file"
    
    # Get the file name (used as container name)
    file_name=$(basename "$env_file" .env)
    
    if docker stop "$file_name" >> "$LOG_FILE" 2>&1 && \
        docker rm "$file_name" >> "$LOG_FILE" 2>&1; then
        log_message "INFO: Container successfully stopped and removed for: $file_name"
    else
        log_message "ERROR: Failed to stop and remove container for: $file_name"
    fi
done

log_message "--- Report end: $(date) ---"
