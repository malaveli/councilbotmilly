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
        """Connect to the TopstepX market hub."""
        token = self._token_provider()
        if not token:
            self.log.error("No authentication token available for data feed")
            return

        url = f"wss://rtc.topstepx.com/hubs/market?access_token={token}"
        self._hub = HubConnectionBuilder().with_url(url).build()
        self._hub.on_open(lambda: self.log.info("WebSocket opened"))
        self._hub.on_close(lambda: self.log.info("WebSocket closed"))
        self._hub.on_error(lambda data: self.log.error(f"WebSocket error: {data}"))

        try:
            await asyncio.get_event_loop().run_in_executor(None, self._hub.start)
        except Exception as exc:  # pragma: no cover - network errors not under test
            self.log.exception("Failed to start WebSocket connection: %s", exc)

    def subscribe_quotes(self, contract_id: str) -> None:
        """Subscribe to quote updates for the given contract."""
        if not self._hub:
            self.log.error("WebSocket not connected; cannot subscribe to quotes")
            return
        try:
            self._hub.send("SubscribeContractQuotes", [contract_id])
        except Exception as exc:  # pragma: no cover - send may fail if hub closed
            self.log.exception("Failed to subscribe to %s: %s", contract_id, exc)

    def add_handler(self, method: str, handler: Callable[[Any], None]) -> None:
        """Register a handler for a SignalR method."""
        if not self._hub:
            self.log.error("WebSocket not connected; cannot add handler %s", method)
            return
        self._hub.on(method, handler)

    def stop(self) -> None:
        """Stop the data feed connection."""
        if self._hub:
            try:
                self._hub.stop()
            except Exception as exc:  # pragma: no cover
                self.log.exception("Error stopping WebSocket: %s", exc)
