import asyncio
import aiohttp
import json
import logging

# Configure basic logging to see script output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION (REPLACE THESE WITH YOUR ACTUAL CREDENTIALS) ---
YOUR_USERNAME = "millycapital" # Use your TopstepX username
YOUR_API_KEY = "c9eQD3mU4Ke6ntl8Lije1+sXR8lA0Nxhft0QV9FiONU=" # <--- REPLACE THIS
API_BASE_URL = "https://api.topstepx.com"
# -----------------------------------------------------------------

async def fetch_account_data_and_token():
    # Step 1: Get an access token
    auth_url = f"{API_BASE_URL}/api/Auth/loginKey"
    auth_payload = {
        "userName": YOUR_USERNAME,
        "apiKey": YOUR_API_KEY
    }
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            logger.info("Attempting to get access token...")
            async with session.post(auth_url, headers=headers, json=auth_payload) as response:
                response.raise_for_status() # Raise an exception for bad status codes
                auth_data = await response.json()
                access_token = auth_data.get("token")

                if not access_token:
                    logger.error(f"Failed to get access token: No 'token' found in response: {auth_data}")
                    return

                logger.info("Access token obtained successfully. Proceeding to fetch account data.")

                # Step 2: Search for accounts using the obtained token
                account_search_url = f"{API_BASE_URL}/api/Account/search"
                account_search_payload = {
                    "onlyActiveAccounts": True
                }
                account_headers = {
                    "accept": "application/json",
                    "Authorization": f"Bearer {access_token}", # Use the token here
                    "Content-Type": "application/json"
                }

                logger.info("Attempting to search for active accounts...")
                async with session.post(account_search_url, headers=account_headers, json=account_search_payload) as account_response:
                    account_response.raise_for_status()
                    account_data = await account_response.json()

                    logger.info("--- RAW ACCOUNT SEARCH RESPONSE ---")
                    print(json.dumps(account_data, indent=4)) # Pretty print the JSON response
                    logger.info("-----------------------------------")

                    accounts = account_data.get("accounts", [])
                    if accounts:
                        first_account = accounts[0]
                        logger.info(f"First active account details: {first_account}")
                        
                        # We are looking for the key that holds the account ID.
                        # Common possibilities are 'accountId', 'id', 'accountID'.
                        # This script will help you see which one it is.
                        if "accountId" in first_account:
                            logger.info(f"Found 'accountId': {first_account['accountId']}")
                        elif "id" in first_account:
                            logger.info(f"Found 'id': {first_account['id']}")
                        elif "accountID" in first_account:
                            logger.info(f"Found 'accountID': {first_account['accountID']}")
                        else:
                            logger.warning("No common account ID key ('accountId', 'id', 'accountID') found in the first account object. Please inspect the RAW JSON response above carefully to find the correct key.")
                    else:
                        logger.warning("No active accounts found in the response.")

    except aiohttp.ClientResponseError as e:
        logger.error(f"HTTP Error: {e.status} - {e.message}. Response: {await e.response.text()}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(fetch_account_data_and_token())