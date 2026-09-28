-- IMPORTANT
-- the following steps need to be performed only if you are
-- running a basic PostgreSQL instance

-- install timescaledb (see https://github.com/timescale/timescaledb)

-- create extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- check if extension has been successfully created
SELECT * FROM pg_extension WHERE extname = 'timescaledb';



-- IMPORTANT
-- the following steps can be performed only if you have successfully
-- created the timescaledb extension and want to configure the database table for
-- storing and querying machine status changes

CREATE TABLE IF NOT EXISTS machine_events (
    timestamp TIMESTAMPTZ NOT NULL,
    machine_id VARCHAR(40) NOT NULL,
    variable VARCHAR(20) NOT NULL,
    type VARCHAR(20) NOT NULL,
    value INTEGER NOT NULL,
	event_type CHAR(1) NOT NULL
);

-- create the hypertable
SELECT create_hypertable('machine_events', 'timestamp');

-- set retention policy
SELECT set_retention_policy('machine_events', INTERVAL '13 month');

-- Other useful queries
-- check if the hypertable is created
SELECT * FROM timescaledb_information.hypertables
WHERE hypertable_name = 'machine_events';

-- other intresting queries
SELECT * FROM timescaledb_information.dimensions
WHERE hypertable_name = 'machine_events';

SELECT * FROM timescaledb_information.chunks
WHERE hypertable_name = 'machine_events';

select hypertable_size('machine_events');

SELECT * from hypertable_detailed_size('machine_events');


-- create user and grant permission for EMQX
CREATE USER emqx_user WITH ENCRYPTED PASSWORD '[enter_password]';
GRANT CONNECT ON DATABASE gaia_db TO emqx_user;
GRANT USAGE ON SCHEMA public TO emqx_user;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO emqx_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO emqx_user;


-- create user and grant permissions for Grafana
CREATE USER grafana_user WITH ENCRYPTED PASSWORD '[enter_password]';
GRANT CONNECT ON DATABASE gaia_db TO grafana_user;
GRANT USAGE ON SCHEMA public TO grafana_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public to grafana_user;

-- (optional) automatically grant select permissions to the user for any new tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_user;
