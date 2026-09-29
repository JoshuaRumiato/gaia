#!/bin/bash

# Configure paths
IMAGE_NAME="ghcr.io/joshuarumiato/opcua-server:v2.0"
ENV_DIR="../envs"
LOG_FILE="../logs/report.log"
LOG_DIR=$(dirname $LOG_FILE)

# Ensure the log folder exists
mkdir -p "$LOG_DIR"

# Prints a message and saves it in the log file (with timestamp)
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

# Check if ENV_DIR exists
if [ ! -d "$ENV_DIR" ]; then
    log_message "ERROR: folder $ENV_DIR does not exist."
    exit 1
fi

# Pull the image from the registry
log_message "Pulling image..."
docker pull $IMAGE_NAME >> $LOG_FILE 2>&1

# Start containers
for env_file in "$ENV_DIR"/*.env; do
    # Check if some .env file actually exist 
    [ -f "$env_file" ] || continue
    
    log_message "Processing file: $env_file"
    
    # Get the file name without extension to use it as container name
    file_name=$(basename "$env_file" .env)
    
    if [ "$(docker ps -a --format '{{.Names}}' | grep -w "^$file_name$")" ]; then
        log_message "INFO: Container $file_name already exists. No action performed."
    else
        if docker run -d \
                --name "$file_name" \
                --env-file "$env_file" \
                --network gaia-global-network \
                --restart unless-stopped \
                $IMAGE_NAME >> $LOG_FILE 2>&1; then
            log_message "INFO: Container successfully started for $file_name"
        else
            log_message "ERROR: Failed to start container for $file_name"
        fi
    fi
done

log_message "--- Report end: $(date) ---"
