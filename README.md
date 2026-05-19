# G.A.I.A.

Gateway for Advanced Industrial Analytics.

## Table of contents

- [General info](#general-info)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Architecture](#architecture)
- [Resources](#resources)

## General info

G.A.I.A. is a proof-of-concept platform for an industrial IoT gateway and analytics pipeline.

It demonstrates an end-to-end flow where a simulated OPC UA machine server generates industrial signals, a gateway transforms and enriches those signals with MES data, and the resulting telemetry is published to MQTT and stored for analytics.

This repository supports both a university IoT exam paper and a bachelor's thesis project.


## Project structure

```text
.
├── fill-db/              # Database seeding tool for populating synthetic manufacturing data
│   └── src/              
├── gateway/              # OPC UA-to-MQTT Gateway service
│   ├── deploy/           # Deployment configurations specific to the gateway
│   │   ├── envs/         # Environment variables and configuration files (.env) for gateway containers
│   │   ├── logs/         # Local scripts log storage
│   │   └── scripts/      # Shell scripts for managing (start/stop) gateway containers
│   └── src/              
├── mesapi-server/        # Manufacturing Execution System (MES) REST API
│   └── src/              
├── opcua-server/         # Industrial machine simulator
│   ├── deploy/           # Deployment configurations specific to the simulation server
│   │   ├── envs/         # Environment variables and configuration files (.env) for OPC UA server containers
│   │   ├── logs/         # Local scripts log storage
│   │   └── scripts/      # Shell scripts for managing (start/stop) OPC UA server containers
│   └── src/              
├── resources/            # Academic and other documentation assets
│   └── report/           
│       └── img/          
└── signoz/               # Observability stack configuration
    ├── common/
    └── docker/               
```

## Architecture

### Core components

- `opcua-server`
  - Simulates an OPC UA server exposing machine state tags such as `InCycle`, `InBypass`, `InWarning`, and `InAlarm`.
  - Periodically updates those boolean tags to represent changing production conditions.

- `gateway`
  - Acts as an OPC UA client and subscribes to variable changes.
  - Enriches telemetry with the current MES work order ID by calling the MES API.
  - Publishes JSON telemetry messages to EMQX via MQTT.
  - Uses OpenTelemetry log export for observability.

- `mesapi-server`
  - Implements a FastAPI REST API for MES operations.
  - Connects to TimescaleDB using SQLAlchemy.
  - Serves active order information for a requested machine ID.

- `fill-db`
  - Seeds TimescaleDB with synthetic manufacturing data.
  - Creates `articles`, `orders`, and `order_progress_statements`.
  - Calculates valid order start/end dates from progress records.

### Supporting infrastructure

- `timescaledb`
  - Time-series database for MES and production data.

- `emqx`
  - MQTT broker for edge telemetry ingestion.

- `grafana`
  - Visualization service for dashboards and metrics.

### Observability

- `signoz`
  - Optional observability stack present in the `signoz/` folder.
  - Provides OTLP-compatible log collection and dashboarding for the gateway and OPC UA server.

### Networking

- `gaia-infra-network`
  - Internal bridge network used by core infrastructure services.

- `gaia-global-network`
  - External Docker network required for service communication across container boundaries.


## Getting started

### Prerequisites

Ensure the following commands run correctly: `git`, `docker`, `docker compose`, `python`/`python3`, `pip`

### First-time setup

1. Clone the repositoty:
```bash
  git clone https://github.com/lastxxix/social-computing.git
  cd social-computing
```

2. Create the external Docker network required by the gateway and OPC UA services:
```bash
  docker network create gaia-global-network
```

3. Start the SigNoz stack for observability (optional but reccomended)
```bash
  docker compose -f signoz/docker/docker-compose.yaml up -d
```

4. Configure environment variables for `fill-db` and `mesapi-server`
```bash
  cp fill-db/.env.example fill-db/.env
  # Now edit the .env file with the required variables
```
```bash
  cp mesapi-server/.env.example mesapi-server/.env
  # Now edit the .env file with the required variables
```

5. Start the core infrastructure services:
```bash
  docker compose up -d
```

6. Populate the MES/TimescaleDB database:
```bash
  docker compose --profile init up --build
```

7. Configure environment variables for OPC UA servers and gateways:
    - each `.env` file in the `opcua-server/deploy/envs/` folder will represent a single machine exposing an OPC UA server
    - each `.env` file in the `gateway/deploy/envs/` folder will represent a single gateway interfacing with a specific server

```bash
  cp opcua-server/deploy/envs/srv-XYZ.env.example opcua-server/deploy/envs/srv-XYZ.env
  # Now edit the .env file with the required variables
  # Add as many .env files (with different names) as the machines you want to expose statuses
```
```bash
  cp gateway/deploy/envs/gw-XYZ.env.example gateway/deploy/envs/gw-XYZ.env
  # Now edit the .env file with the required variables
  # Add as many .env files (with different names) as the machines you want to monitor
```

8. Start the OPC UA server instances for configured machines:
```bash
  ./opcua-server/deploy/scripts/start_containers.sh
```

9. Start the gateway instances for configured machines:
```bash
  ./gateway/deploy/scripts/start_containers.sh
```


### Normal startup

When the environment has already been initialized, use the following commands from the repository root:

1. Start the SigNoz stack for observability (optional but reccomended)
```bash
  docker compose -f signoz/docker/docker-compose.yaml up -d
```

2. Start the core infrastructure services:
```bash
  docker compose up -d
```

3. Start the OPC UA server containers:
```bash
  ./opcua-server/deploy/scripts/start_containers.sh
```

4. Start the gateway containers:
```bash
  ./gateway/deploy/scripts/start_containers.sh
```


### Partial shutdown

To stop and remove all field-node and edge containers:

1. Stop all gateway containers:
```bash
  ./gateway/deploy/scripts/stop_containers.sh
```

2. Stop all OPC UA server containers:
```bash
  ./opcua-server/deploy/scripts/stop_containers.sh
```

### Full shutdown (quick)

```bash
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
```

### Full shutdown (controlled)

1. Stop all field-node and edge containers:
```bash
  ./gateway/deploy/scripts/stop_containers.sh
  ./opcua-server/deploy/scripts/stop_containers.sh
```

2. Stop the core infrastructure stack:

```bash
docker compose down
```

3. If you also started the optional SigNoz stack, stop it with:
```bash
docker compose -f signoz/docker/docker-compose.yaml down
```

### Service endpoints

| Service | Endpoint | Default Credentials |
| :--- | :--- | :--- |
| **MES API Health** | `http://localhost:8000/health` | _None_ |
| **MES API Order Lookup** | `http://localhost:8000/active-order-id?machine=<machine_id>` | _None_ |
| **EMQX Dashboard** | `http://localhost:18083` | `admin` / `public` *(or your env config)* |
| **Grafana Dashboard** | `http://localhost:3000` | `admin` / `admin` |


## Resources

See `resources/` for academic documentation and other useful material.