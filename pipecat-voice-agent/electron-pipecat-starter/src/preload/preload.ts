import { contextBridge, ipcRenderer } from 'electron';

/**
 * Preload script - exposes a minimal, secure API to the renderer process.
 * contextIsolation = true, nodeIntegration = false
 */

export interface ElectronAPI {
  // Microphone permissions
  getMicPermission: () => Promise<string>;
  requestMicPermission: () => Promise<boolean>;

  // Environment variables (safe ones only)
  getEnv: (key: string) => Promise<string | null>;

  // Logging to main process
  log: (level: 'info' | 'warn' | 'error', message: string) => void;

  // Platform info
  platform: NodeJS.Platform;
}

const electronAPI: ElectronAPI = {
  getMicPermission: () => ipcRenderer.invoke('get-mic-permission'),
  requestMicPermission: () => ipcRenderer.invoke('request-mic-permission'),
  getEnv: (key: string) => ipcRenderer.invoke('get-env', key),
  log: (level: 'info' | 'warn' | 'error', message: string) => {
    ipcRenderer.send('log', level, message);
  },
  platform: process.platform,
};

// Expose the API to the renderer process
contextBridge.exposeInMainWorld('electronAPI', electronAPI);
