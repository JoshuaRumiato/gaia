"""
IoT Bridge for OPC UA to MQTT data ingestion.

This module acts as the entry point for the application. It orchestrates 
the connection to an OPC UA server, monitors specific variables, and 
publishes the gathered data to an MQTT broker. It also handles system 
signals for a graceful shutdown and manages telemetry and MES API integration.
"""

import os
import sys
import signal
import asyncio
import logging
import random
from typing import Any

from gateway_telemetry import GatewayTelemetry
from async_opc_client import AsyncOPCClient
from async_mqtt_publisher import AsyncMQTTPublisher
from counter_watchdog import CounterWatchdog

# Exponential backoff parameters
BASE_TIME = 3.0  # Base time in seconds for the initial retry delay
MAX_TIME = BASE_TIME * 2**7  # Backoff increase stops at the eigth retry (3s * 2^7 = 384s)

# Required for compatibility between aiomqtt and Python's default event loop for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize the logger for the module
logger = logging.getLogger("gateway-logger")


async def publisher_worker(
        mqtt_publisher: AsyncMQTTPublisher,
        mqtt_birth_message: dict[str, Any],
        queue: asyncio.Queue,
        watchdog: CounterWatchdog,
        max_concurrent: int = 50
) -> None:
    """
    Consume and process messages from a queue, then publish them via MQTT.

    Maintain an active connection to the MQTT broker, handle automatic 
    retries on connection failure, and process messages asynchronously 
    from the provided queue. Each message is enriched with extra data and
    production order information before publishing. The worker continuously
    attempts to reconnect to the broker in case of disconnection with a 3
    second retry delay.

    Args:
        mqtt_publisher: Client used to publish messages.
        mqtt_birth_message: Message to publish upon successful connection.
        queue: Asynchronous queue containing messages to process.
        extra_data: Data to merge into every outgoing message. Defaults to None.
        max_concurrent: Maximum number of concurrent publishing tasks. 
            Defaults to 50.

    Returns:
        None

    Raises:
        asyncio.CancelledError: If the worker task is cancelled by the 
            event loop or during application shutdown.
    """

    semaphore = asyncio.Semaphore(max_concurrent)  # Limit the number of concurrent publishing tasks
    mqtt_connection_attempt = 0  # Track the number of connection attempts to the MQTT broker (used for exponential backoff)

    async def publish_message(data: dict[str, Any]) -> None:
        """Publish the message via MQTT.

        Handle connection resets on failure. 

        Args:
            data (dict[str, Any]): Raw message payload retrieved from the queue.

        Returns:
            None
        """
        async with semaphore:
            try:
                await mqtt_publisher.publish(data)
            except Exception as e:
                logger.error(f'MQTT | {e}')
                try:
                    await mqtt_publisher.disconnect()  # Force the client to disconnect
                except:
                    pass

    while True:  # External loop: manage connection and reconnection
        try:
            await mqtt_publisher.connect()
            logger.info(f"MQTT | Client connected to {mqtt_publisher.broker}.")
            mqtt_connection_attempt = 0  # Connection successful, reset the numeber of attempts

            try:
                await mqtt_publisher.publish(mqtt_birth_message, qos=2)
            except Exception as e:
                raise ConnectionError(f"Failed to publish birth message: {e}")

            while True:  # Internal loop: manage message publishing
                if not mqtt_publisher.is_connected:
                    raise ConnectionError("MQTT connection was lost.")
                
                data = await queue.get()  # Retrieve an item from the queue
                anomaly_event = watchdog.process_event(data)
                if anomaly_event:
                    asyncio.create_task(publish_message(anomaly_event))
                    
                asyncio.create_task(publish_message(data))
                queue.task_done()

        except Exception as e:
            mqtt_reconnection_attempt += 1
            base_delay = min(BASE_TIME * 2**(mqtt_reconnection_attempt - 1), MAX_TIME)
            actual_delay = random.uniform(base_delay*0.8, base_delay*1.2)  # Add jitter with range [-20%, +20%]

            logger.error(f'MQTT | {e}. New connection attempt in {actual_delay:.2f}s...')
            try:
                await mqtt_publisher.disconnect()
            except:
                pass
            await asyncio.sleep(actual_delay)
            

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
        """
        Cancel the main task when a stop signal (SIGINT, SIGTERM) is received.
        
        This handler enables graceful shutdown of the gateway application,
        ensuring proper cleanup of connections and resources.
        
        Returns:
            None
        """
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
        "timestamp": 0.0,
        "machine_id": machine_id,
        "variable": "DataValid",
        "type": "Boolean",
        "value": 1,
        "event_type": "D"  # Derived
    }

    mqtt_data_false = {
        "timestamp": 0.0,
        "machine_id": machine_id,
        "variable": "DataValid",
        "type": "Boolean",
        "value": 0,
        "event_type": "D"  # Derived
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
        machine_id = machine_id,
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

    counter_watchdog = CounterWatchdog(
        client_id = client_id,
        timeout_seconds = float(os.getenv("WATCHDOG_TIMEOUT_SECONDS")),
        min_pieces = int(os.getenv("WATCHDOG_MIN_PIECES")),
        line_counter_name = os.getenv("WATCHDOG_LINE_COUNTER_NAME"),
        machine_counter_name = os.getenv("WATCHDOG_MACHINE_COUNTER_NAME")
    )

    # Create a background task for the publishing process
    publisher_task = asyncio.create_task(publisher_worker(mqtt_publisher,
                                                            mqtt_data_true,
                                                            data_queue,
                                                            counter_watchdog))

    opcua_connection_attempt = 0

    while True:
        try:
            await opc_client.connect()
            logger.info(f"OPC UA | Client connected to {opc_client.host}.")
            opcua_connection_attempt = 0  # Connection successful, reset the number of attempts

            # Get the nodes to monitor
            monitored_items = [ s for s in os.getenv("OPCUA_MONITORED_ITEMS").split("|") if s.strip() ]
            subscription = await opc_client.subscribe_to_variables(monitored_items, data_queue, period=500)
            if subscription:
                logger.info(f"OPC UA | Subscriptions activated for: {monitored_items}.")
                
                while True:
                    await opc_client.client.check_connection()
                    await asyncio.sleep(30)
            else:    
                raise ConnectionError(f"Unable to subscribe to data changes for {monitored_items}.")

        except (asyncio.CancelledError, KeyboardInterrupt) as e:
            break
        except Exception as e:
            opcua_connection_attempt += 1
            base_delay = min(BASE_TIME * 2**(opcua_connection_attempt - 1), MAX_TIME)
            actual_delay = random.uniform(base_delay*0.8, base_delay*1.2)  # Add jitter with range [-20%, +20%]

            logger.error(f'OPC UA | {e}. New connection attempt in {actual_delay:.2f}s...')
            try:
                await opc_client.disconnect()
            except:
                pass
            await asyncio.sleep(actual_delay)

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
