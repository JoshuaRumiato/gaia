"""OPC UA server module for simulating industrial equipment.

Provides a wrapper class that simulates an OPC UA server implementing a 
KEPServerEX-like architecture with channels, devices, and boolean tags for
machine state monitoring.
"""

import asyncio
import logging
import random
from typing import Optional

from asyncua import ua, Server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress verbose logging from asyncua address space and binary utilities
logging.getLogger("asyncua.server.address_space").setLevel(logging.WARNING)
logging.getLogger("asyncua.common.binary_utils").setLevel(logging.WARNING)

class OPCServer:
    """
    Simulates an OPC UA server with industrial device structure.
    
    Implements a KEPServerEX-like architecture with a channel, device, and
    boolean tags for machine state: InAlarm, InBypass, InCycle, InWarning.

    Attributes:
        server: Internal OPC UA server instance.
        endpoint: OPC UA endpoint URL.
        channel: Folder node representing the communication channel.
        device: Folder node representing the device.
        tags: Dictionary mapping tag names to node objects.
    """

    def __init__(self, endpoint: str) -> None:
        """
        Initialize the OPC UA server.
        
        Args:
            endpoint (str): OPC UA endpoint URL.

        Returns:
            None
        """
        self.server = Server()
        self.endpoint = endpoint
        self.channel = None
        self.device = None
        self.tags = {}


    async def setup(self) -> None:
        """
        Configure the server and create the node structure.
        
        Set up the server name, endpoint, and initialize the node hierarchy
        (Channel -> Device -> Tags) with boolean state variables.

        Returns:
            None
        """

        self.server.set_server_name("G.A.I.A. - OPC UA server")
        self.server.set_endpoint(self.endpoint)

        await self.server.init()
        
        idx = 2  # Custom namespace index for our nodes
        objects_node = self.server.get_objects_node()
        
        # Create structure: Channel -> Device -> Tags
        # Using string-based NodeIds to match gateway subscription expectations

        self.channel = await objects_node.add_folder(
            ua.NodeId("Channel1", idx),
            "Channel1"
        )

        self.device = await self.channel.add_folder(
            ua.NodeId("Channel1.Device1", idx), 
            "Device1"
        )
        
        boolean_tags = ["InAlarm", "InBypass", "InCycle", "InWarning"]
        counter_tags = ["MachinePieceCounter", "LinePieceCounter"]
        self.tag_types = {
            **dict.fromkeys(boolean_tags, ua.VariantType.Boolean),
            **dict.fromkeys(counter_tags, ua.VariantType.Int32),
        }

        for tag in boolean_tags:
            self.tags[tag] = await self.device.add_variable(
                ua.NodeId(f"Channel1.Device1.{tag}", idx),
                tag,
                False,
                ua.VariantType.Boolean
            )

        for tag in counter_tags:
            self.tags[tag] = await self.device.add_variable(
                ua.NodeId(f"Channel1.Device1.{tag}", idx),
                tag,
                random.randint(300, 500),
                ua.VariantType.Int32
            )


    async def start(self) -> None:
        """
        Start the OPC UA server.
        
        Start the server and wait indefinitely for client connections.

        Returns:
            None
        """
        async with self.server:
            await asyncio.Event().wait()


    async def stop(self) -> None:
        """
        Stop the OPC UA server.

        Returns:
            None
        """
        await self.server.stop()

    async def set_tag_value(self, tag_name: str, value: bool | int) -> None:
        """
        Set the value of a tag.

        Args:
            tag_name (str): Name of the tag (InAlarm, InBypass, InCycle, InWarning).
            value (bool): Boolean value to set.

        Returns:
            None
        """
        if tag_name in self.tags:
            await self.tags[tag_name].write_value(
                ua.Variant(value, self.tag_types[tag_name])
            )
        else:
            logger.warning(f"Tag '{tag_name}' not found")

    async def get_tag_value(self, tag_name: str) -> Optional[bool]:
        """
        Get the value of a tag.

        Args:
            tag_name (str): Name of the tag (InAlarm, InBypass, InCycle, InWarning).

        Returns:
            Optional[bool]: The boolean value of the tag, or None if tag not found.
        """
        if tag_name in self.tags:
            return await self.tags[tag_name].read_value()
        else:
            logger.warning(f"Tag '{tag_name}' not found")
            return None

    # async def print_tag_status(self) -> None:
    #     """Print the current status of all tags.
        
    #     Returns:
    #         None
    #     """
    #     for tag_name in self.tags.keys():
    #         value = await self.get_tag_value(tag_name)
    #         print(f"\t{tag_name}: {value}\t", end=" | ")
    #     print()
