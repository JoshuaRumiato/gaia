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

CREATE TABLE IF NOT EXISTS machine_status_changes (
    timestamp TIMESTAMPTZ NOT NULL,
    machine_id VARCHAR(40) NOT NULL,
    variable VARCHAR(20) NOT NULL,
    type VARCHAR(20) NOT NULL,
    value INTEGER NOT NULL,
	order_id INTEGER
);



-- create the hypertable
SELECT create_hypertable('machine_status_changes', 'timestamp');

-- check if the hypertable is created
SELECT * FROM timescaledb_information.hypertables
WHERE hypertable_name = 'machine_status_changes';

-- set retention policy
SELECT set_retention_policy(INTERVAL '13 month')


-- other intresting queries
SELECT * FROM timescaledb_information.dimensions
WHERE hypertable_name = 'machine_status_changes';

SELECT * FROM timescaledb_information.chunks
WHERE hypertable_name = 'machine_status_changes';

select hypertable_size('machine_status_changes');

SELECT * from hypertable_detailed_size('machine_status_changes');


-- create user and grant permissions for EMQX
CREATE USER emqx_user WITH ENCRYPTED PASSWORD '[enter_password]';
GRANT CONNECT ON DATABASE gaia_db TO emqx_user;
GRANT USAGE ON SCHEMA public TO emqx_user;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public to emqx_user;

-- (optional) automatically grant select permissions to the user for any new tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO emqx_user;


-- create user and grant permissions for Grafana
CREATE USER grafana_user WITH ENCRYPTED PASSWORD '[enter_password]';
GRANT CONNECT ON DATABASE gaia_db TO grafana_user;
GRANT USAGE ON SCHEMA public TO grafana_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public to grafana_user;

-- (optional) automatically grant select permissions to the user for any new tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_user;