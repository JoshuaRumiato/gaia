"""
MES API Client Module.

Provide an asynchronous interface to interact with the Manufacturing 
Execution System (MES) and retrieve real-time production data.
"""

import aiohttp
from typing import Optional, Type
from types import TracebackType

class AsyncMesAPIClient:
    """Provide an asynchronous client to interact with the MES API.

    Handle connection lifecycle and data retrieval for production line 
    work orders using HTTP requests.

    Attributes:
        base_url (str): The root endpoint for the MES API service.
        session (Optional[aiohttp.ClientSession]): The underlying HTTP session.
    """

    def __init__(self, base_url: str = "http://mesapi.xdomain.local/GetActiveWorkOrder") -> None:
        """Initialize the client with a base URL.

        Args:
            base_url (str): The target URL for API requests.
        
        Returns:
            None
        """
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None


    async def __aenter__(self) -> "AsyncMesAPIClient":
        """Initialize the asynchronous HTTP session when entering the context.

        Returns:
            AsyncMesAPIClient: The instance with an active session.
        """
        self.session = aiohttp.ClientSession()
        return self


    async def __aexit__(
        self, 
        exc_type: Optional[Type[BaseException]], 
        exc_val: Optional[BaseException], 
        exc_tb: Optional[TracebackType]
    ) -> None:
        """Close the asynchronous HTTP session when exiting the context."""
        if self.session:
            await self.session.close()


    async def get_current_work_order_num(self, prod_line: str) -> Optional[int]:
        """
        Fetch the active work order number for a specific production line.

        Send a GET request to the API, validate the response, and extract 
         the 'WorkOrderNum' identifier.

        Args:
            prod_line (str): The name or ID of the production line.

        Returns:
            Optional[int]: The current work order number if found.

        Raises:
            RuntimeError: If the session is not initialized or the request fails.
        """

        if not self.session:
            raise RuntimeError("HTTP Session uninitialized. Use 'async with'.")

        url = f"{self.base_url}/{prod_line}"

        try:
            async with self.session.get(url, timeout=5.0) as response:
                response.raise_for_status()
                data = await response.json()
                return int(data.get("WorkOrderNum"))
            
        except Exception as e:
            raise RuntimeError(f'Could not retrieve current fase ID: {e}')
