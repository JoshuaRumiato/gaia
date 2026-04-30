"""
OPC UA Server wrapper class that simulates 
"""

import asyncio
import logging

from asyncua import ua, Server

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Silenzia specificamente il modulo dell'address space di asyncua
logging.getLogger("asyncua.server.address_space").setLevel(logging.WARNING)
# Opzionale: silenzia anche la gestione binaria se troppo verbosa
logging.getLogger("asyncua.common.binary_utils").setLevel(logging.WARNING)

class OPCServer:
    """
    Server OPCUA che simula l'architettura di KEPServerEX con:
    - Un canale
    - Un device dentro il canale
    - 4 tag boolean per gli stati macchina: InAlarm, InBypass, InCycle, InWarning
    """

    def __init__(self, endpoint: str = "opc.tcp://0.0.0.0:4840/freeopcua/server/") -> None:
        """
        Initialize the OPCUA server.
        
        Args:
            endpoint (str): OPCUA endpoint URL.
                Defaults to "opc.tcp://0.0.0.0:4840/freeopcua/server/"

        Returns:
            None
        """
        self.server = Server()
        self.endpoint = endpoint
        self.channel = None
        self.device = None
        self.tags = {}
        logger.info(f"Server OPCUA inizializzato con endpoint: {endpoint}")


    async def setup(self) -> None:
        """Configura il server e la struttura di nodi."""

        self.server.set_server_name("IoT project - OPCUA server")  # Set server name
        self.server.set_endpoint(self.endpoint)

        await self.server.init()
        
        idx = 2  # Ottieni lo spazio dei nomi di default
        objects_node = self.server.get_objects_node()
        
        # Create structure: Channel -> Device -> Tags

        self.channel = await objects_node.add_folder(idx, "Channel1")
        logger.info("Canale 'Channel1' creato")

        self.device = await self.channel.add_folder(idx, "Device1")
        logger.info("Device 'Device1' creato dentro il canale")
        
        self.tags['InAlarm'] = await self.device.add_variable(
            idx, 
            "InAlarm", 
            False,
            varianttype=ua.VariantType.Boolean
        )
        await self.tags['InAlarm'].set_writable(True)
        
        self.tags['InBypass'] = await self.device.add_variable(
            idx, 
            "InBypass", 
            False,
            varianttype=ua.VariantType.Boolean
        )
        await self.tags['InBypass'].set_writable(True)
        
        self.tags['InCycle'] = await self.device.add_variable(
            idx, 
            "InCycle", 
            False,
            varianttype=ua.VariantType.Boolean
        )
        await self.tags['InCycle'].set_writable(True)
        
        self.tags['InWarning'] = await self.device.add_variable(
            idx, 
            "InWarning", 
            False,
            varianttype=ua.VariantType.Boolean
        )
        await self.tags['InWarning'].set_writable(True)
        
        logger.info("Tag creati: InAlarm, InBypass, InCycle, InWarning")


    async def start(self) -> None:
        """Start OPC UA server.."""
        async with self.server:
            logger.info("Server OPCUA avviato")
            logger.info(f"Endpoint disponibile su: {self.endpoint}")
            await asyncio.Event().wait()


    async def stop(self) -> None:
        """Stop OPC UA server."""
        await self.server.stop()
        logger.info("Server OPCUA fermato")

    async def set_tag_value(self, tag_name: str, value: bool) -> None:
        """
        Imposta il valore di un tag.
        
        Args:
            tag_name: Nome del tag (InAlarm, InBypass, InCycle, InWarning)
            value: Valore booleano da impostare
        """
        if tag_name in self.tags:
            await self.tags[tag_name].write_value(value)
        else:
            logger.warning(f"Tag '{tag_name}' non trovato")

    async def get_tag_value(self, tag_name: str) -> bool:
        """
        Legge il valore di un tag.
        
        Args:
            tag_name: Nome del tag (InAlarm, InBypass, InCycle, InWarning)
            
        Returns:
            Valore booleano del tag
        """
        if tag_name in self.tags:
            return await self.tags[tag_name].read_value()
        else:
            logger.warning(f"Tag '{tag_name}' non trovato")
            return None

    async def print_tag_status(self) -> None:
        """Stampa lo stato attuale di tutti i tag."""
        for tag_name in self.tags.keys():
            value = await self.get_tag_value(tag_name)
            print(f"\t{tag_name}: {value}\t", end=" | ")
        print()
