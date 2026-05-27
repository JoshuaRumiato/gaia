"""
Asynchronous MQTT communication module.

Provides a wrapper for the `aiomqtt` library to simplify MQTT client
connections and message publishing to an MQTT broker, with built-in
SSL/TLS configuration and JSON serialization support.
"""

import json
import ssl
from typing import Literal, Optional

import aiomqtt

class AsyncMQTTPublisher:
    """
    Client for publishing messages asynchronously to an MQTT broker.
    
    Manages the connection lifecycle and provides methods to send data to
    specific topics using the MQTT protocol with support for TLS and
    multiple transport protocols.

    Attributes:
        broker: Network address of the MQTT broker.
        port: Network port for the connection.
        topic: Topic where messages will be published.
        client_id: Unique identifier for the MQTT client.
        username: Username for broker authentication.
        password: Password for broker authentication.
        use_tls: Whether to use Transport Layer Security (TLS).
        transport: Transport protocol to use (tcp, websockets, or unix).
        will_payload: Optional dictionary for the MQTT Last Will message.
        client: Internal asynchronous MQTT client instance.
        is_connected: Boolean indicating connection status.
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
            transport: Literal["tcp", "websockets", "unix"] = "tcp",
            will_payload: Optional[dict] = None
    ) -> None:
        """
        Initialize the AsyncMQTTPublisher.

        Args:
            broker (str): IP address or hostname of the MQTT broker.
            port (int): Port number (e.g., 1883 for TCP or 8883 for TLS).
            topic (str): MQTT topic used for publishing.
            client_id (str): Unique string identifying the client.
            username (Optional[str]): Username for broker authentication. Defaults to None.
            password (Optional[str]): Password for broker authentication. Defaults to None.
            use_tls (bool): If True, enables TLS encryption. Defaults to False.
            transport (Literal["tcp", "websockets", "unix"]): Transport protocol to use. Defaults to 'tcp'.
            will_payload (Optional[dict]): Dictionary for the will message. Defaults to None.
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
        self.will_payload = will_payload
        self.client = None
        self.is_connected = False


    async def connect(self) -> None:
        """
        Connect to the MQTT broker and start the network event loop.

        Configure the transport layer protocol and SSL/TLS context if enabled.
        This method is idempotent: no action is performed if already connected.

        Returns:
            None

        Raises:
            TypeError: If the will_payload is not a dictionary when provided.
            ConnectionError: If the connection to the broker fails.
        """

        if not self.is_connected:
            # Set up SSL/TLS context (if enabled)
            tls_params = None
            if self.use_tls:
                tls_params = ssl.create_default_context()
                tls_params.verify_mode = ssl.CERT_REQUIRED

            if self.will_payload is not None and not isinstance(self.will_payload, dict):
                raise TypeError("Will payload must be a dictionary.")

            mqtt_will = None
            if self.will_payload is not None:
                mqtt_will = aiomqtt.Will(
                    topic=self.topic,
                    payload=json.dumps(self.will_payload),
                    qos=1,
                    retain=False
                )
            
            # Initialize the aiomqtt.Client instance
            self.client = aiomqtt.Client(
                hostname=self.broker,
                port=self.port,
                username=self.username,
                password=self.password,
                identifier=self.client_id,
                will=mqtt_will,
                tls_context=tls_params,
                transport=self.transport,
                websocket_path="/mqtt" if self.transport == "websockets" else None
            )

            # Attempt to connect
            try:
                await self.client.__aenter__()
                self.is_connected = True
            except Exception as e:
                self.is_connected = False
                raise ConnectionError(f"Failed to connect to {self.broker}: {e}") from e


    async def publish(self, msg: dict, qos: int = 0) -> None:
        """
        Serialize a dictionary to JSON and publish it to the configured topic.

        Args:
            msg (dict): Data dictionary to be sent as a JSON payload.
            qos (int): Quality of Service level (0, 1, or 2). Defaults to 0.

        Returns:
            None

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
            payload = json.dumps(msg)  # Serialize dictionary to JSON string
            await self.client.publish(
                self.topic, 
                payload=payload,
                qos=qos
            )
                
        except Exception as e:
            raise RuntimeError(f"Failed to publish message: {e}")


    async def disconnect(self) -> None:
        """
        Disconnect from the MQTT broker and stop the event loop.

        Clean up resources and close the connection. This method is idempotent:
        no action is performed if already disconnected.

        Returns:
            None

        Raises:
            RuntimeError: If an error occurs during disconnection.
        """
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
            except Exception as e:
                raise RuntimeError(f"Failed to disconnect from the broker: {e}")
            finally:
                self.client = None
        
        self.is_connected = False
