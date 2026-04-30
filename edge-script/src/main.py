import os
import sys
import signal
import asyncio
import logging

from telemetry import Telemetry
from async_opc_client import AsyncOPCClient
from async_mqtt_publisher import AsyncMQTTPublisher
from async_mesapi_client import AsyncMesAPIClient


# Required for compatibility between aiomqtt and Python's default event loop for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize the logger for the module
logger = logging.getLogger("edge-logger")


def load_config() -> dict[str, dict[str, str | int | bool]]:
    return {
        "global" : {
            "manufacturer" : os.getenv("MANUFACTURER"),
            "line" : os.getenv("LINE")
        },
        "telemetry": {
            "host" : os.getenv("OTEL_HOST"),
            "port" : int(os.getenv("OTEL_PORT")),
            "service_name" : os.getenv("OTEL_SERVICE_NAME"),
            "deployment_environment" : os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT")
        },
        "opcua_server": {
            "host" : os.getenv("OPCUA_HOST"),
            "port" : int(os.getenv("OPCUA_PORT")),
            "username" : os.getenv("OPCUA_USERNAME"),
            "password" : os.getenv("OPCUA_PASSWORD"),
            "monitored_items" : os.getenv("OPCUA_MONITORED_ITEMS")
        },
        "mqtt_publisher": {
            "host" : os.getenv("MQTT_HOST"),
            "port" : int(os.getenv("MQTT_PORT")),
            "topic" : os.getenv("MQTT_TOPIC"),
            "username" : os.getenv("MQTT_USERNAME"),
            "password" : os.getenv("MQTT_PASSWORD"),
            "use_tls" : os.getenv("MQTT_USE_TLS") == "true",
            "transport" : os.getenv("MQTT_TRANSPORT") 
        }
    }


async def publisher_worker(
        mqtt_publisher: AsyncMQTTPublisher,
        mesapi_client: AsyncMesAPIClient, 
        prod_line: str,
        queue: asyncio.Queue,
        extra_data: dict[str, str] = {},
        max_concurrent: int = 50
) -> None:
    """Consume messages from a queue, add some extra info and publish them via MQTT.

    This worker maintains an active connection to the MQTT broker, handles
    automatic retries on connection failure, and processes messages 
    asynchronously from the provided queue.

    Args:
        mqtt_publisher (AsyncMQTTPublisher): The client used to publish messages.
        queue (asyncio.Queue): The asynchronous queue containing messages to be sent.

    Returns:
        None
    """

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_message(data: dict[str, str | int]) -> None:
        async with semaphore:
            try:
                for key in extra_data:
                    data[key] = extra_data[key]
                
                try:
                    # Add fase_id to get production order info when visualizing data
                    data["fase_id"] = await mesapi_client.get_current_fase_id(prod_line)
                except Exception as e:
                    logger.warning(f"MESAPI | {e}")
                    data["fase_id"] = None

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
    asycronous queue, and publish them via MQTT.

    If connection with the OPC UA server or with the MQTT broker fails, the function
    will permanently try to reconnect, unless it is manually stopped by the user.

    Returns:
        None
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
    

    config = load_config()
    manufacturer = config['global']['manufatrurer']
    prod_line = config['global']['line']
    client_id = f"{manufacturer}_{prod_line}"
    data_queue = asyncio.Queue(maxsize = 1000)

    device_telemetry = Telemetry(
        endpoint_host = config['telemetry']['host'],
        endpoint_port = config['telemetry']['port'],
        service_name = config['telemetry']['service_name'],
        deployment_environment = config['telemetry']['deployment_environment'],
        hostname = client_id,
        queue = data_queue
    )

    device_telemetry.setup()

    opc_client = AsyncOPCClient(
        host = config['opcua_server']['host'],
        port = config['opcua_server']['port'],
        username = config['opcua_server']['username'],
        password = config['opcua_server']['password']
    )
    
    logger.info("OPC UA | Client started.")

    mqtt_publisher = AsyncMQTTPublisher(
        broker = config['mqtt_publisher']['host'],
        port = config['mqtt_publisher']['port'],  # Cast the value to int (default is str)
        topic = config['mqtt_publisher']['topic'],
        client_id = client_id,
        username = config['mqtt_publisher']['username'],
        password = config['mqtt_publisher']['password'],
        use_tls = config['mqtt_publisher']['use_tls'],
        transport = config['mqtt_publisher']['transport']
    )

    logger.info("MQTT | Client started.")

    async with AsyncMesAPIClient() as mesapi_client:

        logger.info("MESAPI | Client started.")

        # Create a background task for the publishing process
        publisher_task = asyncio.create_task(publisher_worker(mqtt_publisher,
                                                              mesapi_client, 
                                                              prod_line,
                                                              data_queue,
                                                              {"client_id" : client_id}))

        while True:
            try:
                await opc_client.connect()
                logger.info(f"OPC UA | Client connected to {opc_client.host}.")

                monitored_items = [ s for s in config["opcua_server"]["monitored_items"].split("|") if s.strip() ]

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
