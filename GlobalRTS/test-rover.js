#!/usr/bin/env node
/**
 * test-rover.js - Simulates a rover sending telemetry
 * 
 * Usage: node test-rover.js [server-url]
 * Default server: http://localhost:8080
 * 
 * This simulates your nRF9151 sending data to the server.
 * The GlobalRTS browser should show the rover moving around LA.
 */

const SERVER = process.argv[2] || 'http://localhost:8080';
const ROVER_ID = 'rover-001';
const ROVER_NAME = 'TestRover';

// Start position: Los Angeles
let lat = 34.0522;
let lon = -118.2437;
let heading = 0;

console.log(`🤖 Test Rover starting...`);
console.log(`   Server: ${SERVER}`);
console.log(`   ID: ${ROVER_ID}`);
console.log(`   Press Ctrl+C to stop\n`);

async function sendTelemetry() {
    // Simulate movement - small random walk
    lat += (Math.random() - 0.5) * 0.0001;
    lon += (Math.random() - 0.5) * 0.0001;
    heading = (heading + (Math.random() - 0.5) * 10 + 360) % 360;

    const telemetry = {
        id: ROVER_ID,
        name: ROVER_NAME,
        type: 'robot',
        // GPS
        lat,
        lon,
        alt: 100,
        speed: 0.5 + Math.random() * 0.5,
        heading,
        accuracy: 2.5,
        hdop: 1.2,
        // IMU (simulated)
        ax: Math.floor((Math.random() - 0.5) * 1000),
        ay: Math.floor((Math.random() - 0.5) * 1000),
        az: Math.floor(16000 + Math.random() * 500), // ~1g
        gx: Math.floor((Math.random() - 0.5) * 100),
        gy: Math.floor((Math.random() - 0.5) * 100),
        gz: Math.floor((Math.random() - 0.5) * 100),
        // Encoders
        encL: Math.floor(Math.random() * 10000),
        encR: Math.floor(Math.random() * 10000),
        // Status
        battery: 85,
        status: 'online'
    };

    try {
        const res = await fetch(`${SERVER}/api/telemetry`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(telemetry)
        });
        
        if (res.ok) {
            process.stdout.write(`📍 ${lat.toFixed(6)}, ${lon.toFixed(6)} | Heading: ${heading.toFixed(0)}°\r`);
        } else {
            console.error(`\n❌ Server error: ${res.status}`);
        }
    } catch (err) {
        console.error(`\n❌ Connection failed: ${err.message}`);
    }
}

async function pollCommands() {
    try {
        const res = await fetch(`${SERVER}/api/commands/${ROVER_ID}`);
        if (res.ok) {
            const data = await res.json();
            if (data.commands && data.commands.length > 0) {
                console.log(`\n📥 Received ${data.commands.length} command(s):`);
                data.commands.forEach(cmd => {
                    console.log(`   ${cmd.type}:`, JSON.stringify(cmd.payload));
                    
                    // If it's a navigate command, move towards target
                    if (cmd.type === 'navigate' && cmd.payload.latitude && cmd.payload.longitude) {
                        console.log(`   🎯 Moving towards: ${cmd.payload.latitude}, ${cmd.payload.longitude}`);
                        // Gradually move towards target
                        lat = lat + (cmd.payload.latitude - lat) * 0.1;
                        lon = lon + (cmd.payload.longitude - lon) * 0.1;
                    }
                });
            }
        }
    } catch (err) {
        // Ignore poll errors
    }
}

// Send telemetry every second
setInterval(sendTelemetry, 1000);

// Poll for commands every second
setInterval(pollCommands, 1000);

// Initial send
sendTelemetry();
