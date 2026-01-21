# Electron Pipecat Starter

A desktop application for real-time voice chat using **Electron**, **Vite**, **React** (TypeScript), and the **Pipecat Client JS SDK**.

## Features

- Real-time voice communication with Pipecat bots
- SmallWebRTCTransport (default, free, autonomous) or DailyTransport
- Minimal UI: Connect/Disconnect, Mic On/Off, Status indicator
- Audio level VU-meter for local and remote audio
- Event logs and conversation transcript display
- Secure Electron setup: `contextIsolation=true`, `nodeIntegration=false`

## Project Structure

```
electron-pipecat-starter/
├── src/
│   ├── main/
│   │   └── main.ts              # Electron main process
│   ├── preload/
│   │   └── preload.ts           # Secure IPC bridge
│   └── renderer/
│       ├── components/
│       │   ├── AudioMeter.tsx   # VU-meter component
│       │   ├── Controls.tsx     # Connect/Mic buttons
│       │   ├── LogPanel.tsx     # Event log display
│       │   ├── StatusIndicator.tsx
│       │   └── TranscriptPanel.tsx
│       ├── lib/
│       │   ├── pipecatAdapter.ts # Pipecat client wrapper
│       │   └── types.ts
│       ├── styles/
│       │   └── App.css
│       ├── App.tsx              # Main React component
│       ├── main.tsx             # React entry point
│       └── vite-env.d.ts
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── .env.example
├── entitlements.mac.plist       # macOS permissions
└── README.md
```

## Prerequisites

- **Node.js** >= 18.x
- **npm** or **yarn**
- A running **Pipecat bot server** with SmallWebRTCTransport enabled

## HOW TO RUN

### 1. Install Dependencies

```bash
cd electron-pipecat-starter
npm install
```

### 2. Configure Environment

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# For SmallWebRTCTransport (default)
VITE_PIPECAT_URL=http://localhost:7860/offer
VITE_TRANSPORT_TYPE=small-webrtc

# For DailyTransport (optional)
# VITE_TRANSPORT_TYPE=daily
# VITE_DAILY_ROOM_URL=https://your-domain.daily.co/room-name
# VITE_DAILY_TOKEN=your-daily-token
```

### 3. Start Your Pipecat Bot Server

Make sure your Pipecat Python server is running with SmallWebRTCTransport. Example:

```python
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport

transport = SmallWebRTCTransport(
    host="0.0.0.0",
    port=7860,
)
```

### 4. Run in Development Mode

```bash
npm run dev
```

This will:
- Start the Vite dev server on port 5173
- Launch the Electron window with hot-reload

### 5. Build for Production

```bash
npm run build
```

Output will be in `release/` folder.

### 6. Run Production Build

```bash
npm start
```

## Switching Transports

The adapter supports both **SmallWebRTCTransport** and **DailyTransport**.

### SmallWebRTCTransport (Default)

- Free and autonomous (no external service required)
- Best for local development and demos
- Requires your own Pipecat server with SmallWebRTC support

```env
VITE_TRANSPORT_TYPE=small-webrtc
VITE_PIPECAT_URL=http://localhost:7860/offer
```

### DailyTransport

- More robust, production-ready
- Requires a Daily.co account
- Better NAT traversal and infrastructure

```env
VITE_TRANSPORT_TYPE=daily
VITE_DAILY_ROOM_URL=https://your-domain.daily.co/room-name
VITE_DAILY_TOKEN=your-daily-token
```

## TROUBLESHOOTING

### Microphone Permission Issues

#### macOS

1. **System Preferences** > **Security & Privacy** > **Privacy** > **Microphone**
2. Ensure your terminal (for dev) or the app (for production) has microphone access
3. If using development build, you may need to grant permission to the terminal or Electron Helper

The app will automatically request permission on first launch.

#### Windows

1. **Settings** > **Privacy** > **Microphone**
2. Enable "Allow apps to access your microphone"
3. Make sure the app is listed and enabled

#### Linux

```bash
# Check if PulseAudio is running
pulseaudio --check

# List audio devices
pactl list sources short

# Grant permissions if using Flatpak/Snap
flatpak override --user --device=all com.your.app
```

### WebRTC / Connection Issues

#### STUN/TURN Configuration

The default configuration uses Google's public STUN servers:

```typescript
iceServers: [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
]
```

For production or restrictive networks, add TURN servers in `pipecatAdapter.ts`:

```typescript
iceServers: [
  { urls: 'stun:stun.l.google.com:19302' },
  {
    urls: 'turn:your-turn-server.com:3478',
    username: 'user',
    credential: 'password',
  },
]
```

#### Firewall

Ensure these ports are open:
- **TCP/UDP 3478** - STUN/TURN
- **UDP 49152-65535** - WebRTC media (or your configured port range)
- **TCP 7860** (or your configured port) - Pipecat signaling

#### Common Connection Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `ICE connection failed` | Network/firewall blocking | Check firewall, add TURN server |
| `Connection timeout` | Server not reachable | Verify `VITE_PIPECAT_URL` and server is running |
| `Permission denied` | Microphone not allowed | Grant microphone permission |
| `Transport error` | Wrong transport type | Verify server and client use same transport |

### Debug Logs

Open DevTools in the Electron window (`Cmd+Opt+I` / `Ctrl+Shift+I`) to see:
- Console logs from the renderer process
- Network requests
- WebRTC internals (chrome://webrtc-internals in Chrome-based browsers)

Main process logs appear in the terminal where you ran `npm run dev`.

### Audio Not Playing

1. Check browser/Electron autoplay policies
2. Ensure volume is not muted
3. Check the Log Panel for "Bot audio track received" event
4. Verify the bot is sending audio (check server logs)

## API Reference

### PipecatAdapter

```typescript
import { PipecatAdapter, createPipecatAdapter } from './lib/pipecatAdapter';

const adapter = createPipecatAdapter(
  {
    transportType: 'small-webrtc',
    webrtcUrl: 'http://localhost:7860/offer',
    enableMic: true,
  },
  {
    onStateChange: (state) => console.log('State:', state),
    onLog: (entry) => console.log(entry),
    onLocalAudioLevel: (level) => {},
    onRemoteAudioLevel: (level) => {},
    onBotTranscript: (text) => console.log('Bot:', text),
    onUserTranscript: (text, final) => console.log('User:', text),
    onError: (error) => console.error(error),
  }
);

// Connect
await adapter.connect();

// Toggle microphone
await adapter.toggleMic();

// Disconnect
await adapter.disconnect();
```

### Key Methods

| Method | Description |
|--------|-------------|
| `connect()` | Connect to the Pipecat bot |
| `disconnect()` | Disconnect from the bot |
| `toggleMic()` | Toggle microphone on/off |
| `setMicEnabled(boolean)` | Enable/disable microphone |
| `sendText(string)` | Send text to the bot |
| `getMicrophones()` | Get available microphone devices |
| `setMicrophone(deviceId)` | Switch microphone |

### Callbacks

| Callback | Parameters | Description |
|----------|------------|-------------|
| `onStateChange` | `state: ConnectionState` | Connection state changed |
| `onLog` | `entry: LogEntry` | Log event |
| `onLocalAudioLevel` | `level: number` | Local audio level (0-1) |
| `onRemoteAudioLevel` | `level: number` | Remote audio level (0-1) |
| `onBotTranscript` | `text: string` | Bot speech text |
| `onUserTranscript` | `text: string, final: boolean` | User speech text |
| `onBotStartedSpeaking` | - | Bot started speaking |
| `onBotStoppedSpeaking` | - | Bot stopped speaking |
| `onUserStartedSpeaking` | - | User started speaking |
| `onUserStoppedSpeaking` | - | User stopped speaking |
| `onError` | `error: Error` | Error occurred |

## Security Notes

- **contextIsolation=true**: Renderer process cannot access Node.js APIs directly
- **nodeIntegration=false**: Node.js is disabled in the renderer
- **preload script**: Only exposes a minimal, safe API to the renderer
- **No API keys in renderer**: Sensitive data should be handled in the main process

## License

MIT

## Resources

- [Pipecat JS SDK Documentation](https://docs.pipecat.ai/client/js/introduction)
- [Pipecat Client Methods](https://docs.pipecat.ai/client/js/api-reference/client-methods)
- [Pipecat Callbacks Reference](https://docs.pipecat.ai/client/js/api-reference/callbacks)
- [SmallWebRTCTransport](https://docs.pipecat.ai/client/js/transports/small-webrtc)
- [Electron Documentation](https://www.electronjs.org/docs)
- [Vite Documentation](https://vitejs.dev/)
