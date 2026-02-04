/**
 * GlobalRTS Server - Minimal & Fast
 * 
 * No frameworks. Just Node.js http + ws library.
 * Connects rovers (HTTP) to GlobalRTS browsers (WebSocket).
 * 
 * Architecture:
 *   Rover (nRF9151) --HTTP POST--> Server --WebSocket--> GlobalRTS Browser
 *   Rover (nRF9151) <--HTTP GET--- Server <--WebSocket-- GlobalRTS Browser
 */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const PORT = process.env.PORT || 8080;

// ============================================
// IN-MEMORY STATE (no database needed)
// ============================================

// Current rover state - latest telemetry from each rover
// Key: roverId, Value: { id, name, type, lat, lon, alt, speed, heading, imu, encoders, lastSeen, status }
const rovers = new Map();

// Pending commands for rovers - they poll this
// Key: roverId, Value: [{ id, type, payload, timestamp }]
const pendingCommands = new Map();

// Connected GlobalRTS browser clients
const browserClients = new Set();

// Command ID counter
let commandIdCounter = 0;

// ============================================
// OURA API PROXY
// ============================================

function proxyToOura(ouraUrl, token, res) {
    console.log(`🌙 Oura proxy: ${ouraUrl}`);
    
    const options = {
        headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'application/json'
        }
    };
    
    https.get(ouraUrl, options, (ouraRes) => {
        let data = '';
        ouraRes.on('data', chunk => data += chunk);
        ouraRes.on('end', () => {
            console.log(`🌙 Oura response: ${ouraRes.statusCode}`);
            res.writeHead(ouraRes.statusCode, { 
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            });
            res.end(data);
        });
    }).on('error', (err) => {
        console.error('Oura proxy error:', err);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Failed to fetch from Oura API' }));
    });
}

// ============================================
// HTTP SERVER - Serves files + rover API
// ============================================

const MIME_TYPES = {
    '.html': 'text/html',
    '.js': 'text/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.ico': 'image/x-icon'
};

const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const pathname = url.pathname;

    // CORS headers for all responses
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    // ========== ROVER API ENDPOINTS ==========

    // POST /api/telemetry - Rover sends telemetry data
    if (req.method === 'POST' && pathname === '/api/telemetry') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                const data = JSON.parse(body);
                handleRoverTelemetry(data);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok: true }));
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid JSON' }));
            }
        });
        return;
    }

    // GET /api/commands/:roverId - Rover polls for commands
    if (req.method === 'GET' && pathname.startsWith('/api/commands/')) {
        const roverId = pathname.split('/')[3];
        const commands = pendingCommands.get(roverId) || [];
        pendingCommands.set(roverId, []); // Clear after sending
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ commands }));
        return;
    }

    // POST /api/command - Browser sends command to rover (alternative to WebSocket)
    if (req.method === 'POST' && pathname === '/api/command') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                const { roverId, type, payload } = JSON.parse(body);
                queueCommand(roverId, type, payload);
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok: true }));
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid JSON' }));
            }
        });
        return;
    }

    // GET /api/rovers - Get all rover states
    if (req.method === 'GET' && pathname === '/api/rovers') {
        const roverList = Array.from(rovers.values());
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(roverList));
        return;
    }

    // GET /api/health - Simple health check
    if (req.method === 'GET' && pathname === '/api/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ 
            status: 'ok', 
            rovers: rovers.size, 
            browsers: browserClients.size,
            uptime: process.uptime()
        }));
        return;
    }

    // ========== OURA RING API PROXY ==========
    // Proxies requests to Oura API to avoid CORS issues
    if (req.method === 'GET' && pathname.startsWith('/api/oura/')) {
        const ouraPath = pathname.replace('/api/oura', '');
        const queryString = url.search || '';
        const ouraUrl = `https://api.ouraring.com${ouraPath}${queryString}`;
        
        // Get token from CONFIG or environment
        const OURA_TOKEN = process.env.OURA_TOKEN || '527UFS4RVNQA4R72IIAGNHWMCQZ7A6EU';
        
        proxyToOura(ouraUrl, OURA_TOKEN, res);
        return;
    }

    // ========== STATIC FILE SERVING ==========
    
    let filePath = pathname === '/' ? '/globalui.html' : pathname;
    filePath = path.join(__dirname, 'public', filePath);

    const ext = path.extname(filePath);
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    fs.readFile(filePath, (err, content) => {
        if (err) {
            if (err.code === 'ENOENT') {
                res.writeHead(404);
                res.end('Not Found');
            } else {
                res.writeHead(500);
                res.end('Server Error');
            }
        } else {
            res.writeHead(200, { 'Content-Type': contentType });
            res.end(content);
        }
    });
});

// ============================================
// WEBSOCKET SERVER - Browser connections
// ============================================

const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
    console.log('🌐 Browser connected');
    browserClients.add(ws);

    // Send current rover states immediately
    ws.send(JSON.stringify({
        type: 'devices:list',
        data: Array.from(rovers.values()).map(roverToDevice)
    }));

    ws.on('message', (message) => {
        try {
            const msg = JSON.parse(message);
            handleBrowserMessage(ws, msg);
        } catch (e) {
            console.error('Invalid WebSocket message:', e);
        }
    });

    ws.on('close', () => {
        console.log('🌐 Browser disconnected');
        browserClients.delete(ws);
    });

    ws.on('error', (err) => {
        console.error('WebSocket error:', err);
        browserClients.delete(ws);
    });
});

// ============================================
// MESSAGE HANDLERS
// ============================================

function handleRoverTelemetry(data) {
    const { 
        id,                    // Required: rover identifier
        name = 'Rover',        // Display name
        type = 'robot',        // Device type for icon
        // GPS data
        lat, lon, alt = 0,
        speed = 0, heading = 0,
        accuracy = 0, altAccuracy = 0, speedAccuracy = 0, headingAccuracy = 0,
        pdop = 0, hdop = 0, vdop = 0, tdop = 0,
        vSpeed = 0, vSpeedAccuracy = 0,
        // IMU data (raw 16-bit values)
        gx = 0, gy = 0, gz = 0,  // Gyroscope
        ax = 0, ay = 0, az = 0,  // Accelerometer
        // Encoder data
        encL = 0, encR = 0,      // Left/Right encoder counts
        encLVel = 0, encRVel = 0, // Encoder velocities
        // Status
        battery = 100,
        status = 'online'
    } = data;

    if (!id) {
        console.error('Telemetry missing rover id');
        return;
    }

    const now = Date.now();
    const roverData = {
        id,
        name,
        type,
        // GPS
        lat, lon, alt,
        speed, heading,
        accuracy, altAccuracy, speedAccuracy, headingAccuracy,
        pdop, hdop, vdop, tdop,
        vSpeed, vSpeedAccuracy,
        // IMU
        gx, gy, gz, ax, ay, az,
        // Encoders
        encL, encR, encLVel, encRVel,
        // Meta
        battery,
        status,
        lastSeen: now
    };

    const isNew = !rovers.has(id);
    rovers.set(id, roverData);

    // Broadcast to all browsers
    const msgType = isNew ? 'device:online' : 'device:update';
    broadcast({
        type: msgType,
        data: roverToDevice(roverData)
    });

    if (isNew) {
        console.log(`🤖 Rover online: ${name} (${id})`);
    }
}

function handleBrowserMessage(ws, msg) {
    const { type, data } = msg;

    switch (type) {
        case 'getDevices':
            ws.send(JSON.stringify({
                type: 'devices:list',
                data: Array.from(rovers.values()).map(roverToDevice)
            }));
            break;

        case 'sendCommand':
            const { deviceId, commandType, payload } = data;
            queueCommand(deviceId, commandType, payload);
            ws.send(JSON.stringify({
                type: 'command:sent',
                data: { deviceId, commandType, status: 'queued' }
            }));
            break;

        // Pairing not needed for v1, but keep compatible
        case 'dismissPairing':
        case 'revokeDevice':
            // No-op for now
            break;

        default:
            console.log('Unknown message type:', type);
    }
}

function queueCommand(roverId, commandType, payload) {
    if (!pendingCommands.has(roverId)) {
        pendingCommands.set(roverId, []);
    }
    
    const command = {
        id: ++commandIdCounter,
        type: commandType,
        payload: payload || {},
        timestamp: Date.now()
    };
    
    pendingCommands.get(roverId).push(command);
    console.log(`📤 Command queued: ${commandType} -> ${roverId}`);
}

// Convert internal rover data to GlobalRTS device format
function roverToDevice(rover) {
    return {
        id: rover.id,
        name: rover.name,
        type: rover.type,
        latitude: rover.lat,
        longitude: rover.lon,
        altitude: rover.alt,
        speed: rover.speed,
        heading: rover.heading,
        battery: rover.battery,
        status: rover.status,
        last_seen: Math.floor(rover.lastSeen / 1000),
        // Extended telemetry (GlobalRTS can display if it wants)
        telemetry: {
            gps: {
                accuracy: rover.accuracy,
                altAccuracy: rover.altAccuracy,
                speedAccuracy: rover.speedAccuracy,
                headingAccuracy: rover.headingAccuracy,
                pdop: rover.pdop,
                hdop: rover.hdop,
                vdop: rover.vdop,
                tdop: rover.tdop,
                vSpeed: rover.vSpeed,
                vSpeedAccuracy: rover.vSpeedAccuracy
            },
            imu: {
                gx: rover.gx, gy: rover.gy, gz: rover.gz,
                ax: rover.ax, ay: rover.ay, az: rover.az
            },
            encoders: {
                left: rover.encL, right: rover.encR,
                leftVel: rover.encLVel, rightVel: rover.encRVel
            }
        }
    };
}

function broadcast(msg) {
    const data = JSON.stringify(msg);
    browserClients.forEach(client => {
        if (client.readyState === 1) { // OPEN
            client.send(data);
        }
    });
}

// ============================================
// ROVER TIMEOUT - Mark offline if no data
// ============================================

setInterval(() => {
    const now = Date.now();
    const TIMEOUT = 10000; // 10 seconds

    rovers.forEach((rover, id) => {
        if (rover.status !== 'offline' && now - rover.lastSeen > TIMEOUT) {
            rover.status = 'offline';
            rovers.set(id, rover);
            broadcast({
                type: 'device:offline',
                data: { deviceId: id }
            });
            console.log(`🤖 Rover offline: ${rover.name} (${id})`);
        }
    });
}, 5000);

// ============================================
// START
// ============================================

server.listen(PORT, () => {
    console.log(`
╔═══════════════════════════════════════════════════╗
║         GlobalRTS Server - Running                ║
╠═══════════════════════════════════════════════════╣
║  Web UI:     http://localhost:${PORT}               ║
║  WebSocket:  ws://localhost:${PORT}                 ║
║  Rover API:  POST /api/telemetry                  ║
║              GET  /api/commands/:id               ║
╚═══════════════════════════════════════════════════╝
    `);
});
