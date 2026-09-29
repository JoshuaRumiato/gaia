-- Grafana panel query: total machine pieces produced while DataValid is true.
WITH valid_intervals AS (
    SELECT
        "timestamp" AS interval_start,
        LEAD("timestamp") OVER (ORDER BY "timestamp") AS next_event,
        value AS is_valid
    FROM machine_events
    WHERE variable = 'DataValid'
      AND machine_id = '${machine_id}'
      AND "timestamp" <= $__timeTo()::timestamptz
),
overlapping_intervals AS (
    SELECT
        GREATEST(interval_start, $__timeFrom()::timestamptz) AS interval_start,
        LEAST(COALESCE(next_event, $__timeTo()::timestamptz), $__timeTo()::timestamptz) AS interval_end
    FROM valid_intervals
    WHERE is_valid = 1
      AND (interval_start, COALESCE(next_event, $__timeTo()::timestamptz))
          OVERLAPS ($__timeFrom()::timestamptz, $__timeTo()::timestamptz)
),
counter_readings AS (
    SELECT
        intervals.interval_start,
        events."timestamp",
        events.value,
        LAG(events.value) OVER (
            PARTITION BY intervals.interval_start
            ORDER BY events."timestamp"
        ) AS previous_value
    FROM overlapping_intervals AS intervals
    JOIN machine_events AS events
      ON events."timestamp" >= intervals.interval_start
     AND events."timestamp" < intervals.interval_end
     AND events.machine_id = '${machine_id}'
     AND events.variable = 'MachinePieceCounter'
)
SELECT COALESCE(SUM(
    CASE
        WHEN previous_value IS NULL THEN 0
        WHEN value >= previous_value THEN value - previous_value
        ELSE value
    END
), 0) AS total_pieces_counted
FROM counter_readings;

-- Grafana panel query: total rejected pieces while DataValid is true.
WITH valid_intervals AS (
    SELECT
        "timestamp" AS interval_start,
        LEAD("timestamp") OVER (ORDER BY "timestamp") AS next_event,
        value AS is_valid
    FROM machine_events
    WHERE variable = 'DataValid'
      AND machine_id = '${machine_id}'
      AND "timestamp" <= $__timeTo()::timestamptz
),
overlapping_intervals AS (
    SELECT
        GREATEST(interval_start, $__timeFrom()::timestamptz) AS interval_start,
        LEAST(COALESCE(next_event, $__timeTo()::timestamptz), $__timeTo()::timestamptz) AS interval_end
    FROM valid_intervals
    WHERE is_valid = 1
      AND (interval_start, COALESCE(next_event, $__timeTo()::timestamptz))
          OVERLAPS ($__timeFrom()::timestamptz, $__timeTo()::timestamptz)
),
rejected_readings AS (
    SELECT
        intervals.interval_start,
        events."timestamp",
        events.value,
        LAG(events.value) OVER (
            PARTITION BY intervals.interval_start
            ORDER BY events."timestamp"
        ) AS previous_value
    FROM overlapping_intervals AS intervals
    JOIN machine_events AS events
      ON events."timestamp" >= intervals.interval_start
     AND events."timestamp" < intervals.interval_end
     AND events.machine_id = '${machine_id}'
     AND events.variable = 'MachineRejectedPieces'
)
SELECT COALESCE(SUM(
    CASE
        WHEN previous_value IS NULL THEN 0
        WHEN value >= previous_value THEN value - previous_value
        ELSE value
    END
), 0) AS total_rejected_pieces
FROM rejected_readings;

-- Grafana panel query: rejected-piece percentage while DataValid is true.
WITH valid_intervals AS (
    SELECT
        "timestamp" AS interval_start,
        LEAD("timestamp") OVER (ORDER BY "timestamp") AS next_event,
        value AS is_valid
    FROM machine_events
    WHERE variable = 'DataValid'
      AND machine_id = '${machine_id}'
      AND "timestamp" <= $__timeTo()::timestamptz
),
overlapping_intervals AS (
    SELECT
        GREATEST(interval_start, $__timeFrom()::timestamptz) AS interval_start,
        LEAST(COALESCE(next_event, $__timeTo()::timestamptz), $__timeTo()::timestamptz) AS interval_end
    FROM valid_intervals
    WHERE is_valid = 1
      AND (interval_start, COALESCE(next_event, $__timeTo()::timestamptz))
          OVERLAPS ($__timeFrom()::timestamptz, $__timeTo()::timestamptz)
),
counter_readings AS (
    SELECT
        intervals.interval_start,
        events."timestamp",
        events.value,
        events.variable,
        LAG(events.value) OVER (
            PARTITION BY intervals.interval_start, events.variable
            ORDER BY events."timestamp"
        ) AS previous_value
    FROM overlapping_intervals AS intervals
    JOIN machine_events AS events
      ON events."timestamp" >= intervals.interval_start
     AND events."timestamp" < intervals.interval_end
     AND events.machine_id = '${machine_id}'
     AND events.variable IN ('MachinePieceCounter', 'MachineRejectedPieces')
),
deltas AS (
    SELECT
        variable,
        CASE
            WHEN previous_value IS NULL THEN 0
            WHEN value >= previous_value THEN value - previous_value
            ELSE value
        END AS delta
    FROM counter_readings
),
totals AS (
    SELECT
        COALESCE(SUM(delta) FILTER (WHERE variable = 'MachinePieceCounter'), 0) AS total_pieces,
        COALESCE(SUM(delta) FILTER (WHERE variable = 'MachineRejectedPieces'), 0) AS total_rejected_pieces
    FROM deltas
)
SELECT COALESCE(
    total_rejected_pieces * 100.0 / NULLIF(total_pieces, 0),
    0
) AS rejected_percentage
FROM totals;

-- Grafana panel query: anomaly starts while DataValid is true.
WITH valid_intervals AS (
    SELECT
        "timestamp" AS interval_start,
        LEAD("timestamp") OVER (ORDER BY "timestamp") AS next_event,
        value AS is_valid
    FROM machine_events
    WHERE variable = 'DataValid'
      AND machine_id = '${machine_id}'
      AND "timestamp" <= $__timeTo()::timestamptz
),
overlapping_intervals AS (
    SELECT
        GREATEST(interval_start, $__timeFrom()::timestamptz) AS interval_start,
        LEAST(COALESCE(next_event, $__timeTo()::timestamptz), $__timeTo()::timestamptz) AS interval_end
    FROM valid_intervals
    WHERE is_valid = 1
      AND (interval_start, COALESCE(next_event, $__timeTo()::timestamptz))
          OVERLAPS ($__timeFrom()::timestamptz, $__timeTo()::timestamptz)
)
SELECT COUNT(*) AS total_anomalies
FROM overlapping_intervals AS intervals
JOIN machine_events AS events
  ON events."timestamp" >= intervals.interval_start
 AND events."timestamp" < intervals.interval_end
 AND events.machine_id = '${machine_id}'
 AND events.variable = 'MachineAnomaly'
 AND events.value = 1;

-- Grafana panel query: duration of anomaly intervals while DataValid is true.
WITH valid_intervals AS (
    SELECT
        "timestamp" AS interval_start,
        LEAD("timestamp") OVER (ORDER BY "timestamp") AS next_event,
        value AS is_valid
    FROM machine_events
    WHERE variable = 'DataValid'
      AND machine_id = '${machine_id}'
      AND "timestamp" <= $__timeTo()::timestamptz
),
overlapping_valid_intervals AS (
    SELECT
        GREATEST(interval_start, $__timeFrom()::timestamptz) AS interval_start,
        LEAST(COALESCE(next_event, $__timeTo()::timestamptz), $__timeTo()::timestamptz) AS interval_end
    FROM valid_intervals
    WHERE is_valid = 1
      AND (interval_start, COALESCE(next_event, $__timeTo()::timestamptz))
          OVERLAPS ($__timeFrom()::timestamptz, $__timeTo()::timestamptz)
),
anomaly_events AS (
    SELECT
        "timestamp" AS anomaly_start,
        LEAD("timestamp") OVER (ORDER BY "timestamp") AS next_anomaly_event,
        value AS is_anomaly
    FROM machine_events
    WHERE variable = 'MachineAnomaly'
      AND machine_id = '${machine_id}'
      AND "timestamp" <= $__timeTo()::timestamptz
),
anomaly_intervals AS (
    SELECT
        anomaly_start,
        COALESCE(next_anomaly_event, $__timeTo()::timestamptz) AS anomaly_end
    FROM anomaly_events
    WHERE is_anomaly = 1
),
overlapping_anomalies AS (
    SELECT
        GREATEST(validity.interval_start, anomaly.anomaly_start) AS anomaly_start,
        LEAST(validity.interval_end, anomaly.anomaly_end) AS anomaly_end
    FROM overlapping_valid_intervals AS validity
    JOIN anomaly_intervals AS anomaly
      ON (validity.interval_start, validity.interval_end)
         OVERLAPS (anomaly.anomaly_start, anomaly.anomaly_end)
)
SELECT COALESCE(
    SUM(EXTRACT(EPOCH FROM (anomaly_end - anomaly_start))),
    0
) AS total_anomaly_seconds
FROM overlapping_anomalies
WHERE anomaly_end > anomaly_start;
