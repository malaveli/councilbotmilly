// nodejs_bridge/signalr_bridge.js
const signalR = require("@microsoft/signalr");
const axios = require("axios");
const util = require('util');
const express = require('express');

// --- Configuration Constants (These should match your config.py) ---
// Note: These are hardcoded here for clarity and to avoid issues with argument parsing IF Python's values are consistent.
// If Python is launching with correct args, these are redundant, but helpful for debugging what the Node.js side expects.
const DEFAULT_MARKET_HUB_URL = "wss://rtc.topstepx.com/hubs/market"; // Ensure this matches config.py
const DEFAULT_USER_HUB_URL = "wss://rtc.topstepx.com/hubs/user";     // Ensure this matches config.py
const DEFAULT_API_BASE_URL = "https://api.topstepx.com";
const DEFAULT_CONTRACT_ID = "CON.F.US.EP.M25";

// Arguments passed from Python (These will override the defaults if present)
const authToken = process.argv[2];
// Use the arguments from Python, falling back to defaults if not provided or empty
const apiBaseUrl = process.argv[3] || DEFAULT_API_BASE_URL;
const marketHubUrl = process.argv[4] || DEFAULT_MARKET_HUB_URL;
const userHubUrl = process.argv[5] || DEFAULT_USER_HUB_URL;
const defaultContractId = process.argv[6] || DEFAULT_CONTRACT_ID;

let currentAccountId = null;
let subscribedAccountId = null;

const pythonFlaskUrl = "http://localhost:5000/data_stream";
const nodeBridgePort = 5001;

const signalrLogLevel = signalR.LogLevel.Information; // Adjust to Debug or Trace for more verbose logs

console.log("--- Node.js SignalR Bridge Starting ---");
console.log(`Node.js Bridge received token: ${authToken ? "YES" : "NO"}`);
console.log(`Market Hub URL (Effective): ${marketHubUrl}`); // Log the effective URL being used
console.log(`User Hub URL (Effective): ${userHubUrl}`);     // Log the effective URL being used
console.log(`Default Contract: ${defaultContractId}`);
console.log(`Python Flask URL (outgoing): ${pythonFlaskUrl}`);
console.log(`Node.js Bridge API Port (incoming from Python): ${nodeBridgePort}`);
console.log("---------------------------------------");

if (!authToken) {
    console.error("ERROR: No auth token provided. Bridge cannot connect to SignalR hubs.");
    process.exit(1);
}
if (!marketHubUrl || !userHubUrl || !defaultContractId) {
    console.error("ERROR: Missing essential configuration (Hub URLs or Contract ID). Please check arguments or defaults.");
    process.exit(1);
}

// --- SignalR Connections ---
let marketHubConnection = null;
let userHubConnection = null;
let reconnectAttemptCount = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_INTERVAL_MS = 5000;

async function connectToHub(hubName, url, onOpenCallback, onReceiveDataCallbacks) {
    const connection = new signalR.HubConnectionBuilder()
        .withUrl(url, {
            accessTokenFactory: () => authToken,
            skipNegotiation: true,
            transport: signalR.HttpTransportType.WebSockets
        })
        .withAutomaticReconnect({
            nextRetryDelayInMilliseconds: retryContext => {
                reconnectAttemptCount++;
                console.warn(`${hubName} Connection lost. Reconnecting attempt ${reconnectAttemptCount}/${MAX_RECONNECT_ATTEMPTS}...`);
                if (reconnectAttemptCount > MAX_RECONNECT_ATTEMPTS) {
                    console.error(`${hubName} Max reconnect attempts reached. Giving up.`);
                    return null;
                }
                return RECONNECT_INTERVAL_MS;
            }
        })
        .configureLogging(signalrLogLevel)
        .build();

    connection.onreconnected(() => {
        console.log(`${hubName} Connection reestablished.`);
        reconnectAttemptCount = 0;
        if (hubName === "Market Hub") {
            subscribeToMarketData(connection, defaultContractId);
        } else if (hubName === "User Hub" && currentAccountId) {
            subscribeToUserData(connection, currentAccountId);
        }
    });

    connection.onclose(error => {
        if (error) {
            console.error(`${hubName} Connection closed with error: ${error.message}`);
        } else {
            console.log(`${hubName} Connection closed cleanly.`);
        }
    });

    for (const eventName in onReceiveDataCallbacks) {
        connection.on(eventName, data => onReceiveDataCallbacks[eventName](data));
    }

    try {
        await connection.start();
        console.log(`${hubName} Connection started.`);
        onOpenCallback(connection);
        return connection;
    } catch (err) {
        console.error(`Error connecting to ${hubName}: ${err.message}`);
        return null;
    }
}

// --- Data Forwarding to Python ---
async function sendToPython(dataType, payload) {
    try {
        await axios.post(pythonFlaskUrl, {
            type: dataType,
            payload: payload
        });
    } catch (error) {
        if (error.code === 'ECONNREFUSED') {
            // console.warn("Could not connect to Python Flask server. Is it running?");
        } else {
            console.error(`Error sending ${dataType} to Python: ${error.message} - ${util.inspect(error.response ? error.response.data : error.message)}`);
        }
    }
}

// --- Market Hub Callbacks & Subscriptions ---
function onMarketHubOpen(connection) {
    console.log("Market Hub: Subscribing to contract data...");
    subscribeToMarketData(connection, defaultContractId);
}

function subscribeToMarketData(connection, contractId) {
    if (connection.state === signalR.HubConnectionState.Connected) {
        connection.send("SubscribeContractTrades", contractId)
            .then(() => console.log(`Subscribed to GatewayTrade for ${contractId}`))
            .catch(err => console.error(`Error subscribing to GatewayTrade: ${err.message}`));

        connection.send("SubscribeContractQuotes", contractId)
            .then(() => console.log(`Subscribed to GatewayQuote for ${contractId}`))
            .catch(err => console.error(`Error subscribing to GatewayQuote: ${err.message}`));

        connection.send("SubscribeContractMarketDepth", contractId)
            .then(() => console.log(`Subscribed to GatewayDepth for ${contractId}`))
            .catch(err => console.error(`Error subscribing to GatewayDepth: ${err.message}. (Expected if not supported).`));
    } else {
        console.warn("Market Hub not connected. Cannot subscribe to market data yet.");
    }
}

const marketHubDataCallbacks = {
    "GatewayTrade": data => sendToPython("trade", data),
    "GatewayQuote": data => sendToPython("quote", data),
    "GatewayDepth": data => sendToPython("depth", data)
};


// --- User Hub Callbacks & Subscriptions ---
function onUserHubOpen(connection) {
    console.log("User Hub: Subscribing to general user data (GatewayUserAccount)...");
    connection.send("SubscribeAccounts")
        .then(() => console.log(`Subscribed to GatewayUserAccount`))
        .catch(err => console.error(`Error subscribing to GatewayUserAccount: ${err.message}`));

    if (currentAccountId) {
        console.log("User Hub: Account ID already known, subscribing to specific user data.");
        subscribeToUserData(connection, currentAccountId);
    } else {
        console.warn("User Hub: Account ID not yet known. Specific user subscriptions (Orders, Positions, Trades) will be delayed.");
    }
}

function subscribeToUserData(connection, accountIdToSubscribe) {
    if (connection.state === signalR.HubConnectionState.Connected && accountIdToSubscribe) {
        if (subscribedAccountId && subscribedAccountId !== accountIdToSubscribe) {
            console.log(`User Hub: Unsubscribing from old account ID ${subscribedAccountId} for specific data.`);
            connection.send("UnsubscribeOrders", subscribedAccountId).catch(e => console.error(`Unsub failed for orders: ${e.message}`));
            connection.send("UnsubscribePositions", subscribedAccountId).catch(e => console.error(`Unsub failed for positions: ${e.message}`));
            connection.send("UnsubscribeTrades", subscribedAccountId).catch(e => console.error(`Unsub failed for trades: ${e.message}`));
        }

        console.log(`User Hub: Attempting to subscribe to specific user data for Account ID: ${accountIdToSubscribe}`);
        connection.send("SubscribeOrders", accountIdToSubscribe)
            .then(() => console.log(`Subscribed to GatewayUserOrder for ${accountIdToSubscribe}`))
            .catch(err => console.error(`Error subscribing to GatewayUserOrder: ${err.message}`));

        connection.send("SubscribePositions", accountIdToSubscribe)
            .then(() => console.log(`Subscribed to GatewayUserPosition for ${accountIdToSubscribe}`))
            .catch(err => console.error(`Error subscribing to GatewayUserPosition: ${err.message}`));

        connection.send("SubscribeTrades", accountIdToSubscribe)
            .then(() => console.log(`Subscribed to GatewayUserTrade for ${accountIdToSubscribe}`))
            .catch(err => console.error(`Error subscribing to GatewayUserTrade: ${err.message}`));
        
        subscribedAccountId = accountIdToSubscribe;
    } else {
        console.warn("User Hub: Cannot subscribe to specific user data without accountId or if not connected.");
    }
}

const userHubDataCallbacks = {
    "GatewayUserAccount": data => sendToPython("account", data),
    "GatewayUserOrder": data => sendToPython("order", data),
    "GatewayUserPosition": data => sendToPython("position", data),
    "GatewayUserTrade": data => sendToPython("user_trade", data)
};


// --- Node.js Local API to receive accountId from Python ---
const app = express();
app.use(express.json());

app.post('/set_account_id', (req, res) => {
    const { accountId } = req.body;
    if (accountId) {
        if (currentAccountId !== accountId) {
            currentAccountId = accountId;
            console.log(`Node.js Bridge: Received accountId: ${accountId} from Python. Attempting specific user subscriptions.`);
            if (userHubConnection && userHubConnection.state === signalR.HubConnectionState.Connected) {
                subscribeToUserData(userHubConnection, accountId);
            } else {
                console.warn("Node.js Bridge: User Hub not connected or accountId received too early. Subscriptions will occur on reconnect.");
            }
        } else {
            console.log(`Node.js Bridge: Received accountId: ${accountId} from Python (already known).`);
        }
        res.json({ status: "success", message: `Account ID ${accountId} received.` });
    } else {
        res.status(400).json({ status: "error", message: "Account ID not provided." });
    }
});

// Start Node.js local API server
app.listen(nodeBridgePort, () => {
    console.log(`Node.js Bridge local API listening on port ${nodeBridgePort}`);
});


// --- Main Execution ---
async function main() {
    marketHubConnection = await connectToHub(
        "Market Hub",
        `${marketHubUrl}?access_token=${authToken}`, // Market Hub URL includes token directly
        onMarketHubOpen,
        marketHubDataCallbacks
    );

    userHubConnection = await connectToHub(
        "User Hub",
        `${userHubUrl}?access_token=${authToken}`, // User Hub URL includes token directly
        onUserHubOpen,
        userHubDataCallbacks
    );
}

main();

// Handle graceful shutdown
process.on('SIGINT', async () => {
    console.log('SIGINT received. Stopping SignalR connections...');
    if (marketHubConnection) {
        await marketHubConnection.stop();
    }
    if (userHubConnection) {
        await userHubConnection.stop();
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('SIGTERM received. Stopping SignalR connections...');
    if (marketHubConnection) {
        await marketHubConnection.stop();
    }
    if (userHubConnection) {
        await userHubConnection.stop();
    }
    process.exit(0);
});