import os
import sys
import random
import logging
import asyncio
from opcua_server_telemetry import OPCServerTelemetry
from opcua_server import OPCServer

# Required for compatibility between aiomqtt and Python's default event loop for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize the logger for the module
logger = logging.getLogger("opcua-server-logger")


async def simulate_tag_changes(server: OPCServer, interval: int = 3):
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            
            # Simulazione con probabilità: cambiamento di stato casuale
            # Probabilità che la macchina sia in ciclo (60%)
            if random.random() < 0.6:
                await server.set_tag_value("InCycle", True)
                await server.set_tag_value("InBypass", False)
            else:
                await server.set_tag_value("InCycle", False)
                await server.set_tag_value("InBypass", True)
            
            # Probabilità di warning (20%)
            if random.random() < 0.2:
                await server.set_tag_value("InWarning", True)
            else:
                await server.set_tag_value("InWarning", False)
            
            # Probabilità di allarme (20%)
            if random.random() < 0.2:
                await server.set_tag_value("InAlarm", True)
            else:
                await server.set_tag_value("InAlarm", False)
            
            await server.print_tag_status()
            
            await asyncio.sleep(interval)  # Wait for the next cycle
    
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error during simulation: {e}")


async def main():
    # Setup telemetry
    server_telemetry = OPCServerTelemetry(
        endpoint_host = os.getenv("OTEL_HOST"),
        endpoint_port = int(os.getenv("OTEL_PORT")),
        service_name = os.getenv("OTEL_SERVICE_NAME"),
        deployment_environment = os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT"),
        hostname = os.getenv("MACHINE_ID"),
    )

    server_telemetry.setup()

    # Crea l'istanza del server
    opc_server = OPCServer(endpoint=os.getenv("OPCUA_ENDPOINT"))
    logger.info(f"OPC UA server initialized with endpoint: {opc_server.endpoint}.")

    await opc_server.setup()
    logger.info(f"OPC UA server configured and ready to start.")
    
    server_task = asyncio.create_task(opc_server.start())  # Start the server in background
    logger.info("OPC UA server started and awaiting client connections.")

    try:
        # Avvia la simulazione dei tag
        interval_seconds = 3
        simulation_task = asyncio.create_task(
            simulate_tag_changes(opc_server, interval=interval_seconds)
        )
        logger.info(f"Started tag simulation with {interval_seconds}-second intervals.")
        
        await simulation_task  # Wait for the simulation to complete (runs indefinitely until cancelled)
    except KeyboardInterrupt:
        logger.info("Simulation cancelled.")
    finally:
        server_task.cancel()
        await opc_server.stop()
        logger.info("OPC UA server stopped.")
        server_telemetry.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
