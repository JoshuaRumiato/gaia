"""
Asynchronous OPC UA client interface module.

Provides a wrapper class for the OPC UA protocol to simplify connection
management and data interaction with OPC UA servers, including subscription
handling for data change notifications.
"""

import datetime
import asyncio
from typing import Optional, Any

import asyncua

class SubscriptionHandler:
    """
    Handles data change notifications from an OPC UA subscription.
    
    Process incoming server notifications by mapping technical NodeIds 
    to human-readable names. This mapping prevents redundant asynchronous
    network requests for BrowseName resolution.

    Attributes:
        node_mapping (dict[str, str]): Dictionary mapping NodeId strings to node metadata
            (name and type).
        queue (asyncio.Queue): Asynchronous queue used as communication buffer.
    """

    def __init__(self, node_mapping: dict[str, str], queue: asyncio.Queue) -> None:
        """
        Initialize the SubscriptionHandler.
        
        Args:
            node_mapping (dict[str, str]): Map used for fast variable name resolution.
            queue (asyncio.Queue): Asynchronous queue used to store and share data.
        
        Returns:
            None
        """

        self.node_mapping = node_mapping
        self.queue = queue


    def status_change_notification(self, val: Any) -> None:
        """
        Handle status change notifications from the OPC UA server.

        Monitor the subscription status and raise an error if the connection 
        state becomes invalid or unhealthy.

        Args:
            val (Any): Object containing details about the subscription status change.

        Returns:
            None

        Raises:
            RuntimeError: If the notification status indicates a connection 
                failure or an invalid state.
        """

        if val.Status.value != 0:
            raise RuntimeError("Connection status changed badly")


    def datachange_notification(
            self,
            node: asyncua.common.node.Node,
            val: Any,
            data: asyncua.ua.uatypes.DataValue
    ) -> None:
        """
        Callback executed when a subscribed node value changes.

        Extract the NodeId, resolve its name through the mapping and
        encapsulate the update in a dictionary, then put it in the queue.

        Args:
            node (asyncua.common.node.Node): Node that triggered the notification.
            val (Any): New value of the node.
            data (asyncua.ua.uatypes.DataValue): Full data value object 
                containing metadata (timestamps, status, etc.).
        
        Returns:
            None
        """

        timestamp = datetime.datetime.now().timestamp()
        node_id_str = node.nodeid.to_string()
        node_info = self.node_mapping.get(node_id_str, {"name": node_id_str, "type": "Unknown"})

        change_data = {
            'timestamp': timestamp,
            'variable': node_info["name"],
            'type': node_info["type"],
            'value': int(val)
        }
        
        try:
            self.queue.put_nowait(change_data)  # Put data in the queue without blocking
        except asyncio.QueueFull:
            pass


class AsyncOPCClient:
    """
    Manages asynchronous OPC UA client connections.
    
    Wrapper class for asynchronous OPC UA client operations, providing
    methods to connect, disconnect, and subscribe to data changes.

    Attributes:
        host (str): Network address of the OPC UA server.
        port (int): Network port for the connection.
        username (Optional[str]): Username for server authentication.
        password (Optional[str]): Password for server authentication.
        client (opcua_client): Internal asyncronous OPC UA client instance.
        is_connected (bool): Boolean indicating connection status
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> None:
        """
        Initialize the AsyncOPCClient.

        Args:
            host (str): IP address or hostname of the OPC UA server.
            port (int): Port number (e.g., 4840).
            username (Optional[str]): Username for server authentication. Defaults to None.
            password (Optional[str]): Password for server authentication. Defaults to None.
        
        Returns:
            None
        """

        self.host = host
        self.port = port
        self.username = username
        self.password = password

        self.client = None
        self.is_connected = False


    async def connect(self) -> None:
        """
        Connect to the OPC UA server.

        Establish connection to the server endpoint using credentials
        provided during initialization. This method is idempotent: no
        action is performed if already connected.

        Returns:
            None

        Raises:
            ConnectionError: If the connection to the server fails.
        """
        if not self.client and not self.is_connected:
            try:
                self.client = asyncua.Client(url=f"opc.tcp://{self.host}:{self.port}")
                if self.username and self.password:
                    self.client.set_user_password(self.username, self.password)
                
                await self.client.connect()
                self.is_connected = True
            except Exception as e:
                self.client = None
                raise ConnectionError(f"Failed to connect to opc.tcp://{self.host}:{self.port}: {e}") from e


    async def disconnect(self) -> None:
        """
        Disconnect from the OPC UA server.

        Terminate the connection and clean up resources. This method is
        idempotent: no action is performed if already disconnected.

        Returns:
            None

        Raises:
            ConnectionError: If an error occurs while closing the connection.
        """

        if self.client and self.is_connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                raise ConnectionError(f"Failed to disconnect from opc.tcp://{self.host}:{self.port}: {e}") from e
            finally:
                self.client = None
                self.is_connected = False


    async def _get_data_type(self, node: asyncua.common.node.Node) -> str:
        """Resolve the OPC UA data type of a node to a human-readable string.

        Args:
            node (asyncua.common.node.Node): The node whose data type 
                needs to be identified.

        Returns:
            str: The name of the data type (e.g., 'Double', 'Int32') 
                or 'Unknown' if no match is found.
        """
        
        node_type = await node.read_data_type()

        # VariantType is an Enum. Items can be accessed via __members__
        for name, member in asyncua.ua.VariantType.__members__.items():
            if member.value == node_type.Identifier:
                return name
        return "Unknown"
        
    
    async def subscribe_to_variables(
            self,
            node_ids: list[str],
            queue: asyncio.Queue,
            period: int = 500
    ) -> asyncua.common.subscription.Subscription:
        """
        Subscribe to data changes for a list of node IDs.

        Create a local mapping of NodeIds to BrowseNames for efficient access, 
        and initialize an OPC UA subscription for the specified nodes. Data change
        notifications are processed by a handler that enriches them with metadata
        and places them in the provided queue for asynchronous processing.

        Args:
            node_ids (list[str]): List of Node ID strings to subscribe to.
            queue (asyncio.Queue): Asynchronous queue for storing data changes
                enriched with metadata (timestamp, variable name, type, value).
            period (int): Publishing interval in milliseconds. Defaults to 500.

        Returns:
            asyncua.common.subscription.Subscription: The created subscription object.

        Raises:
            RuntimeError: If called while the client is disconnected or not connected
                to the OPC UA server.
        """
        
        if not self.is_connected:
            raise RuntimeError(f"Client is not connected to the server")
        
        try:
            node_mapping = {}
            variables = []

            for node_id_str in node_ids:
                node = self.client.get_node(node_id_str)
                variables.append(node)

                # Read metadata for mapping
                browse_name = await node.read_browse_name()
                node_type = await self._get_data_type(node)

                node_mapping[node_id_str] = {
                    "name" : browse_name.Name,
                    "type" : node_type
                }

            handler = SubscriptionHandler(node_mapping, queue)
            subscription = await self.client.create_subscription(period, handler)
            await subscription.subscribe_data_change(variables)
            return subscription
        except Exception as e:
            raise RuntimeError(f"Could not perform subscription: {e}") from e
