// Use require to avoid Rollup transformation issues with Electron
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { app, BrowserWindow, ipcMain, systemPreferences } = require('electron');
// eslint-disable-next-line @typescript-eslint/no-var-requires
const path = require('path');

// Type imports for TypeScript
import type { BrowserWindow as BrowserWindowType } from 'electron';

// Disable hardware acceleration if needed for WebRTC compatibility
// app.disableHardwareAcceleration();

let mainWindow: BrowserWindowType | null = null;

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

function createWindow(): void {
  const win = new BrowserWindow({
    width: 800,
    height: 600,
    minWidth: 400,
    minHeight: 400,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // Required for some WebRTC features
    },
    title: 'Pipecat Voice Chat',
    backgroundColor: '#1a1a2e',
  });

  mainWindow = win;

  // Load the app
  if (isDev) {
    win.loadURL('http://localhost:5173');
    win.webContents.openDevTools();
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  win.on('closed', () => {
    mainWindow = null;
  });

  // Handle permission requests for microphone
  win.webContents.session.setPermissionRequestHandler(
    (_webContents: unknown, permission: string, callback: (granted: boolean) => void) => {
      const allowedPermissions = ['media', 'microphone', 'camera'];
      if (allowedPermissions.includes(permission)) {
        callback(true);
      } else {
        callback(false);
      }
    }
  );
}

// Request microphone permission on macOS
async function requestMicrophonePermission(): Promise<boolean> {
  if (process.platform === 'darwin') {
    const status = systemPreferences.getMediaAccessStatus('microphone');
    if (status === 'not-determined') {
      const granted = await systemPreferences.askForMediaAccess('microphone');
      return granted;
    }
    return status === 'granted';
  }
  // On Windows/Linux, permissions are handled differently
  return true;
}

// App lifecycle
app.whenReady().then(async () => {
  // Request mic permission before creating window
  const micGranted = await requestMicrophonePermission();
  console.log(`Microphone permission: ${micGranted ? 'granted' : 'denied'}`);

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// IPC Handlers

// Get microphone permission status
ipcMain.handle('get-mic-permission', async () => {
  if (process.platform === 'darwin') {
    return systemPreferences.getMediaAccessStatus('microphone');
  }
  return 'granted'; // Assume granted on non-macOS
});

// Request microphone permission
ipcMain.handle('request-mic-permission', async () => {
  return await requestMicrophonePermission();
});

// Get environment variables (safe ones only)
ipcMain.handle('get-env', (_event: unknown, key: string) => {
  const allowedKeys = [
    'VITE_PIPECAT_URL',
    'VITE_TRANSPORT_TYPE',
    'VITE_DAILY_ROOM_URL',
    // Note: VITE_DAILY_TOKEN should NOT be exposed to renderer in production
    // For dev purposes only
  ];
  if (allowedKeys.includes(key)) {
    return process.env[key] || null;
  }
  return null;
});

// Log from renderer
ipcMain.on('log', (_event: unknown, level: string, message: string) => {
  const timestamp = new Date().toISOString();
  switch (level) {
    case 'error':
      console.error(`[${timestamp}] [RENDERER] ${message}`);
      break;
    case 'warn':
      console.warn(`[${timestamp}] [RENDERER] ${message}`);
      break;
    default:
      console.log(`[${timestamp}] [RENDERER] ${message}`);
  }
});
