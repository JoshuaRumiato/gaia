# G.A.I.A.

Gateway for Advanced Industrial Analytics.

## Table of contents

- [General info](#general-info)
- [Project structure](#project-structure)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Resources](#resources)

## General info

G.A.I.A. is a proof-of-concept platform for an industrial IoT gateway and analytics pipeline.

It demonstrates an end-to-end flow where a simulated OPC UA machine server generates machine states and production counters. A gateway publishes raw samples over MQTT and derives anomaly events from counter activity.

This repository supports both a university IoT exam paper and a bachelor's thesis project.


## Project structure

```text
.
├── gateway/              # OPC UA-to-MQTT Gateway service
│   ├── deploy/           # Deployment configurations specific to the gateway
│   │   ├── envs/         # Environment variables and configuration files (.env) for gateway containers
│   │   ├── logs/         # Local scripts log storage
│   │   └── scripts/      # Shell scripts for managing (start/stop) gateway containers
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
  - Simulates machine-state tags and integer production counters over OPC UA.
  - Models line activity, machine stoppages, counter resets, and rejected pieces.

- `gateway`
  - Subscribes to OPC UA counters and publishes raw samples to EMQX via MQTT.
  - Uses a counter watchdog to derive machine-anomaly events.
  - Uses OpenTelemetry log export for observability.

### Supporting infrastructure

- `timescaledb`
  - Time-series database for machine events and production data.

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

Ensure the following commands run correctly: `git`, `docker`, and `docker compose`.

### First-time setup

1. Clone the repository at the v2.0 release:
```bash
  git clone --branch v2.0 https://github.com/JoshuaRumiato/gaia.git
  cd gaia
```

2. Create the external Docker network required by the gateway and OPC UA services:
```bash
  docker network create gaia-global-network
```

3. Start the SigNoz stack for observability (optional but recommended)
```bash
  docker compose -f signoz/docker/docker-compose.yaml up -d
```

4. Start the core infrastructure services:
```bash
  docker compose up -d
```

5. Configure TimescaleDB and EMQX using `resources/timescale.sql` and `resources/emqx.sql`. Replace the password placeholders before applying the SQL. Configure the Grafana `machine_id` variable as a single-value text variable and use the panel queries in `resources/grafana.sql`.

6. Configure environment variables for OPC UA servers and gateways:
    - each `.env` file in `opcua-server/deploy/envs/` represents one simulated machine;
    - each `.env` file in `gateway/deploy/envs/` represents one gateway connected to a server;
    - set matching machine IDs and OPC UA endpoints, and use an MQTT topic under `prod/gaia/` if the events should be persisted by the configured EMQX rule.

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

7. Start the OPC UA server instances for configured machines:
```bash
  cd ./opcua-server/deploy/scripts/
  ./start_containers.sh
```

8. Start the gateway instances for configured machines:
```bash
  cd ../../../gateway/deploy/scripts/
  ./start_containers.sh
```


### Normal startup

When the environment has already been initialized, use the following commands from the repository root:

1. Start the SigNoz stack for observability (optional but recommended)
```bash
  docker compose -f signoz/docker/docker-compose.yaml up -d
```

2. Start the core infrastructure services:
```bash
  docker compose up -d
```

3. Start the OPC UA server containers:
```bash
  cd ./opcua-server/deploy/scripts/
  ./start_containers.sh
```

4. Start the gateway containers:
```bash
  cd ../../../gateway/deploy/scripts/
  ./start_containers.sh
```


### Partial shutdown

To stop and remove all field-node and edge containers:

1. Stop all gateway containers (from the root folder of the repository):
```bash
  cd ./gateway/deploy/scripts/
  ./stop_containers.sh
```

2. Stop all OPC UA server containers:
```bash
  cd ../../../opcua-server/deploy/scripts/
  ./stop_containers.sh
```

### Full shutdown (quick)

Attention: this will stop and remove all containers in the current Docker environment, including containers unrelated to this project.

```bash
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
```

### Full shutdown (controlled)

1. Stop all field-node and edge containers (from the root node of the repository):
```bash
  cd ./gateway/deploy/scripts/
  ./stop_containers.sh
```
```bash
  cd ../../../opcua-server/deploy/scripts/
  ./stop_containers.sh
```

2. Stop the core infrastructure stack:

```bash
docker compose down
```

3. If you also started the optional SigNoz stack, stop it with:
```bash
docker compose -f ../../../signoz/docker/docker-compose.yaml down
```

### Service endpoints

| Service | Endpoint | Default Credentials |
| :--- | :--- | :--- |
| **EMQX Dashboard** | `http://localhost:18083` | `admin` / `public` *(or your env config)* |
| **Grafana Dashboard** | `http://localhost:3000` | `admin` / `admin` |


## Resources

The `resources/` directory contains setup SQL, event persistence and dashboard resources, and academic documentation:

- `report/main.tex`
  - Comprehensive Italian-language report on the v1.0 architecture, design decisions, implementation, and deployment strategy.
- `timescale.sql`
  - Defines the hypertable used for storage, retention policy, and database roles/users.
- `emqx.sql`
  - EMQX configuration queries for data bridge rules and authentication setup.
- `grafana.sql`
  - Grafana panel queries for production counters and derived machine anomalies.

## Other information

A v1.0 version of the project exists, which was used as the basis for the IoT exam. This version differs in some components and in the way the gateways and OPC UA servers operate.

To view and use this specific version, run the following commands in the terminal:

```bash
  git clone --branch v1.0 https://github.com/JoshuaRumiato/gaia.git
  cd gaia
```

Then follow the instruction in that version of the `README.md`.