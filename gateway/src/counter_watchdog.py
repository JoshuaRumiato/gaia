import time
from typing import Any

class CounterWatchdog:
    """Detect machine-counter stalls while the line counter advances.

    Attributes:
        machine_id: Machine identifier included in derived events.
        timeout_seconds: Minimum machine-counter stall duration.
        min_pieces: Minimum line-counter increase required to report an anomaly.
        line_counter_name: OPC UA variable used as the line counter.
        machine_counter_name: OPC UA variable used as the machine counter.
    """

    def __init__(
            self,
            machine_id: int,
            timeout_seconds: float,
            min_pieces: int,
            line_counter_name: str,
            machine_counter_name: str
    ):
        self.machine_id = machine_id
        self.timeout_seconds = timeout_seconds
        self.min_pieces = min_pieces
        self.line_counter_name = line_counter_name
        self.machine_counter_name = machine_counter_name

        # Internal watchdog state
        self.last_machine_time = time.time()
        self.current_line_count = 0
        self.pieces_since_last_machine = 0
        self.anomaly = False

    def process_event(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Process a counter sample and return an event when anomaly state changes.

        A machine-counter update clears an active anomaly. A line-counter
        update can raise one after the timeout and piece threshold are exceeded.

        Args:
            data: Raw OPC UA sample containing a variable name and value.

        Returns:
            A derived MachineAnomaly event when the state changes; otherwise None.
        """
        if data["variable"] == self.machine_counter_name:
            self.last_machine_time = time.time()
            self.pieces_since_last_machine = 0

            if self.anomaly:
                self.anomaly = False
                return {
                    "timestamp": time.time(),
                    "machine_id": self.machine_id,
                    "variable": "MachineAnomaly",
                    "type": "Boolean",
                    "value": int(self.anomaly),
                    "event_type": "D"  # Derived
                }

        elif data["variable"] == self.line_counter_name:
            new_count = data["value"]
            delta_pieces = 0

            if new_count >= self.current_line_count:
                delta_pieces = new_count - self.current_line_count
            else:
                delta_pieces = new_count

            self.current_line_count = new_count
            self.pieces_since_last_machine += delta_pieces

            # Check for anomaly
            if not self.anomaly:
                time_since_last_machine = time.time() - self.last_machine_time
                if time_since_last_machine > self.timeout_seconds:
                    if self.pieces_since_last_machine >= self.min_pieces:
                        self.anomaly = True
                        return {
                            "timestamp": time.time(),
                            "machine_id": self.machine_id,
                            "variable": "MachineAnomaly",
                            "type": "Boolean",
                            "value": int(self.anomaly),
                            "event_type": "D"  # Derived
                        }

        return None
