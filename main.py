"""Simple entrypoint for Council Bot."""
import asyncio
import logging
import os
from utils import setup_logging
from auth_handler import AuthHandler
from data_feed import TopstepDataFeed
from strategy import ICTStrategy, DeltaStrategy, MentalistStrategy, StrategyManager
from models import MarketData


async def main() -> None:
    setup_logging()
    auth = AuthHandler()
    api_key = os.environ.get("TOPSTEP_API_KEY", "YOUR_API_KEY")
    success = await auth.authenticate_async(api_key)
    if not success:
        print("Authentication failed")
        return

    feed = TopstepDataFeed(auth.get_access_token)
    try:
        await feed.connect()
    except Exception as exc:
        logging.getLogger(__name__).error("Failed to connect data feed: %s", exc)
        return

    feed.subscribe_quotes("CON.F.US.EP.M25")

    manager = StrategyManager([ICTStrategy(), DeltaStrategy(), MentalistStrategy()])

    def handle_quote(data):
        md = MarketData(
            symbol=data.get("contractId", ""),
            timestamp=data.get("timestamp", 0),
            bid=data.get("bid", 0.0),
            ask=data.get("ask", 0.0),
            last=data.get("last", 0.0),
            volume=data.get("volume", 0),
        )
        asyncio.create_task(process_market_data(manager, md))

    feed.add_handler("GatewayQuote", handle_quote)
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        feed.stop()


async def process_market_data(manager: StrategyManager, data: MarketData) -> None:
    try:
        signal = await manager.evaluate(data)
        if signal:
            logging.getLogger("trade").info(
                "Trade signal %s from %s at %s", signal.direction, signal.strategy, signal.entry_price
            )
    except Exception as exc:
        logging.getLogger(__name__).exception("Error processing market data: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())
