import aiohttp
from typing import Optional

class AsyncMesAPIClient:

    def __init__(self, base_url: str = "http://api.mes.com/current-fase?prod_line="):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None


    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self


    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()


    async def get_current_fase_id(self, prod_line: str) -> Optional[int]:
        if not self.session:
            raise RuntimeError("HTTP Session uninitialized. Use 'async with'.")

        url = f"{self.base_url}/{prod_line}"

        try:
            async with self.session.get(url, timeout=5.0) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("fase_id")
            
        except Exception as e:
            raise RuntimeError(f'Could not retrieve current fase ID: {e}')