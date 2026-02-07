#!/usr/bin/env node
/**
 * test-rover.js - Simulates a rover sending telemetry via WebSocket
 * 
 * This mimics EXACTLY what the Raspberry Pi rover_client.py does:
 * 1. Connect WebSocket to /rover
 * 2. Send rover:identify
 * 3. Wait for ack
 * 4. Send rover:telemetry every second
 * 
 * Usage: node test-rover.js [server-url]
 *   node test-rover.js                          # local: ws://localhost:8080
 *   node test-rover.js wss://miraeopus.com      # production
 *   node test-rover.js https://miraeopus.com    # auto-converts to wss://
 */

const WebSocket = require('ws');

let SERVER = process.argv[2] || 'ws://localhost:8080';
// Auto-convert URL schemes
if (SERVER.startsWith('https://')) SERVER = SERVER.replace('https://', 'wss://');
if (SERVER.startsWith('http://')) SERVER = SERVER.replace('http://', 'ws://');

const ROVER_ID = 'test-rover';
const ROVER_NAME = 'TestRover';

// Start position: San Francisco (Golden Gate Park area)
let lat = 37.7694;
let lon = -122.4862;
let heading = 45.0;
let encL = 0;
let encR = 0;
let telemetrySent = 0;

const WS_URL = `${SERVER}/rover`;

console.log(`🤖 Test Rover (WebSocket mode)`);
console.log(`   Server: ${WS_URL}`);
console.log(`   ID: ${ROVER_ID}`);
console.log(`   Start: ${lat}, ${lon} (San Francisco)`);
console.log(`   Press Ctrl+C to stop\n`);

function connect() {
    console.log(`🔌 Connecting to ${WS_URL}...`);
    
    const ws = new WebSocket(WS_URL);
    let telemetryInterval = null;
    let identified = false;

    ws.on('open', () => {
        console.log(`✅ WebSocket connected!`);
        
        // Step 1: Send identification (exactly like rover_client.py)
        const identifyMsg = JSON.stringify({
            type: 'rover:identify',
            data: {
                id: ROVER_ID,
                name: ROVER_NAME,
                type: 'robot'
            }
        });
        console.log(`📤 Sending identify: ${identifyMsg}`);
        ws.send(identifyMsg);
    });

    ws.on('message', (data) => {
        const msg = JSON.parse(data.toString());
        console.log(`📥 Received: ${JSON.stringify(msg)}`);
        
        if (msg.type === 'ack') {
            console.log(`✅ Server acknowledged! Starting telemetry stream...\n`);
            identified = true;
            
            // Step 2: Start sending telemetry every second (exactly like rover_client.py)
            telemetryInterval = setInterval(() => {
                // Simulate GPS drift (small random walk around SF)
                lat += (Math.random() - 0.5) * 0.0001;
                lon += (Math.random() - 0.5) * 0.0001;
                heading = (heading + (Math.random() - 0.5) * 10 + 360) % 360;
                encL += Math.floor(Math.random() * 10);
                encR += Math.floor(Math.random() * 10);

                const telemetry = {
                    type: 'rover:telemetry',
                    data: {
                        id: ROVER_ID,
                        name: ROVER_NAME,
                        type: 'robot',
                        lat,
                        lon,
                        alt: 50.0,
                        speed: 0.5 + Math.random() * 0.5,
                        heading,
                        accuracy: 2.5,
                        hdop: 1.2,
                        ax: Math.floor((Math.random() - 0.5) * 1000),
                        ay: Math.floor((Math.random() - 0.5) * 1000),
                        az: Math.floor(16000 + Math.random() * 500),
                        gx: Math.floor((Math.random() - 0.5) * 100),
                        gy: Math.floor((Math.random() - 0.5) * 100),
                        gz: Math.floor((Math.random() - 0.5) * 100),
                        encL,
                        encR,
                        encLVel: Math.floor(Math.random() * 100),
                        encRVel: Math.floor(Math.random() * 100),
                        battery: 85,
                        status: 'online'
                    }
                };

                ws.send(JSON.stringify(telemetry));
                telemetrySent++;
                process.stdout.write(`\r📡 #${telemetrySent} | ${lat.toFixed(6)}, ${lon.toFixed(6)} | H:${heading.toFixed(0)}°  `);
            }, 1000);
        }
        
        if (msg.type === 'command') {
            console.log(`\n🎯 Command: ${msg.data.type}`, JSON.stringify(msg.data.payload));
            if (msg.data.type === 'navigate' && msg.data.payload) {
                lat += (msg.data.payload.latitude - lat) * 0.1;
                lon += (msg.data.payload.longitude - lon) * 0.1;
            }
        }
    });

    ws.on('close', (code, reason) => {
        console.log(`\n❌ WebSocket closed: code=${code} reason=${reason || 'none'}`);
        if (telemetryInterval) clearInterval(telemetryInterval);
        // Reconnect after 5 seconds
        console.log(`   Reconnecting in 5s...`);
        setTimeout(connect, 5000);
    });

    ws.on('error', (err) => {
        console.error(`\n❌ WebSocket error: ${err.message}`);
    });
}

connect();
