# flask_data_receiver.py
from flask import Flask, request, jsonify
from PySide6.QtCore import Signal, QObject, QMetaObject, Qt
import logging

logger = logging.getLogger(__name__)

# This QObject acts as a bridge to emit signals safely from Flask's thread to the GUI thread
class FlaskSignalEmitter(QObject):
    # Signals for different data types
    market_trade_signal = Signal(object)
    market_quote_signal = Signal(object)
    market_depth_signal = Signal(object)
    user_account_signal = Signal(object)
    user_order_signal = Signal(object)
    user_position_signal = Signal(object)
    user_trade_signal = Signal(object)
    diagnostics_log_signal = Signal(str) # For logging from Flask thread

    def __init__(self, parent=None):
        super().__init__(parent)

# Create a Flask app instance
app = Flask(__name__)

# This will hold the single instance of our QObject signal emitter
# It will be set by gui_main.py after the GUI object is created
signal_emitter_instance = None

def set_signal_emitter(emitter):
    global signal_emitter_instance
    signal_emitter_instance = emitter

@app.route('/data_stream', methods=['POST'])
def receive_data():
    if not signal_emitter_instance:
        logger.error("FlaskDataReceiver: Signal emitter not set up. Cannot process data.")
        return jsonify({"status": "error", "message": "Signal emitter not initialized"}), 500

    try:
        data = request.json
        data_type = data.get('type')
        payload = data.get('payload')

        # Log received data for debugging
        logger.debug(f"FlaskDataReceiver: Received data_type={data_type}, payload={payload}")
        signal_emitter_instance.diagnostics_log_signal.emit(f"Bridge Data: {data_type} received.")

        # Emit the appropriate PySide6 signal on the GUI thread
        # QMetaObject.invokeMethod is used for thread-safe signal emission
        if data_type == "trade":
            QMetaObject.invokeMethod(signal_emitter_instance, "market_trade_signal",
                                     Qt.QueuedConnection, Q_ARG(object, [None, payload]))
        elif data_type == "quote":
            QMetaObject.invokeMethod(signal_emitter_instance, "market_quote_signal",
                                     Qt.QueuedConnection, Q_ARG(object, [None, payload]))
        elif data_type == "depth":
            QMetaObject.invokeMethod(signal_emitter_instance, "market_depth_signal",
                                     Qt.QueuedConnection, Q_ARG(object, [None, payload]))
        elif data_type == "account":
            QMetaObject.invokeMethod(signal_emitter_instance, "user_account_signal",
                                     Qt.QueuedConnection, Q_ARG(object, [None, payload]))
        elif data_type == "order":
            QMetaObject.invokeMethod(signal_emitter_instance, "user_order_signal",
                                     Qt.QueuedConnection, Q_ARG(object, [None, payload]))
        elif data_type == "position":
            QMetaObject.invokeMethod(signal_emitter_instance, "user_position_signal",
                                     Qt.QueuedConnection, Q_ARG(object, [None, payload]))
        elif data_type == "user_trade":
            QMetaObject.invokeMethod(signal_emitter_instance, "user_trade_signal",
                                     Qt.QueuedConnection, Q_ARG(object, [None, payload]))
        else:
            logger.warning(f"FlaskDataReceiver: Unhandled data type: {data_type}")
            signal_emitter_instance.diagnostics_log_signal.emit(f"Bridge Data: Unhandled type {data_type}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.exception("FlaskDataReceiver: Error processing incoming data.")
        if signal_emitter_instance:
            signal_emitter_instance.diagnostics_log_signal.emit(f"Bridge Data Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_flask_app():
    # Make sure Flask listens on 0.0.0.0 to be accessible from Node.js (even on same machine)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False) # Use reloader=False for threading