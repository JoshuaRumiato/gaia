-- Tab 1: Stat

-- Build validity periods for the DataValid signal
WITH periods AS (
    SELECT 
        "timestamp" as validity_start,
        COALESCE(LEAD("timestamp") OVER (ORDER BY "timestamp"), $__timeTo()::timestamp) as validity_end,
        value as is_valid
    FROM machine_status_changes
    WHERE variable = 'DataValid'
      AND machine_id = ${machine_id}
      AND "timestamp" <= $__timeTo()::timestamp
),
-- Keep only valid time windows overlapping the selected range
valid_windows AS (
    SELECT validity_start, validity_end
    FROM periods
    WHERE is_valid = 1 
      AND (validity_start, validity_end) OVERLAPS ($__timeFrom()::timestamp, $__timeTo()::timestamp)
),
-- Build status intervals for the selected variables
state_intervals AS (
    SELECT 
        variable,
        value,
        "timestamp" as s_start,
        LEAD("timestamp") OVER (PARTITION BY variable ORDER BY "timestamp") as s_next
    FROM machine_status_changes
    WHERE variable IN ('$status')
      AND machine_id = ${machine_id}
),
-- Intersect status intervals with valid data windows
valid_state_intervals AS (
    SELECT 
        s.variable,
        s.value,
        s.s_start,
        COALESCE(s.s_next, $__timeTo()::timestamp) as s_next_clean,
        GREATEST(s.s_start, v.validity_start, $__timeFrom()::timestamp) as i_start,
        LEAST(COALESCE(s.s_next, $__timeTo()::timestamp), v.validity_end, $__timeTo()::timestamp) as i_end
    FROM state_intervals s
    JOIN valid_windows v ON (s.s_start, COALESCE(s.s_next, $__timeTo()::timestamp)) OVERLAPS (v.validity_start, v.validity_end)
),
-- Calculate active time for each variable
calculations AS (
    SELECT 
        variable,
        SUM(
            CASE WHEN i_end > i_start 
            THEN EXTRACT(EPOCH FROM (i_end - i_start)) 
            ELSE 0 END
        ) as active_seconds,
        $__timeFrom()::timestamp as range_start,
        $__timeTo()::timestamp as range_end
    FROM valid_state_intervals
    WHERE value = 1
    GROUP BY variable
)
-- Convert active time into percentage over the selected range
SELECT
    variable as metric,
    (active_seconds / NULLIF(EXTRACT(EPOCH FROM (range_end - range_start)), 0)) * 100 as percentage
FROM calculations;


-- Tab 1: State Timeline

-- Build validity intervals for the DataValid signal
WITH periods AS (
    SELECT 
        "timestamp" as validity_start,
        COALESCE(LEAD("timestamp") OVER (ORDER BY "timestamp"), $__timeTo()::timestamp) as validity_end,
        value as is_valid
    FROM machine_status_changes
    WHERE variable = 'DataValid'
      AND machine_id = ${machine_id}
      AND "timestamp" <= $__timeTo()::timestamp
),
-- Keep only valid time windows overlapping the selected range
valid_windows AS (
    SELECT validity_start, validity_end
    FROM periods
    WHERE is_valid = 1 
      AND (validity_start, validity_end) OVERLAPS ($__timeFrom()::timestamp, $__timeTo()::timestamp)
),
-- Build status intervals for the selected variables
state_intervals AS (
    SELECT 
        variable,
        value,
        "timestamp" as s_start,
        LEAD("timestamp") OVER (PARTITION BY variable ORDER BY "timestamp") as s_next
    FROM machine_status_changes
    WHERE variable IN ('$status')
      AND machine_id = ${machine_id}
),
-- Intersect status intervals with valid data windows
valid_state_intervals AS (
    SELECT 
        s.variable,
        s.value,
        s.s_start,
        COALESCE(s.s_next, $__timeTo()::timestamp) as s_next_clean,
        GREATEST(s.s_start, v.validity_start, $__timeFrom()::timestamp) as i_start,
        LEAST(COALESCE(s.s_next, $__timeTo()::timestamp), v.validity_end, $__timeTo()::timestamp) as i_end
    FROM state_intervals s
    JOIN valid_windows v ON (s.s_start, COALESCE(s.s_next, $__timeTo()::timestamp)) OVERLAPS (v.validity_start, v.validity_end)
),
-- Calculate active time for each variable
calculations AS (
    SELECT 
        variable,
        SUM(
            CASE WHEN i_end > i_start 
            THEN EXTRACT(EPOCH FROM (i_end - i_start)) 
            ELSE 0 END
        ) as active_seconds,
        $__timeFrom()::timestamp as range_start,
        $__timeTo()::timestamp as range_end
    FROM valid_state_intervals
    WHERE value = 1
    GROUP BY variable
)
-- Convert active time into percentage over the selected range
SELECT
    variable as metric,
    (active_seconds / NULLIF(EXTRACT(EPOCH FROM (range_end - range_start)), 0)) * 100 as percentage
FROM calculations;


-- Tab 2: Table

WITH filtered_orders AS (
  -- Select orders with activity inside the selected Grafana time range
  SELECT DISTINCT order_id
  FROM order_progress_statements
  WHERE $__timeFilter("timestamp")
    AND order_id IN ($order_id)
),
base_table AS (
  SELECT
    MAX(ops."timestamp") AS "Last update",
    ops.order_id AS "Order ID",
    CASE
      WHEN NOW()::timestamp < o.END_DATE THEN 'ACTIVE'
      ELSE 'CLOSED'
    END AS "Status",

    a.id AS "Article ID",
    a.description AS "Article description",
    o.target_qty as "Target qty.",
    SUM(ops.produced_qty) AS "Produced qty.",
    SUM(ops.discarded_qty) AS "Discarded qty."
  FROM order_progress_statements ops
    JOIN filtered_orders fo ON ops.order_id = fo.order_id
    JOIN orders o ON ops.order_id = o.id
    JOIN articles a ON o.article_id = a.id
  WHERE
    ops."timestamp" <= $__timeTo()::timestamp
  GROUP BY
    ops.order_id,
    o.end_date,
    a.id,
    a.description,
    o.target_qty
)
-- Return aggregated order overview
SELECT * 
FROM base_table 
ORDER BY "Last update" ASC


-- Tab 2: Time Series

-- Compute cumulative net produced quantity over time
WITH base_table AS ( 
  SELECT
    "timestamp" as "time",
    SUM(produced_qty - discarded_qty) 
      OVER (PARTITION BY order_id ORDER BY "timestamp") as "net produced quantity"
  FROM order_progress_statements
  WHERE order_id IN ($order_id)
)
-- Return time series data
SELECT * 
FROM base_table



