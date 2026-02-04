# GlobalRTS Server

Minimal WebSocket server connecting your rover (nRF9151) to GlobalRTS browser UI.

## Quick Start (Local)

```bash
# Install dependencies
npm install

# Start server
npm start

# Open browser
open http://localhost:8080

# In another terminal, run test rover
node test-rover.js
```

You should see a rover appear on the map and move around LA.

---

## Deploy to Fly.io (Free)

### 1. Install Fly CLI

**Mac:**
```bash
brew install flyctl
```

**Windows:**
```powershell
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

**Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

### 2. Create Fly Account & Login

```bash
fly auth signup   # Or: fly auth login
```

### 3. Deploy

```bash
cd globalrts-server

# First time only - creates the app
fly launch --name globalrts --region lax --no-deploy

# Deploy
fly deploy
```

Your server will be live at: `https://globalrts.fly.dev`

### 4. Test It

```bash
# Run test rover against deployed server
node test-rover.js https://globalrts.fly.dev
```

Open `https://globalrts.fly.dev` in browser - you should see the rover!

---

## Custom Domain (miraeopus.com)

After deploying to Fly.io:

### 1. Add Certificate

```bash
fly certs add miraeopus.com
fly certs add www.miraeopus.com
```

### 2. Configure DNS

Add these DNS records at your domain registrar:

| Type  | Name | Value                    |
|-------|------|--------------------------|
| A     | @    | (Fly.io IP - shown after fly certs add) |
| AAAA  | @    | (Fly.io IPv6 - shown after fly certs add) |
| CNAME | www  | globalrts.fly.dev        |

### 3. Wait for DNS Propagation

Can take 5 minutes to 48 hours. Check with:
```bash
fly certs check miraeopus.com
```

Once verified, your rover can use `https://miraeopus.com` instead of fly.dev.

---

## Files

```
globalrts-server/
├── server.js      # Main server (HTTP + WebSocket)
├── package.json   # Dependencies (just 'ws')
├── fly.toml       # Fly.io config
├── Dockerfile     # Container config
├── test-rover.js  # Simulated rover for testing
├── API.md         # Full API documentation
└── public/
    ├── globalui.html  # GlobalRTS UI
    └── CONFIG.js      # Frontend config
```

---

## Architecture

```
┌─────────────┐       HTTP POST        ┌────────────────────┐
│   nRF9151   │ ─────────────────────▶ │                    │
│   (Rover)   │                        │   Fly.io Server    │
│             │ ◀───────────────────── │   (globalrts.fly.dev)
└─────────────┘       HTTP GET         │                    │
                    (poll commands)    │   - In-memory only │
                                       │   - No database    │
┌─────────────┐                        │   - Just Node + ws │
│  GlobalRTS  │ ◀════ WebSocket ═════▶ │                    │
│  (Browser)  │                        └────────────────────┘
└─────────────┘

Latency: ~100-300ms depending on cellular signal
Data: ~2.5 KB/hour at 1Hz telemetry
```

---

## Troubleshooting

**Rover not appearing on map?**
- Check server logs: `fly logs`
- Verify telemetry is being sent: `curl https://globalrts.fly.dev/api/rovers`
- Make sure lat/lon are valid numbers

**WebSocket not connecting?**
- Browser must use `wss://` (secure) for HTTPS pages
- Check browser console for errors
- Verify `CONFIG.SERVER_URL` is empty (auto-detect) or correct

**Commands not reaching rover?**
- Rover must poll `/api/commands/{id}` regularly
- Commands are cleared after retrieval
- Check command queue: send a command, then immediately GET the endpoint
