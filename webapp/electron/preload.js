const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  startBot: () => ipcRenderer.invoke('start-bot'),
  stopBot: () => ipcRenderer.invoke('stop-bot'),
  checkServer: () => ipcRenderer.invoke('check-server'),
  openBrowser: () => ipcRenderer.invoke('open-browser'),
  onBotOutput: (callback) => {
    ipcRenderer.on('bot-output', (event, data) => callback(data));
  },
  onLoadingProcess: (callback) => {
    ipcRenderer.on('loading-process', (event, processName, status, detail) => {
      callback(processName, status, detail);
    });
  },
  onPipecatEvent: (callback) => {
    window._pipecatEventCallback = callback;
    ipcRenderer.on('pipecat-event', (event, eventName, data) => {
      callback(eventName, data);
    });
  },
  removePipecatEventListeners: () => {
    ipcRenderer.removeAllListeners('pipecat-event');
  },
  onBackendReady: (callback) => {
    ipcRenderer.on('backend-ready', () => callback());
  },
  getEnv: (key) => ipcRenderer.invoke('get-env', key),
  getMicPermission: () => ipcRenderer.invoke('get-mic-permission'),
  requestMicPermission: () => ipcRenderer.invoke('request-mic-permission'),
  getSetting: (key) => ipcRenderer.invoke('get-setting', key),
  setSetting: (key, value) => ipcRenderer.invoke('set-setting', key, value),
  getUserProfile: () => ipcRenderer.invoke('get-user-profile'),
  updateUserProfile: (profile) => ipcRenderer.invoke('update-user-profile', profile),
  getApiKey: (service) => ipcRenderer.invoke('get-api-key', service),
  setApiKey: (service, apiKey) => ipcRenderer.invoke('set-api-key', service, apiKey),
  getAllApiKeys: () => ipcRenderer.invoke('get-all-api-keys'),
  isFirstInstall: () => ipcRenderer.invoke('is-first-install'),
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
  closeWindow: () => ipcRenderer.invoke('close-window'),
  loadPipecatModules: () => ipcRenderer.invoke('load-pipecat-modules')
});
