-- EMQX rule
SELECT 
  payload.timestamp as timestamp,
  payload.machine_id as machine_id,
  payload.variable as variable, 
  payload.type as type,
  payload.value as value, 
  payload.event_type as event_type
FROM "prod/gaia/#"

-- EMQX sink
INSERT INTO machine_events (
  timestamp, 
  machine_id, 
  variable, 
  type, 
  value, 
  event_type
) 
VALUES (
  (CASE 
    WHEN ${variable} = 'DataValid' THEN clock_timestamp()
    ELSE to_timestamp(${timestamp})
  END),
  ${machine_id},
  ${variable},
  ${type},
  ${value},
  ${event_type}
)