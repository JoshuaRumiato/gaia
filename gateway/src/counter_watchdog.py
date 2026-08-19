import time
from typing import Any

class CounterWatchdog:
    def __init__(
            self,
            client_id: str,
            timeout_seconds: float,
            min_pieces: int,
            line_counter_name: str,
            machine_counter_name: str
    ):
        self.client_id = client_id
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
        if data["variable"] == self.machine_counter_name:
            self.last_machine_time = time.time()
            self.pieces_since_last_machine = 0

            if self.anomaly:
                self.anomaly = False
                return {
                    "timestamp": time.time(),
                    "client_id": self.client_id,
                    "variable": "VisionAnomaly",
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
                            "client_id": self.client_id,
                            "variable": "VisionAnomaly",
                            "type": "Boolean",
                            "value": int(self.anomaly),
                            "event_type": "D"  # Derived
                        }

        return None
