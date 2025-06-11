# auth_handler.py
import asyncio
import aiohttp
import logging
from typing import Optional, Callable
from config import API_BASE_URL, USERNAME
import time
import jwt # NEW: Import PyJWT

logger = logging.getLogger(__name__)

class AuthHandler:
    """
    Handles authentication with the TopstepX API to obtain an access token.
    This version attempts to use the /api/Auth/loginKey endpoint as per the cheat sheet.
    """
    def __init__(self, api_base_url: str = API_BASE_URL, username: str = USERNAME):
        self.access_token: Optional[str] = None
        self.expires_in: int = 0 # seconds
        self.last_auth_time: Optional[float] = None # time.time() or asyncio.get_event_loop().time()
        self.api_base_url = api_base_url
        self.username = username

    async def authenticate_async(self, api_key: str) -> bool:
        """Authenticates with TopstepX API asynchronously and fetches a JWT token."""
        try:
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json"
            }
            payload = {
                "userName": self.username,
                "apiKey": api_key
            }
            url = f"{self.api_base_url}/api/Auth/loginKey"

            logger.info(f"Attempting authentication for {self.username} using {url}...")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    data = await response.json()

                    self.access_token = data.get("token")

                    if self.access_token:
                        try:
                            # NEW: Decode JWT token to get actual expiration time
                            # We don't verify signature here as we're just reading claims
                            decoded_token = jwt.decode(self.access_token, options={"verify_signature": False})
                            # 'exp' is the expiration time as a Unix timestamp
                            token_expiry_timestamp = decoded_token.get("exp")
                            if token_expiry_timestamp:
                                self.expires_in = token_expiry_timestamp - time.time() # Remaining seconds
                                if self.expires_in < 0: # Token already expired
                                    self.expires_in = 0
                                    logger.warning("Authentication successful, but token is already expired. Re-authenticate immediately.")
                                self.last_auth_time = asyncio.get_event_loop().time() # Record time of token acquisition
                                logger.info(f"Authentication successful. Token expires in {int(self.expires_in)} seconds.")
                                return True
                            else:
                                logger.error(f"Authentication failed: 'exp' claim missing in JWT token: {decoded_token}")
                                self.access_token = None
                                return False
                        except jwt.exceptions.DecodeError as e:
                            logger.error(f"Authentication failed: Error decoding JWT token: {e}")
                            self.access_token = None
                            return False
                    else:
                        logger.error(f"Authentication failed: No 'token' found in response: {data}")
                        return False

        except aiohttp.ClientResponseError as e:
            logger.error(f"Authentication failed: HTTP Error {e.status} - {e.message} for URL {e.request_info.url}. Response body: {await e.response.text()}")
            return False
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def authenticate(self, api_key: str) -> bool:
        """
        Synchronous wrapper for GUI: runs the async authentication.
        This allows the GUI to call it directly without needing an async context.
        Note: This method is primarily kept for compatibility or direct synchronous calls
        if the UI did not use Q_ARG(bool, success), Q_ARG(str, api_key) with a Slot.
        In your current gui_main.py, the _perform_auth_async directly calls authenticate_async.
        """
        try:
            # Try to get existing loop, create a new one if not available
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.authenticate_async(api_key))

    def get_access_token(self) -> Optional[str]:
        """Returns the current access token if it's still valid."""
        if self.access_token and self.last_auth_time:
            try:
                current_time = asyncio.get_event_loop().time()
            except RuntimeError:
                current_time = time.time()
            
            if current_time < self.last_auth_time + self.expires_in - 60: # 60 sec buffer
                return self.access_token
        return None

    async def refresh_token_if_needed(self, api_key: str):
        """
        Placeholder for token refresh logic. In a real app, you'd use a refresh token
        instead of re-authentuating with the API key.
        """
        if not self.get_access_token(): # If token is expired or missing
            logger.info("Access token expired or missing, attempting re-authentication...")
            await self.authenticate_async(api_key)
