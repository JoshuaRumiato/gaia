-- EMQX rule
SELECT 
  payload.timestamp as timestamp,
  payload.machine_id as machine_id,
  payload.variable as variable, 
  payload.type as type,
  payload.value as value, 
  payload.order_id as order_id
FROM "prod/gaia/#"

-- EMQX sink
INSERT INTO machine_status_changes (
  timestamp, 
  machine_id, 
  variable, 
  type, 
  value, 
  order_id
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
  ${order_id}
)