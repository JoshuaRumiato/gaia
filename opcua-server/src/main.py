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

    Args:
        server (OPCServer): OPC UA server instance.
        interval (int): Time in seconds between state changes. Defaults to 3.

    Returns:
        None

    Raises:
        asyncio.CancelledError: If the simulation task is cancelled.
        Exception: If tag updates fail.
    """
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            
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

    def handle_shutdown_signal() -> None:
        """
        Cancel the OPC UA server task when a shutdown signal is received.
        
        This handler manages graceful shutdown of the OPC UA server in response
        to system signals (SIGINT, SIGTERM), ensuring proper cleanup of the server
        task and associated resources.
        
        Returns:
            None
        """
        logger.info("OPC UA server stopped.")
        server_task.cancel()

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
            simulate_tag_changes(opc_server, interval=interval_seconds)
        )
        logger.info(f"Started tag simulation with {interval_seconds}-second intervals.")
        
        # Wait for simulation to complete (runs until cancelled)
        await simulation_task
    except KeyboardInterrupt:
        logger.info("Simulation cancelled.")
    except asyncio.CancelledError:
        pass
    finally:
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
