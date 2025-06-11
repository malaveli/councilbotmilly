# Council Bot Milly

A minimal example trading bot for the TopstepX platform.

## Requirements
- Python 3.12
- See `requirements.txt` for libraries

## Usage
1. Install dependencies with `pip install -r requirements.txt`.
2. Export your API key as `TOPSTEP_API_KEY`.
3. Run the entry point:
   ```bash
   python main.py
   ```
The bot authenticates, connects to the market WebSocket and logs trade alerts.
It now includes a simple "Mentalist" strategy using a decision tree for trade
qualification.
