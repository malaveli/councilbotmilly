import asyncio
import logging
from typing import Callable, Any
from signalrcore.hub_connection_builder import HubConnectionBuilder


class TopstepDataFeed:
    """Simple wrapper around TopstepX SignalR market hub."""

    def __init__(self, token_provider: Callable[[], str]) -> None:
        self._token_provider = token_provider
        self._hub = None
        self.log = logging.getLogger(self.__class__.__name__)

    async def connect(self) -> None:
        token = self._token_provider()
        if not token:
            self.log.error("No authentication token available for data feed")
            return
        url = f"wss://rtc.topstepx.com/hubs/market?access_token={token}"
        self._hub = HubConnectionBuilder().with_url(url).build()
        self._hub.on_open(lambda: self.log.info("WebSocket opened"))
        self._hub.on_close(lambda: self.log.info("WebSocket closed"))
        self._hub.on_error(lambda data: self.log.error(f"WebSocket error: {data}"))
        await asyncio.get_event_loop().run_in_executor(None, self._hub.start)

    def subscribe_quotes(self, contract_id: str) -> None:
        if self._hub:
            self._hub.send("SubscribeContractQuotes", [contract_id])

    def add_handler(self, method: str, handler: Callable[[Any], None]) -> None:
        if self._hub:
            self._hub.on(method, handler)

    def stop(self) -> None:
        if self._hub:
            self._hub.stop()
