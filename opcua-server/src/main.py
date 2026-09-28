"""OPC UA server simulation entry point.

Initializes and runs an OPC UA server that simulates industrial equipment
with tag state changes. Handles system signals for graceful shutdown and
integrates with OpenTelemetry for observability.
"""

import os
import sys
import signal
import random
import logging
import asyncio
from opcua_server_telemetry import OPCServerTelemetry
from opcua_server import OPCServer

# Required for compatibility between aiomqtt and Python's default event loop for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger("opcua-server-logger")


async def simulate_tag_changes(server: OPCServer, interval: int = 3) -> None:
    """
    Simulate random tag state changes for the OPC UA server.
    
    Periodically update boolean tag states with probabilities:
    - InCycle: 60% true, 40% false
    - InBypass: complementary to InCycle
    - InWarning: 20% true, 80% false
    - InAlarm: 20% true, 80% false

    The task stops when cancelled or when a tag update fails. Cancellation is
    suppressed, while update failures are logged.

    Args:
        server (OPCServer): OPC UA server instance.
        interval (int): Time in seconds between state changes. Defaults to 3.

    Returns:
        None

    """

    try:
        while True:
            
            # InCycle with 60% probability
            if random.random() < 0.6:
                await server.set_tag_value("InCycle", True)
                await server.set_tag_value("InBypass", False)
            else:
                await server.set_tag_value("InCycle", False)
                await server.set_tag_value("InBypass", True)
            
            # InWarning with 20% probability
            if random.random() < 0.2:
                await server.set_tag_value("InWarning", True)
            else:
                await server.set_tag_value("InWarning", False)
            
            # InAlarm with 20% probability
            if random.random() < 0.2:
                await server.set_tag_value("InAlarm", True)
            else:
                await server.set_tag_value("InAlarm", False)
            
            await asyncio.sleep(interval)
    
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error during simulation: {e}")

async def simulate_counters(server: OPCServer) -> None:
    """
    Simulate line and machine counters with resets, stoppages, and rejected pieces.

    The machine counter can stop while the line counter continues advancing,
    allowing the gateway watchdog to detect production anomalies.

    Args:
        server: OPC UA server whose counter tags are updated.

    Returns:
        None
    """

    line_stopped = False
    machine_stop_cycles = 0

    try:
        while True:

            # Update line counter
            current_line_counter = await server.get_tag_value("LinePieceCounter")
            line_random = random.random()

            if line_random < 0.02:  # 2% chance to reset the line counter
                await server.set_tag_value("LinePieceCounter", 0)
                line_stopped = False
            elif line_random < 0.82:  # 80% chance to increment the line counter
                await server.set_tag_value("LinePieceCounter", current_line_counter + 30)
                line_stopped = False
            else: # 18% chance to do nothing (line is stopped)
                line_stopped = True

            await asyncio.sleep(random.uniform(0.2, 1.2)) # Random interval between increments

            # Update machine counter
            current_machine_counter = await server.get_tag_value("MachinePieceCounter")
            current_rejected_counter = await server.get_tag_value("MachineRejectedPieces")

            if machine_stop_cycles > 0:  # Machine is currently stopped
                machine_stop_cycles -= 1
            else:
                if not line_stopped:
                    machine_random = random.random()

                    if machine_random < 0.02:  # 2% chance to reset the machine counter
                        await server.set_tag_value("MachinePieceCounter", 0)
                    elif machine_random < 0.62:  # 60% chance to increment the machine counter
                        await server.set_tag_value("MachinePieceCounter", current_machine_counter + 30)
                        reject_random = random.random()
                        if reject_random < 0.05:  # 5% chance to increment the rejected pieces counter
                            await server.set_tag_value("MachineRejectedPieces", current_rejected_counter + 5)
                    else:  # 38% chance to do nothing (machine is stopped)
                        machine_stop_cycles = random.randint(20, 30) 

            await asyncio.sleep(random.uniform(0.2, 1.2))  # Random interval between increments
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error during counters simulation: {e}")



async def main() -> None:
    """
    Execute the OPC UA server application.
    
    Initialize telemetry, set up the OPC UA server, start the server and
    tag simulation, and handle system signals for graceful shutdown.

    Returns:
        None

    Raises:
        Exception: Errors are caught and logged during shutdown.
    """

    machine_id = int(os.getenv("MACHINE_ID"))
    server_id = f"SRV-{machine_id}"

    # Setup telemetry
    server_telemetry = OPCServerTelemetry(
        endpoint_host = os.getenv("OTEL_HOST"),
        endpoint_port = int(os.getenv("OTEL_PORT")),
        service_name = os.getenv("OTEL_SERVICE_NAME"),
        deployment_environment = os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT"),
        hostname = server_id,
    )

    server_telemetry.setup()

    # Initialize OPC UA server
    opc_server = OPCServer(endpoint=os.getenv("OPCUA_ENDPOINT"))
    logger.info(f"OPC UA server initialized with endpoint: {opc_server.endpoint}.")

    await opc_server.setup()
    logger.info(f"OPC UA server configured and ready to start.")
    
    # Start server in background
    server_task = asyncio.create_task(opc_server.start())
    logger.info("OPC UA server started and awaiting client connections.")
    simulation_task: asyncio.Task[None] | None = None

    def handle_shutdown_signal() -> None:
        """
        Cancel the counter simulation when a shutdown signal is received.
        
        The simulation handles cancellation, allowing main() to reach its
        cleanup block and stop the OPC UA server.
        
        Returns:
            None
        """
        logger.info("Shutdown signal received.")
        if simulation_task is not None:
            simulation_task.cancel()

    try:
        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        if sys.platform == "win32":
            signal.signal(signal.SIGINT, lambda s,f: loop.call_soon_threadsafe(handle_shutdown_signal))
            signal.signal(signal.SIGTERM, lambda s,f: loop.call_soon_threadsafe(handle_shutdown_signal))
        else:
            loop.add_signal_handler(signal.SIGINT, handle_shutdown_signal)
            loop.add_signal_handler(signal.SIGTERM, handle_shutdown_signal)
        
        # Start tag simulation
        interval_seconds = 3
        simulation_task = asyncio.create_task(
            simulate_counters(opc_server)
        )
        logger.info(f"Started counters simulation.")
        
        # Wait for simulation to complete (runs until cancelled)
        await simulation_task
    except KeyboardInterrupt:
        logger.info("Simulation cancelled.")
    except asyncio.CancelledError:
        pass
    finally:
        if simulation_task is not None:
            simulation_task.cancel()
            try:
                await simulation_task
            except asyncio.CancelledError:
                pass
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        await opc_server.stop()
        logger.info("OPC UA server stopped.")
        server_telemetry.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
