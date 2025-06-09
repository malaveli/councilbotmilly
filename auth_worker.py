# auth_worker.py

from PySide6.QtCore import QObject, Signal
import requests
import logging

logger = logging.getLogger(__name__)

class AuthWorker(QObject):
    # Signals to communicate results back to the main thread
    finished = Signal(bool, str, object) # success, message, raw_data_or_error
    diagnostics_log_signal = Signal(str) # NEW: Signal for logging from worker thread

    def __init__(self, auth_url, username, api_key):
        super().__init__()
        self.auth_url = auth_url
        self.username = username
        self.api_key = api_key

    def run(self):
        """
        Performs the synchronous authentication request.
        This runs within the separate QThread.
        """
        self.diagnostics_log_signal.emit(f"AuthWorker: Starting authentication for {self.username}...")
        logger.info(f"AuthWorker: Starting authentication for {self.username}...")
        try:
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json"
            }
            payload = {
                "userName": self.username,
                "apiKey": self.api_key
            }

            # Use requests.post here, which is synchronous and will block this worker thread.
            # This is correct as this worker runs in a dedicated QThread separate from the GUI.
            response = requests.post(self.auth_url, headers=headers, json=payload, timeout=10) # Added timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            data = response.json()
            
            token = data.get("token")
            if token:
                self.diagnostics_log_signal.emit("AuthWorker: Authentication successful.")
                logger.info("AuthWorker: Authentication successful.")
                self.finished.emit(True, "Authentication successful.", data)
            else:
                self.diagnostics_log_signal.emit(f"AuthWorker: Authentication failed: No token found in response: {data}")
                logger.warning(f"AuthWorker: Authentication failed: No token found in response: {data}")
                self.finished.emit(False, f"Authentication failed: No token received.", data)

        except requests.exceptions.HTTPError as e:
            error_msg = f"AuthWorker: HTTP Error {e.response.status_code} - {e.response.text}"
            self.diagnostics_log_signal.emit(error_msg)
            logger.error(error_msg)
            self.finished.emit(False, f"Authentication failed: {error_msg}", {"error_details": e.response.text})
        except requests.exceptions.ConnectionError as e:
            error_msg = f"AuthWorker: Connection Error: {e}"
            self.diagnostics_log_signal.emit(error_msg)
            logger.error(error_msg)
            self.finished.emit(False, f"Authentication failed: {error_msg}", {"error_details": str(e)})
        except requests.exceptions.Timeout as e:
            error_msg = f"AuthWorker: Timeout Error: {e}"
            self.diagnostics_log_signal.emit(error_msg)
            logger.error(error_msg)
            self.finished.emit(False, f"Authentication failed: {error_msg}", {"error_details": str(e)})
        except requests.exceptions.RequestException as e:
            error_msg = f"AuthWorker: Request Error: {e}"
            self.diagnostics_log_signal.emit(error_msg)
            logger.error(error_msg)
            self.finished.emit(False, f"Authentication failed: {error_msg}", {"error_details": str(e)})
        except Exception as e:
            error_msg = f"AuthWorker: Unexpected Error: {e}"
            self.diagnostics_log_signal.emit(error_msg)
            logger.exception(error_msg)
            self.finished.emit(False, f"Authentication failed: {error_msg}", {"error_details": str(e)})