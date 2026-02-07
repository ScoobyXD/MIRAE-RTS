/**
 * GlobalRTS Server - Enhanced with Rover WebSocket Support
 * 
 * Now supports TWO connection modes for rovers:
 * 1. WebSocket (preferred): Low latency, bidirectional, instant commands
 * 2. HTTP (fallback): Works when WebSocket fails
 * 
 * Architecture:
 *   Rover --WebSocket /rover--> Server --WebSocket--> Browser (instant!)
 *   Rover --HTTP POST---------> Server --WebSocket--> Browser (fallback)
 *   
 * WebSocket gives you ~50-100ms latency (cellular only)
 * HTTP polling adds +1000ms on top of that
 */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { WebSocketServer, WebSocket } = require('ws');

const PORT = process.env.PORT || 8080;

// ============================================
// IN-MEMORY STATE
// ============================================

// Current rover state - latest telemetry from each rover
// Key: roverId, Value: { id, name, type, lat, lon, ..., lastSeen, status }
const rovers = new Map();

// Pending commands for rovers (HTTP polling only)
// Key: roverId, Value: [{ id, type, payload, timestamp }]
const pendingCommands = new Map();

// Connected rover WebSocket clients
// Key: roverId, Value: WebSocket
const roverClients = new Map();

// Connected GlobalRTS browser clients
const browserClients = new Set();

// Command ID counter
let commandIdCounter = 0;

// Current active command per rover (for /api/health display)
// Key: roverId, Value: { type, payload, timestamp, status }
const activeCommands = new Map();

// ============================================
// OURA API PROXY (unchanged)
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
// HTTP SERVER
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

    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    // ========== ROVER API ENDPOINTS ==========

    // POST /api/telemetry - Rover sends telemetry (HTTP fallback)
    if (req.method === 'POST' && pathname === '/api/telemetry') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                const data = JSON.parse(body);
                handleRoverTelemetry(data, 'http');
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ ok: true }));
            } catch (e) {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Invalid JSON' }));
            }
        });
        return;
    }

    // GET /api/commands/:roverId - Rover polls for commands (HTTP fallback)
    if (req.method === 'GET' && pathname.startsWith('/api/commands/')) {
        const roverId = pathname.split('/')[3];
        const commands = pendingCommands.get(roverId) || [];
        pendingCommands.set(roverId, []); // Clear after sending
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ commands }));
        return;
    }

    // POST /api/command - Browser sends command to rover
    if (req.method === 'POST' && pathname === '/api/command') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                const { roverId, type, payload } = JSON.parse(body);
                sendCommandToRover(roverId, type, payload);
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

    // GET /api/health - Health check with live telemetry + active commands
    if (req.method === 'GET' && pathname === '/api/health') {
        const roverList = [];
        rovers.forEach((rover, id) => {
            const cmd = activeCommands.get(id);
            roverList.push({
                id: rover.id,
                name: rover.name,
                // ── Live Telemetry ──
                telemetry: {
                    lat: rover.lat,
                    lon: rover.lon,
                    alt: rover.alt,
                    speed: rover.speed,
                    heading: rover.heading,
                    accuracy: rover.accuracy,
                    hdop: rover.hdop,
                    imu: { ax: rover.ax, ay: rover.ay, az: rover.az, gx: rover.gx, gy: rover.gy, gz: rover.gz },
                    encoders: { L: rover.encL, R: rover.encR, velL: rover.encLVel, velR: rover.encRVel },
                    battery: rover.battery,
                    status: rover.status,
                    connectionMode: rover.connectionMode,
                    lastSeen: rover.lastSeen,
                    age: `${((Date.now() - rover.lastSeen) / 1000).toFixed(1)}s ago`
                },
                // ── Active Command ──
                activeCommand: cmd ? {
                    type: cmd.type,
                    payload: cmd.payload,
                    status: cmd.status,
                    issuedAt: new Date(cmd.timestamp).toISOString(),
                    age: `${((Date.now() - cmd.timestamp) / 1000).toFixed(1)}s ago`
                } : null
            });
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ 
            status: 'ok', 
            connections: {
                rovers: rovers.size,
                roversWS: roverClients.size,
                roversHTTP: rovers.size - roverClients.size,
                browsers: [...browserClients].filter(c => c.readyState === WebSocket.OPEN).length,
            },
            uptime: process.uptime(),
            roverData: roverList
        }, null, 2));
        return;
    }

    // ========== OURA API PROXY ==========
    if (req.method === 'GET' && pathname.startsWith('/api/oura/')) {
        const ouraPath = pathname.replace('/api/oura', '');
        const queryString = url.search || '';
        const ouraUrl = `https://api.ouraring.com${ouraPath}${queryString}`;
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
// WEBSOCKET SERVER - Browser connections (unchanged path)
// ============================================

const wss = new WebSocketServer({ noServer: true });

// Handle upgrade requests - route to appropriate handler
server.on('upgrade', (request, socket, head) => {
    const pathname = new URL(request.url, `http://${request.headers.host}`).pathname;
    
    if (pathname === '/rover') {
        // Rover WebSocket connection
        wssRover.handleUpgrade(request, socket, head, (ws) => {
            wssRover.emit('connection', ws, request);
        });
    } else {
        // Browser WebSocket connection (default path: /)
        wss.handleUpgrade(request, socket, head, (ws) => {
            wss.emit('connection', ws, request);
        });
    }
});

// Browser WebSocket connections
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
        console.error('Browser WebSocket error:', err);
        browserClients.delete(ws);
    });
});

// ============================================
// WEBSOCKET SERVER - Rover connections (NEW!)
// ============================================

const wssRover = new WebSocketServer({ noServer: true });

wssRover.on('connection', (ws, request) => {
    const clientIP = request.headers['x-forwarded-for'] || request.socket.remoteAddress;
    console.log(`🤖 Rover WebSocket connected from ${clientIP} (awaiting identification)`);
    
    let roverId = null;
    let heartbeatInterval = null;
    
    // Setup heartbeat to detect stale connections
    const heartbeat = () => {
        ws.isAlive = true;
    };
    ws.isAlive = true;
    ws.on('pong', heartbeat);
    
    // Ping every 30 seconds to keep connection alive
    heartbeatInterval = setInterval(() => {
        if (ws.isAlive === false) {
            console.log(`🤖 Rover heartbeat failed: ${roverId || 'unknown'}`);
            return ws.terminate();
        }
        ws.isAlive = false;
        ws.ping();
    }, 30000);
    
    ws.on('message', (message) => {
        try {
            const msgStr = message.toString();
            const msg = JSON.parse(msgStr);
            
            // Handle rover identification
            if (msg.type === 'rover:identify') {
                roverId = msg.data?.id;
                if (roverId) {
                    // Check if rover already connected (from different instance?)
                    const existingWs = roverClients.get(roverId);
                    if (existingWs && existingWs !== ws && existingWs.readyState === WebSocket.OPEN) {
                        console.log(`🤖 Rover ${roverId} reconnecting - closing old connection`);
                        existingWs.close(1000, 'Superseded by new connection');
                    }
                    
                    // Store WebSocket connection
                    roverClients.set(roverId, ws);
                    console.log(`🤖 Rover identified: ${roverId} (WebSocket mode, total: ${roverClients.size})`);
                    
                    // Send acknowledgment
                    ws.send(JSON.stringify({
                        type: 'ack',
                        data: { message: 'Identified', id: roverId }
                    }));
                    
                    // If there are pending commands (from before WS connected), send them
                    const pending = pendingCommands.get(roverId) || [];
                    if (pending.length > 0) {
                        ws.send(JSON.stringify({
                            type: 'commands',
                            data: { commands: pending }
                        }));
                        pendingCommands.set(roverId, []);
                        console.log(`📤 Sent ${pending.length} pending commands to ${roverId}`);
                    }
                }
            }
            
            // Handle telemetry from rover
            else if (msg.type === 'rover:telemetry') {
                handleRoverTelemetry(msg.data, 'websocket');
            }
            
            // Handle rover reporting command status
            else if (msg.type === 'rover:command_status') {
                if (msg.data?.id && msg.data?.status) {
                    const existing = activeCommands.get(msg.data.id);
                    if (existing) {
                        existing.status = msg.data.status;
                        if (msg.data.status === 'arrived') {
                            existing.arrivedAt = Date.now();
                        }
                    }
                    console.log(`📋 Command status from ${msg.data.id}: ${msg.data.status}`);
                }
            }
            
            // Handle other rover messages
            else {
                console.log(`🤖 Rover message: ${msg.type}`, msg.data);
            }
            
        } catch (e) {
            console.error('Invalid rover WebSocket message:', e.message);
        }
    });

    ws.on('close', (code, reason) => {
        clearInterval(heartbeatInterval);
        if (roverId) {
            // Only delete if this is still the active connection for this rover
            if (roverClients.get(roverId) === ws) {
                roverClients.delete(roverId);
            }
            console.log(`🤖 Rover WebSocket disconnected: ${roverId} (code: ${code}, reason: ${reason || 'none'})`);
            
            // Mark rover as potentially offline
            const rover = rovers.get(roverId);
            if (rover) {
                rover.connectionMode = 'disconnected';
            }
        } else {
            console.log(`🤖 Rover WebSocket disconnected before identification (code: ${code})`);
        }
    });

    ws.on('error', (err) => {
        clearInterval(heartbeatInterval);
        console.error(`Rover WebSocket error: ${err.message}`);
        if (roverId) {
            if (roverClients.get(roverId) === ws) {
                roverClients.delete(roverId);
            }
        }
    });
});

// ============================================
// MESSAGE HANDLERS
// ============================================

function handleRoverTelemetry(data, source = 'http') {
    const { 
        id,
        name = 'Rover',
        type = 'robot',
        // GPS data
        lat, lon, alt = 0,
        speed = 0, heading = 0,
        accuracy = 0, altAccuracy = 0, speedAccuracy = 0, headingAccuracy = 0,
        pdop = 0, hdop = 0, vdop = 0, tdop = 0,
        vSpeed = 0, vSpeedAccuracy = 0,
        // IMU data
        gx = 0, gy = 0, gz = 0,
        ax = 0, ay = 0, az = 0,
        // Encoder data
        encL = 0, encR = 0,
        encLVel = 0, encRVel = 0,
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
        lastSeen: now,
        connectionMode: source  // 'websocket' or 'http'
    };

    const isNew = !rovers.has(id);
    rovers.set(id, roverData);

    // Log every telemetry (first 5, then every 10th)
    const count = roverData._telemetryCount = (rovers.get(id)?._telemetryCount || 0) + 1;
    roverData._telemetryCount = count;
    if (count <= 5 || count % 10 === 0) {
        console.log(`📡 Telemetry #${count} from ${id} via ${source}: lat=${lat}, lon=${lon}, speed=${speed}`);
    }

    // Broadcast to all browsers
    const msgType = isNew ? 'device:online' : 'device:update';
    const browserCount = [...browserClients].filter(c => c.readyState === WebSocket.OPEN).length;
    broadcastToBrowsers({
        type: msgType,
        data: roverToDevice(roverData)
    });

    if (isNew) {
        console.log(`🤖 Rover online: ${name} (${id}) via ${source} — broadcasting to ${browserCount} browsers`);
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
            sendCommandToRover(deviceId, commandType, payload);
            // Track active command
            activeCommands.set(deviceId, {
                type: commandType,
                payload: payload || {},
                timestamp: Date.now(),
                status: 'sent'
            });
            ws.send(JSON.stringify({
                type: 'command:sent',
                data: { deviceId, commandType, status: 'sent' }
            }));
            break;

        case 'selectDevice':
            if (data.deviceId) {
                console.log(`🖱️  Browser selected: ${data.deviceId}`);
                // Forward to rover
                const selWs = roverClients.get(data.deviceId);
                if (selWs && selWs.readyState === WebSocket.OPEN) {
                    selWs.send(JSON.stringify({ type: 'selected', data: { id: data.deviceId } }));
                }
            }
            break;

        case 'deselectDevice':
            if (data.deviceId) {
                console.log(`🖱️  Browser deselected: ${data.deviceId}`);
                const deselWs = roverClients.get(data.deviceId);
                if (deselWs && deselWs.readyState === WebSocket.OPEN) {
                    deselWs.send(JSON.stringify({ type: 'deselected', data: { id: data.deviceId } }));
                }
            }
            break;

        case 'dismissPairing':
        case 'revokeDevice':
            // No-op for now
            break;

        default:
            console.log('Unknown browser message type:', type);
    }
}

/**
 * Send command to rover - prefers WebSocket, falls back to queue for HTTP
 */
function sendCommandToRover(roverId, commandType, payload) {
    const command = {
        id: ++commandIdCounter,
        type: commandType,
        payload: payload || {},
        timestamp: Date.now()
    };
    
    // Try WebSocket first (instant delivery)
    const roverWs = roverClients.get(roverId);
    if (roverWs && roverWs.readyState === WebSocket.OPEN) {
        roverWs.send(JSON.stringify({
            type: 'command',
            data: command
        }));
        console.log(`📤 Command sent (WebSocket): ${commandType} -> ${roverId}`);
        return;
    }
    
    // Fall back to queue for HTTP polling
    if (!pendingCommands.has(roverId)) {
        pendingCommands.set(roverId, []);
    }
    pendingCommands.get(roverId).push(command);
    console.log(`📤 Command queued (HTTP): ${commandType} -> ${roverId}`);
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
        connection_mode: rover.connectionMode,  // NEW: 'websocket' or 'http'
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

function broadcastToBrowsers(msg) {
    const data = JSON.stringify(msg);
    browserClients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
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
            broadcastToBrowsers({
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
╔═══════════════════════════════════════════════════════════════╗
║            GlobalRTS Server - Enhanced                        ║
╠═══════════════════════════════════════════════════════════════╣
║  Web UI:        http://localhost:${PORT}                        ║
║                                                               ║
║  Browser WS:    ws://localhost:${PORT}/                         ║
║  Rover WS:      ws://localhost:${PORT}/rover      ← NEW!        ║
║                                                               ║
║  HTTP API:      POST /api/telemetry                           ║
║                 GET  /api/commands/:id                        ║
║                 GET  /api/health                              ║
╚═══════════════════════════════════════════════════════════════╝
    `);
});
