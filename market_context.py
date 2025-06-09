# market_context.py
# Version: 1.2 | Consolidated time context + combined economic + earnings news sync for ES futures bot
# Includes permanent Finnhub API token integration

import asyncio
import datetime
import logging
from typing import List, Optional
from zoneinfo import ZoneInfo  # Python 3.9+
import aiohttp

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

class NewsEvent:
    def __init__(self, title: str, timestamp_utc: datetime.datetime, impact: str):
        self.title = title
        self.timestamp_utc = timestamp_utc
        self.impact = impact  # e.g. "high", "medium", "low"

    def __repr__(self):
        return f"<NewsEvent {self.title} at {self.timestamp_utc.isoformat()} impact={self.impact}>"

class MarketContext:
    """
    Combines session time windows and economic/earnings news sync.
    Provides API for bot to query market context for trade decisions.
    """

    def __init__(self, news_api_token: Optional[str] = None):
        self.current_time_et: datetime.datetime = datetime.datetime.now(tz=ET)
        self.news_events: List[NewsEvent] = []
        self.news_fetch_interval_sec = 300  # 5 minutes
        # Finnhub API token now loaded from config.py in gui_main
        self.news_api_token = news_api_token # This will be set by gui_main after init

        self.sessions = {
            "pre_market":   (datetime.time(4, 0),  datetime.time(9, 29, 59)),
            "regular":      (datetime.time(9, 30), datetime.time(16, 0)),
            "post_market":  (datetime.time(16, 0, 1), datetime.time(20, 0)),
            "closed":       (datetime.time(20, 0, 1), datetime.time(23, 59, 59)),
        }

        self.intraday_segments = {
            "morning": (datetime.time(9, 30), datetime.time(11, 30)),
            "lunch":   (datetime.time(11, 30), datetime.time(13, 30)),
            "afternoon": (datetime.time(13, 30), datetime.time(16, 0)),
        }

        self.news_impact_before = datetime.timedelta(minutes=15)
        self.news_impact_after = datetime.timedelta(minutes=15)

        self.chop_start = datetime.time(8, 30)  # ET, before market open, example
        self.chop_end = datetime.time(9, 15)    # ET, example

    def update_current_time(self, now: Optional[datetime.datetime] = None):
        self.current_time_et = now.astimezone(ET) if now else datetime.datetime.now(tz=ET)
        logger.debug(f"Updated current ET time to {self.current_time_et.isoformat()}")

    def is_session_open(self, session_name: str) -> bool:
        if session_name not in self.sessions:
            logger.warning(f"Unknown session_name requested: {session_name}")
            return False
        start, end = self.sessions[session_name]
        now_t = self.current_time_et.time()
        if start <= end:
            return start <= now_t <= end
        else:
            return now_t >= start or now_t <= end

    def get_current_session(self) -> str:
        for session_name, (start, end) in self.sessions.items():
            if self.is_session_open(session_name):
                return session_name
        return "closed"

    def is_intraday_segment(self, segment_name: str) -> bool:
        if segment_name not in self.intraday_segments:
            return False
        start, end = self.intraday_segments[segment_name]
        now_t = self.current_time_et.time()
        return start <= now_t <= end

    def is_chop_now(self) -> bool:
        now_t = self.current_time_et.time()
        # Consider regular trading hours only, for simplicity in this example
        # You might want to define chop zones relative to current session
        regular_session_start, regular_session_end = self.sessions.get("regular", (None, None))
        if not regular_session_start or not regular_session_end:
            return False # No regular session defined

        if self.is_session_open("regular"):
            return self.chop_start <= now_t <= self.chop_end
        return False

    def should_suppress_trades(self) -> bool:
        if self.is_chop_now():
            logger.debug("Trade suppression active due to chop zone.")
            return True
        if self.is_news_active():
            logger.debug("Trade suppression active due to news event.")
            return True
        return False

    def is_news_active(self) -> bool:
        now_utc = self.current_time_et.astimezone(datetime.timezone.utc)
        for event in self.news_events:
            start_impact = event.timestamp_utc - self.news_impact_before
            end_impact = event.timestamp_utc + self.news_impact_after
            # IMPORTANT: is_news_active currently only triggers for "high" impact.
            # If you want earnings to trigger, change 'impact="medium"' to 'impact="high"'
            # in the earnings parsing section of fetch_news_events below.
            if start_impact <= now_utc <= end_impact and event.impact == "high":
                return True
        return False

    def get_time_to_next_event(self) -> Optional[datetime.timedelta]:
        now_utc = self.current_time_et.astimezone(datetime.timezone.utc)
        future_events = [e for e in self.news_events if e.timestamp_utc > now_utc and e.impact == "high"] # Only show high impact events
        if not future_events:
            return None
        next_event = min(future_events, key=lambda e: e.timestamp_utc)
        return next_event.timestamp_utc - now_utc

    async def fetch_news_events(self):
        if not self.news_api_token:
            logger.warning("No news API token provided for MarketContext, skipping news fetch.")
            return

        try:
            async with aiohttp.ClientSession() as session:
                econ_url = f"https://finnhub.io/api/v1/calendar/economic?token={self.news_api_token}"
                async with session.get(econ_url) as resp_econ:
                    if resp_econ.status == 403:
                        logger.error(f"Finnhub API Error: Economic calendar fetch failed with status 403 (Forbidden). Check your API key or subscription plan.")
                        self.news_api_token = None # Invalidate token to stop future attempts
                        return
                    if resp_econ.status != 200:
                        logger.warning(f"Economic calendar fetch failed with status {resp_econ.status}. Response: {await resp_econ.text()}")
                        return
                    econ_data = await resp_econ.json()

                events = []
                for item in econ_data.get("economicCalendar", []):
                    impact = item.get("impact", "").lower()
                    if impact != "high":
                        continue
                    date_str = item.get("date")
                    time_str = item.get("time", "00:00")
                    # Handle cases where time might be missing or 'No Time'
                    if time_str == 'No Time' or not time_str:
                        dt_str = f"{date_str} 00:00" # Default to midnight if no time
                    else:
                        dt_str = f"{date_str} {time_str}"
                    
                    try:
                        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                        title = item.get("event", "Unknown Event")
                        events.append(NewsEvent(title=f"Economic: {title}", timestamp_utc=dt, impact=impact))
                    except ValueError as ve:
                        logger.warning(f"Failed to parse datetime for economic event: {item}. Error: {ve}")
                        continue

                today = datetime.datetime.now(tz=ET).date()
                from_date = today.isoformat()
                to_date = (today + datetime.timedelta(days=7)).isoformat()
                earn_url = (f"https://finnhub.io/api/v1/calendar/earnings?"
                            f"from={from_date}&to={to_date}&token={self.news_api_token}")
                async with session.get(earn_url) as resp_earn:
                    if resp_earn.status == 403:
                        logger.error(f"Finnhub API Error: Earnings calendar fetch failed with status 403 (Forbidden). Check your API key or subscription plan.")
                        self.news_api_token = None # Invalidate token
                        return
                    if resp_earn.status != 200:
                        logger.warning(f"Earnings calendar fetch failed with status {resp_earn.status}. Response: {await resp_earn.text()}")
                        return
                    earn_data = await resp_earn.json()

                for item in earn_data.get("earningsCalendar", []):
                    symbol = item.get("symbol")
                    date_str = item.get("date")
                    try:
                        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                        dt = dt.replace(hour=9, minute=30, tzinfo=ET).astimezone(datetime.timezone.utc) # 9:30 AM ET converted to UTC
                        title = f"Earnings: {symbol}"
                        events.append(NewsEvent(title=title, timestamp_utc=dt, impact="medium")) # Keep earnings as medium impact
                    except ValueError as ve:
                        logger.warning(f"Failed to parse datetime for earnings event: {item}. Error: {ve}")
                        continue

                events.sort(key=lambda e: e.timestamp_utc)
                self.news_events = events
                logger.info(f"Fetched {len(events)} total news and earnings events.")

        except Exception as e:
            logger.error(f"Exception during combined news fetch: {e}")

    async def periodic_news_sync(self): # <--- This method *is* here
        while True:
            await self.fetch_news_events()
            await asyncio.sleep(self.news_fetch_interval_sec)

# Example usage snippet for integration:

async def example_usage():
    # Example for standalone testing (not used in main app)
    import config
    context = MarketContext(news_api_token=config.FINNHUB_API_KEY)

    asyncio.create_task(context.periodic_news_sync())

    while True:
        context.update_current_time()
        print("Current session:", context.get_current_session())
        print("In chop zone?", context.is_chop_now())
        print("News active?", context.is_news_active())
        print("Should suppress trades?", context.should_suppress_trades())
        tte = context.get_time_to_next_event()
        print("Time to next news event:", tte)
        await asyncio.sleep(60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage())