"""MES API client module.

Provides an asynchronous interface for interacting with the Manufacturing
Execution System (MES) API and retrieving real-time production data such as
active work orders for specific production lines.
"""

import aiohttp
from typing import Optional, Type
from types import TracebackType

class AsyncMesAPIClient:
    """
    Asynchronous client for Manufacturing Execution System API interactions.
    
    Manages HTTP session lifecycle and provides methods to retrieve production
    line work order data through asynchronous API requests.

    Attributes:
        base_url: The root endpoint for the MES API service.
        session: The underlying HTTP session (None until context entered).
    """

    def __init__(self, base_url: str) -> None:
        """
        Initialize the MES API client.

        Args:
            base_url: The target URL for API requests.
        
        Returns:
            None
        """
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None


    async def __aenter__(self) -> "AsyncMesAPIClient":
        """
        Enter the async context manager.
        
        Initialize the asynchronous HTTP session when entering the context.

        Returns:
            The client instance with an active session.
        """
        self.session = aiohttp.ClientSession()
        return self


    async def __aexit__(
        self, 
        exc_type: Optional[Type[BaseException]], 
        exc_val: Optional[BaseException], 
        exc_tb: Optional[TracebackType]
    ) -> None:
        """
        Exit the async context manager.
        
        Close the asynchronous HTTP session when exiting the context.
        
        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception instance if an error occurred.
            exc_tb: Traceback if an error occurred.
        
        Returns:
            None
        """
        if self.session:
            await self.session.close()


    async def get_current_order_id(self, machine: str) -> int:
        """
        Fetch the active work order ID for a specific production machine.

        Send a GET request to the API, validate the response, and extract 
        the 'active_order_id' identifier.

        Args:
            machine (str): The identifier of the production machine.

        Returns:
            int: The current work order ID.
            
        Raises:
            RuntimeError: If the session is not initialized, the request fails,
                or the response does not contain a valid active order ID.
        """

        if not self.session:
            raise RuntimeError("HTTP Session uninitialized. Use 'async with'.")

        url = f"{self.base_url}?machine={machine}"

        try:
            async with self.session.get(url, timeout=5.0) as response:
                response.raise_for_status()
                data = await response.json()
                return int(data.get("active_order_id"))
            
        except Exception as e:
            raise RuntimeError(f'Could not retrieve current order ID: {e}')
