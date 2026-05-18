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

## Tech stack

- Python 3.11
- FastAPI + Uvicorn
- PostgreSQL + TimescaleDB
- EMQX MQTT broker
- asyncua, aiomqtt, aiohttp
- OpenTelemetry / SigNoz for observability
- Docker Compose for local deployment

## Getting started

### Prerequisites

- Docker and Docker Compose
- External Docker network: `gaia-global-network`
- Optional: SigNoz observability stack for OTLP logging

### Setup

1. Create the external Docker network:
   ```bash
   docker network create gaia-global-network
   ```

2. Start the infrastructure stack from the repository root:
   ```bash
   docker compose up -d
   ```

3. Populate the MES database on first setup:
   ```bash
   docker compose --profile init up --build
   ```

4. Start the gateway and OPC UA containers using the deployment scripts if available:
   - `gateway/deploy/scripts/start_containers.sh`
   - `opcua-server/deploy/scripts/start_containers.sh`

### Service endpoints

- MES API health: `http://localhost:8000/health`
- MES API active order lookup: `http://localhost:8000/active-order-id?machine=<machine_id>`
- EMQX dashboard: `http://localhost:18083`
- Grafana dashboard: `http://localhost:3000`

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

## Resources

- Code folders:
  - `opcua-server/src` — OPC UA simulation service
  - `gateway/src` — OPC UA-to-MQTT gateway and MES integration
  - `mesapi-server/src` — MES API and database access
  - `fill-db/src` — database seeding and synthetic data generation

- Deployment assets:
  - `docker-compose.yaml` — main infrastructure stack
  - `signoz/docker/docker-compose.yaml` — optional SigNoz observability stack

- Helper scripts:
  - `gateway/deploy/scripts` — gateway container management scripts
  - `opcua-server/deploy/scripts` — OPC UA server container scripts
