"""
IoT Bridge for OPC UA to MQTT data ingestion.

This module acts as the entry point for the application. It orchestrates 
the connection to an OPC UA server, monitors specific variables, and 
publishes the gathered data to an MQTT broker. It also handles system 
signals for a graceful shutdown and manages telemetry and MES API integration.
"""

import os
import sys
import time
import signal
import asyncio
import logging
from typing import Any

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
        mqtt_birth_message: dict[str, Any],
        queue: asyncio.Queue,
        mesapi_client: AsyncMesAPIClient, 
        machine_id: int,
        extra_data: dict[str, Any] | None = None,
        max_concurrent: int = 50
) -> None:
    """
    Consume and process messages from a queue, then publish them via MQTT.

    Maintain an active connection to the MQTT broker, handle automatic 
    retries on connection failure, and process messages asynchronously 
    from the provided queue. Each message is enriched with extra data and
    production order information before publishing.

    Args:
        mqtt_publisher: Client used to publish messages.
        mqtt_birth_message: Message to publish upon successful connection.
        mesapi_client: Client used to fetch production order information.
        machine_id: Identifier of the production line.
        queue: Asynchronous queue containing messages to process.
        extra_data: Data to merge into every outgoing message. Defaults to None.
        max_concurrent: Maximum number of concurrent publishing tasks. 
            Defaults to 50.

    Returns:
        None

    Raises:
        asyncio.CancelledError: If the worker task is cancelled by the 
            event loop.
    """
    extra_data = extra_data or {}  # Ensure extra_data is a dictionary even if None is passed

    async def process_message(data: dict[str, Any]) -> None:
        """
        Merge extra information to a message and publish it.

        Args:
            data: Raw message payload from the queue.

        Returns:
            None
        """
        async with semaphore:
            try:
                for key in extra_data:
                    data[key] = extra_data[key]
                
                try:
                    # Add order ID
                    data["order_id"] = await mesapi_client.get_current_order_id(machine_id)
                except Exception as e:
                    logger.warning(f"MESAPI | {e}")
                    data["order_id"] = None

                await mqtt_publisher.publish(data)
            except Exception as e:
                logger.error(f'MQTT | {e}')
                try:
                    await mqtt_publisher.disconnect()
                except:
                    pass

    semaphore = asyncio.Semaphore(max_concurrent)

    while True:  # External loop: manage connection and reconnection
        try:
            await mqtt_publisher.connect()

            logger.info(f"MQTT | Client connected to {mqtt_publisher.broker}.")

            try:
                await mqtt_publisher.publish(mqtt_birth_message, qos=1)
            except Exception as e:
                pass

            while True:  # Internal loop: manage message publishing
                data = await queue.get()  # Retrieve an item from the queue
                asyncio.create_task(process_message(data))
                queue.task_done()

        except Exception as e:
            logger.error(f'MQTT | {e}. New connection attempt in 3s...')
            try:
                await mqtt_publisher.disconnect()
            except:
                pass
            await asyncio.sleep(3)
            

async def main() -> None:
    """
    Entry point of the script.

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

    mqtt_data_true = {
        "timestamp": None,
        "machine_id": machine_id,
        "variable": "Data",
        "type": "Bool",
        "value": 1,
        "order_id": None
    }

    mqtt_data_false = {
        "timestamp": None,
        "machine_id": machine_id,
        "variable": "Data",
        "type": "Bool",
        "value": 0,
        "order_id": None
    }

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
        transport = os.getenv("MQTT_TRANSPORT"),
        will_payload = mqtt_data_false
    )

    logger.info("MQTT | Client started.")

    async with AsyncMesAPIClient(os.getenv("MESAPI_BASE_URL")) as mesapi_client:

        logger.info("MESAPI | Client started.")

        # Create a background task for the publishing process
        publisher_task = asyncio.create_task(publisher_worker(mqtt_publisher,
                                                              mqtt_data_true,
                                                              data_queue,
                                                              mesapi_client, 
                                                              machine_id,
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
                    pass
                await asyncio.sleep(3)

            except (asyncio.CancelledError, KeyboardInterrupt) as e:
                break
            except Exception as e:
                logger.error(f'OPC UA | {e}. New connection attempt in 3s...')
                try:
                    await opc_client.disconnect()
                except:
                    pass
                await asyncio.sleep(3)

        # Shutdown procedure

        # Note: clearing the queue is not necessary for this software bridge
        # between IoT protocols on edge devices. It is not required to
        # guarantee the delivery of every single message

        
        try:
            await opc_client.disconnect()
            logger.info("OPC UA | Client disconnected.")
        except Exception as e:
            logger.warning(f"OPC UA | {e}. Client forced to disconnect.")

        try:
            await mqtt_publisher.publish(mqtt_data_false)
            logger.info("MQTT | Published last will message before disconnecting.")
        except Exception as e:
            logger.error(f"MQTT | Error occurred while publishing last will message: {e}")

        publisher_task.cancel()

        try:
            await mqtt_publisher.disconnect()
            logger.info("MQTT | Client disconnected.")
        except Exception as e:
            logger.warning(f"MQTT | {e}. Client forced to disconnect.")

        device_telemetry.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(e)
