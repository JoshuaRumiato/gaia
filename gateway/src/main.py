"""IoT Bridge for OPC UA to MQTT data ingestion.

This module acts as the entry point for the application. It orchestrates 
the connection to an OPC UA server, monitors specific variables, and 
publishes the gathered data to an MQTT broker. It also handles system 
signals for a graceful shutdown and manages telemetry and MES API integration.

Example:
    To run the application, ensure environment variables are set and execute:
        $ python main.py

Attributes:
    logger (logging.Logger): Logger instance for the module.
"""

import os
import sys
import signal
import asyncio
import logging

from gateway_telemetry import GatewayTelemetry
from async_opc_client import AsyncOPCClient
from async_mqtt_publisher import AsyncMQTTPublisher
from async_mesapi_client import AsyncMesAPIClient


# Required for compatibility between aiomqtt and Python's default event loop for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize the logger for the module
logger = logging.getLogger("gateway-logger")


async def publisher_worker(
        mqtt_publisher: AsyncMQTTPublisher,
        mesapi_client: AsyncMesAPIClient, 
        machine_id: str,
        queue: asyncio.Queue,
        extra_data: dict[str, str] | None = None,
        max_concurrent: int = 50
) -> None:
    """Consume messages from a queue, add extra information and publish them via MQTT.

    Maintain an active connection to the MQTT broker, handle automatic 
    retries on connection failure, and process messages asynchronously 
    from the provided queue.

    Args:
        mqtt_publisher (AsyncMQTTPublisher): Client used to publish messages.
        mesapi_client (AsyncMesAPIClient): Client used to fetch production 
            order information from the MES API.
        prod_line (str): Identifier of the production line, used to query 
            work order data.
        queue (asyncio.Queue): Asynchronous queue containing messages to 
            be processed and sent.
        extra_data (dict[str, str] | None): Data to be merged into every 
            outgoing message payload. Defaults to None.
        max_concurrent (int): Maximum number of concurrent publishing tasks 
            allowed. Defaults to 50.

    Returns:
        None

    Raises:
        asyncio.CancelledError: If the worker task is cancelled by the 
            event loop.
    """
    extra_data = extra_data or {}  # If extra data is None, 
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_message(data: dict[str, str | int]) -> None:
        """Merge extra information to a message and publish it via MQTT.

        Handle connection resets on failure. 

        Args:
            data (dict[str, Any]): Raw message payload retrieved from the queue.

        Returns:
            None
        """
        async with semaphore:
            try:
                for key in extra_data:
                    data[key] = extra_data[key]
                
                try:
                    # Add order id to get production order info when visualizing data
                    data["order_id"] = await mesapi_client.get_current_order_id(machine_id)
                except Exception as e:
                    logger.warning(f"MESAPI | {e}")
                    data["order_id"] = None

                await mqtt_publisher.publish(data)
            except Exception as e:
                logger.error(f'MQTT | {e}')
                try:
                    await mqtt_publisher.disconnect()  # Force the client to disconnect
                except:
                    pass

    while True:  # External loop: manage the connection attempts
        try:
            await mqtt_publisher.connect()

            logger.info(f"MQTT | Client connected to {mqtt_publisher.broker}.")

            while True:  # Internal loop: manage message publishing
                data = await queue.get()  # Retrieve an item from the queue
                asyncio.create_task(process_message(data))
                queue.task_done()

        except Exception as e:  # Handle the reconnection process
            logger.error(f'MQTT | {e}. New connection attempt in 3s...')
            try:
                await mqtt_publisher.disconnect()
            except:
                pass
            await asyncio.sleep(3)
            

async def main() -> None:
    """Entry point of the script.

    Subscribe for data changes to an OPC UA server, store them in an
    asynchronous queue, and publish them via MQTT.

    If connection with the OPC UA server or with the MQTT broker fails, the 
    function will continuously attempt to reconnect until the application 
    is manually stopped by the user via system signals (SIGINT, SIGTERM).

    Returns:
        None

    Raises:
        asyncio.CancelledError: If a stop signal is received and the main 
            task is cancelled for a clean shutdown.
    """
    
    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task(loop)
    
    def handle_stop_signal():
        main_task.cancel()
    
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, lambda s,f: loop.call_soon_threadsafe(handle_stop_signal))
        signal.signal(signal.SIGTERM, lambda s,f: loop.call_soon_threadsafe(handle_stop_signal))
    else:
        loop.add_signal_handler(signal.SIGINT, handle_stop_signal)
        loop.add_signal_handler(signal.SIGTERM, handle_stop_signal)
    
    machine_id = int(os.getenv("MACHINE_ID"))
    client_id = f"GW-{machine_id}"
    data_queue = asyncio.Queue(maxsize = 1000)

    device_telemetry = GatewayTelemetry(
        endpoint_host = os.getenv("OTEL_HOST"),
        endpoint_port = int(os.getenv("OTEL_PORT")),
        service_name = os.getenv("OTEL_SERVICE_NAME"),
        deployment_environment = os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT"),
        hostname = client_id
    )

    device_telemetry.setup()

    opc_client = AsyncOPCClient(
        host = os.getenv("OPCUA_HOST"),
        port = int(os.getenv("OPCUA_PORT")),
        username = os.getenv("OPCUA_USERNAME"),
        password = os.getenv("OPCUA_PASSWORD")
    )
    
    logger.info("OPC UA | Client started.")

    mqtt_publisher = AsyncMQTTPublisher(
        broker = os.getenv("MQTT_HOST"),
        port = int(os.getenv("MQTT_PORT")),
        topic = os.getenv("MQTT_TOPIC"),
        client_id = client_id,
        username = os.getenv("MQTT_USERNAME"),
        password = os.getenv("MQTT_PASSWORD"),
        use_tls = os.getenv("MQTT_USE_TLS") == "true",
        transport = os.getenv("MQTT_TRANSPORT")
    )

    logger.info("MQTT | Client started.")

    async with AsyncMesAPIClient(os.getenv("MESAPI_BASE_URL")) as mesapi_client:

        logger.info("MESAPI | Client started.")

        # Create a background task for the publishing process
        publisher_task = asyncio.create_task(publisher_worker(mqtt_publisher,
                                                              mesapi_client, 
                                                              machine_id,
                                                              data_queue,
                                                              {"machine_id" : machine_id}))

        while True:
            try:
                await opc_client.connect()
                logger.info(f"OPC UA | Client connected to {opc_client.host}.")

                # Get the nodes to monitor
                monitored_items = [ s for s in os.getenv("OPCUA_MONITORED_ITEMS").split("|") if s.strip() ]
                subscription = await opc_client.subscribe_to_variables(monitored_items, data_queue, period=500)
                if subscription:
                    logger.info(f"OPC UA | Subscriptions activated for: {monitored_items}.")
                    
                    while True:
                        await opc_client.client.check_connection()
                        await asyncio.sleep(30)
                else:    
                    logger.warning(f'OPC UA | Unable to subscribe to data changes for {monitored_items}. New connection attempt in 3s...')

                try:
                    await opc_client.disconnect()
                except:
                    pass  # Ignore errors during disconnection of client is already offline
                await asyncio.sleep(3)

            except (asyncio.CancelledError, KeyboardInterrupt) as e:
                logger.info("Shutdown invoked.")
                await opc_client.disconnect()
                break
            except Exception as e:
                logger.error(f'OPC UA | {e}. New connection attempt in 3s...')
                
                try:
                    await opc_client.disconnect()
                except:
                    pass  # Ignore errors during disconnection of client is already offline
                await asyncio.sleep(3)

        # It is possible to handle clearing the queue, but it doesn't make sense given that this script
        # is simply a software bridge between two IoT protocols taht will be installed on edge devices. 
        # It is not required to ensure reliability or caching of the information

        device_telemetry.shutdown()
        publisher_task.cancel()
        await mqtt_publisher.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(e)
