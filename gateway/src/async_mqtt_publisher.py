"""
Asyncronous MQTT communication module.

Provide a wrapper for the `aiomqtt` library to simplify 
the process of connecting and publishing messages to an MQTT broker.

Handle SSL/TLS configuration and JSON serialization internally. 
"""

import json
import ssl
from typing import Literal, Optional

import aiomqtt

class AsyncMQTTPublisher:
    """Client handler for publishing messages asyncronously
    to an MQTT broker.

    Manage the connection lifecycle and provides methods 
    to send data to specific topics using the MQTT protocol.

    Attributes:
        broker (str): Network address of the MQTT broker.
        port (int): Network port for the connection.
        topic (str): Topic where messages will be published.
        client_id (str): Unique identifier for the MQTT client.
        username (str, optional): Username for broker authentication.
        password (str, optional): Password for broker authentication.
        use_tls (bool): Whether to use Transport Layer Security (TLS).
        transport (str): Transport protocol to use (`tcp`, `websockets` or `unix`).
        client (aiomqtt.Client): Internal asynchronous MQTT client instance.
        is_connected (bool): State tracking connection status
    """
    
    def __init__(
            self,
            broker: str,
            port: int,
            topic: str,
            client_id: str,
            username: Optional[str] = None,
            password: Optional[str] = None,
            use_tls: bool = False,
            transport: Literal["tcp", "websockets", "unix"] = "tcp"
    ) -> None:
        """
        Initialize the AsyncMQTTPublisher object with the given connection parameters.

        Args:
            broker (str): IP address or hostname of the MQTT broker.
            port (int): Port number (e.g., 1883 for TCP or 8883 for TLS).
            topic (str): MQTT topic used for publishing.
            client_id (str): Unique string identifying the client.
            username (str, optional): Usernname for authentication with the broker.
                Defaults to None.
            password (str, optional): Password for authentication with the broker.
                Defaults to None.
            use_tls (bool, optional): If `True`, enables TLS encryption for 
                the connection. Defaults to `False`.
            transport (str, optional): Transport protocol adopted. 
                Defaults to 'tcp'.

        Returns:
            None

        Raises:
            ValueError: If an invalid transport protocol is specified.
        """

        valid_transports = ["tcp", "websockets", "unix"]
        if transport not in valid_transports:
            raise ValueError(f"Invalid transport '{transport}'. Must be one of {valid_transports}")

        self.broker = broker
        self.port = port
        self.topic = topic
        self.client_id = client_id
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.transport = transport
        self.client = None
        self.is_connected = False  


    async def connect(self) -> None:
        """
        Connect to the MQTT broker and starts the asyncronous network loop.

        Before connection, configure the transport layer protocol and SSL/TLS
        contex if enabled.

        This method is idempotent: no action will be performed if a connection
        is already active.

        Returns:
            None

        Raises:
            ConnectionError: If the connection to the broker fails.
        """

        if not self.is_connected:  # Ensure idempotent behaviour
            
            # 1. Set up SSL/TLS context (if enabled)
            tls_params = None
            if self.use_tls:
                tls_params = ssl.create_default_context()
                tls_params.verify_mode = ssl.CERT_REQUIRED
            
            # 2. Initialize the aiomqtt.Client instance
            self.client = aiomqtt.Client(
                hostname=self.broker,
                port=self.port,
                username=self.username,
                password=self.password,
                identifier=self.client_id,
                tls_context=tls_params,
                transport=self.transport,
                websocket_path="/mqtt" if self.transport == "websockets" else None
            )

            # 3. Try to connect, otherwise raise an Error
            try:
                await self.client.__aenter__()
                self.is_connected = True
            except Exception as e:
                self.is_connected = False
                raise ConnectionError(f"Failed to connect to {self.broker}: {e}") from e


    async def publish(self, msg: dict, qos: int = 0) -> None:
        """Serialize a dictionary to JSON and publish it to the configured topic.

        Args:
            msg (dict): Data dictionary to be sent as a JSON payload.
            qos (int): Quality of Service level (0, 1, or 2). Defaults to 0.

        Raises:
            RuntimeError: If called while the client is disconnected or 
                if the publish process fails.
            TypeError: If the input message is not a dictionary or contains
                non-serializable objects.
        """

        if not self.is_connected or self.client is None:
            raise RuntimeError(f"Client is not connected to the broker.")

        if not isinstance(msg, dict):
            raise TypeError("Message payload must be a dictionary.")

        try:
            payload = json.dumps(msg)  # Convert dictionary to a JSON string
            print(payload)
            await self.client.publish(
                self.topic, 
                payload=payload,
                qos=qos
            )
                
        except Exception as e:
            raise RuntimeError(f"Failed to publish message: {e}")


    async def disconnect(self) -> None:
        """
        Disconnect from the MQTT broker and stop the asynchronous network loop.

        This method should be called before the application instance is destroyed.

        This method is idempotent: no action will be performed if no
        connection is active.

        Returns:
            None
        """
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
            except Exception as e:
                raise RuntimeError(f"Failed to disconnect from the broker: {e}")
            finally:
                # Ensures that the instance is reset even if the disconnection fails
                self.client = None
        
        self.is_connected = False
