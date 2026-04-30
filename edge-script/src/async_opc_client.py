"""
Asyncronous OPC UA client interface module

Provide a wrapper class for the OPC UA protocol to simplify 
connection management and data interaction with OPC UA servers.
"""

import datetime
import asyncio
from typing import Optional, Any

import asyncua

class SubscriptionHandler:
    """Internal handler for data change notifications from an OPC UA subscription

    Process incoming server notifications by mapping technical NodeIds 
    to human-readable names. This mapping prevents redundant asyncronous
    network requests for BrowseName.

    Attributes:
        node_mapping (dict[str, str]): Object mapping NodeId strings to their 
            corresponding BrowseNames.
        queue (asyncio.Queue): Asyncronouse queue used as communication buffer.
    """

    def __init__(self, node_mapping: dict[str, str], queue: asyncio.Queue) -> None:
        """
        Initializes the SubscriptionHandler with a node map and a message queue.

        Returns:
            None

        Args:
            node_mapping (dict[str, str]): Map used for fast variable name resolution.
            queue (asyncio.Queue): Asyncronous queue used to store and share data.
        """

        self.node_mapping = node_mapping
        self.queue = queue


    def status_change_notification(self, val):
        if val.Status.value != 0:
            raise RuntimeError("Connection status changed badly")


    def datachange_notification(
            self,
            node: asyncua.common.node.Node,
            val: Any,
            data: asyncua.ua.uatypes.DataValue
    ) -> None:
        """Callback method executed automatically when a node value changes.

        Extract the NodeId, resolve its name through the mapping and
        encapsulate the update in a dictionary. Finally, puts the object
        in the communication queue.

        Args:
            node (asyncua.common.node.Node): Node that triggered the notification.
            val (Any): New value of the node.
            data (asyncua.ua.uatypes.DataValue): Full data value object 
                containing metadata (timestamps, status, etc.).
        """
        
        timestamp = datetime.datetime.now().timestamp()
        node_id_str = node.nodeid.to_string()
        node_info = self.node_mapping.get(node_id_str, {"name": node_id_str, "type": "Unknown"})

        change_data = {
            'timestamp': timestamp,
            'variable': node_info["name"],
            'type': node_info["type"],
            'value': val
        }
        
        try:
            # Put the data in the queue without blocking
            self.queue.put_nowait(change_data)
        except asyncio.QueueFull:
            pass
        

class AsyncOPCClient:
    """Wrapper class for managing asyncrnonous OPC UA client connections.

    Allow to both get variables values and subscribe to data changes.

    Attributes:
        host (str): Network address of the OPC UA server.
        port (int): Network port for the connection.
        username (Optional[str]): Username for server authentication.
        password (Optional[str]): Password for server authentication.
        client (opcua_client): Internal asyncronous OPC UA client instance.
        is_connected (bool): State tracking connection status
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> None:
        """Initializes the AsyncOPCClient object with the given connection parameters.

        Args:
            host (str): IP address or hostname of the OPC UA server.
            port (int): Port number (e.g., 4840).
            username (str, optional): Username for server authentication. 
                Defaults to None.
            password (str, optional): Password for server authentication.
                Defaults to None.
        
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
        """Connect to the OPC UA server.

        Attempt to connect using the endpoint and credentials provided 
        during initialization.

        This method is idempotent: no action will be performed if a connection
        is already active.

        Returns:
            None

        Raises:
            ConnectionError: If the connection to the server fails.
        """
        if not self.client and not self.is_connected:  # Ensure idempotent behaviour
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
        """Disconnect from the OPC UA server.

        This method should be called before the application instance is destroyed.

        This method is idempotent: no action will be performed if no
        connection is active.

        Returns:
            None

        Raises:
            ConnectionError: If an error occurs while attempting to close 
                the connection to the server.
        """

        if self.client and self.is_connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                raise ConnectionError(f"Failed to disconnect from opc.tcp://{self.host}:{self.port}: {e}") from e
            finally:
                self.client = None
                self.is_connected = False


    def get_root_node(self) -> Optional[asyncua.common.node.Node]:
        """Returns the root node of the server
        
        Returns:
            asyncua.common.node.Node: Node representing the root of the OPC UA server
        """
        if self.client and self.is_connected:
            return self.client.nodes.root


    def get_objects_node(self) -> Optional[asyncua.common.node.Node]:
        """Retrieve the `Objects` folder node from the OPC UA server.

        The `Objects` node is the standard entry point for browsing the 
        server's address space and accessing custom variables and objects.

        If no connection was established before calling this method, return `None`.

        Returns:
            Optional[asyncua.common.node.Node]: `asyncua` Node object representing the standard 
                `Objects` folder.
        """
        if self.client and self.is_connected:
            return self.client.nodes.objects
        return None


    async def get_child_by_name(self, parent: asyncua.common.node.Node, name: str) -> Optional[asyncua.common.node.Node]:
        """Find a child node by its BrowseName.

        Iterate through all children of a given parent node and compare 
        their BrowseName with the provided string.

        If no connection was established before calling this method, return `None`.

        Args:
            parent (asyncua.common.node.Node): Parent node to search within.
            name (str): BrowseName of the child node to find.

        Returns:
            Optional[Node]: Matching child node if found.
        """
        if self.client and self.is_connected:
            children = await parent.get_children()
            for c in children:
                browse_name = await c.read_browse_name()
                if browse_name.Name == name:
                    return c
        return None


    async def _get_data_type(self, node: asyncua.common.node.Node):
        node_type = await node.read_data_type()

        # VariantType is an Enum. It is possible to access its items and values 
        # in a map-like object by calling the method items() on __members__
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
        """Set up a subscription to get data changes for all variables whithin a folder.

        Identifies variable nodes, create a local mapping of NodeIds 
        to BrowseNames for efficient access, and initialize an OPC UA subscription.

        Args:
            folder_node (asyncua.common.node.Node): Parent node containing variables to subscribe to.
            queue (asyncio.Queue): Asyncronous queue used to store and share data.
            period (int): Publishing interval in milliseconds. Defaults to 500.

        Returns:
            asyncua.common.subscription.Subscription: The created subscription object.

        Raises:
            RuntimeError: If called while the client is disconnected
        """
        
        if not self.is_connected:
            raise RuntimeError(f"Client is not connected to the server")
        
        try:
            node_mapping = {}
            variables = []

            for node_id_str in node_ids:
                node_class = await node_id_str.read_node_class()
                if node_class == asyncua.ua.NodeClass.Variable:
                    variables.append(node_id_str)
                    browse_name = await node_id_str.read_browse_name()
                    node_type = await self._get_data_type(node_id_str)
                    node_mapping[node_id_str.nodeid.to_string()] = {
                        "name": browse_name.Name,
                        "type": node_type
                    }

            handler = SubscriptionHandler(node_mapping, queue)
            subscription = await self.client.create_subscription(period, handler)
            await subscription.subscribe_data_change(variables)
            return subscription
        except Exception as e:
            raise RuntimeError(f"Could not perform subscription: {e}") from e
