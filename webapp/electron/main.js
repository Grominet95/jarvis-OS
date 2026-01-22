const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const db = require('./database');

function findPipecatModulesPath() {
  const projectRoot = path.join(__dirname, '..');
  const venvPaths = [
    path.join(projectRoot, '.venv', 'Lib', 'site-packages'),
    path.join(projectRoot, '.venv', 'lib', 'site-packages')
  ];

  const searchInDirectory = (dir, filename) => {
    if (!fs.existsSync(dir)) return null;

    try {
      const files = fs.readdirSync(dir, { recursive: true, withFileTypes: true });
      for (const file of files) {
        if (file.isFile() && file.name === filename) {
          const fullPath = path.join(file.path || dir, file.name);
          return fullPath;
        }
      }
    } catch (error) {
      console.warn(`Error searching in ${dir}:`, error.message);
    }
    return null;
  };

  for (const venvPath of venvPaths) {
    if (fs.existsSync(venvPath)) {
      const searchPath = path.join(venvPath, 'pipecat_ai_small_webrtc_prebuilt');
      if (fs.existsSync(searchPath)) {
        const distPath = path.join(searchPath, 'client', 'dist', 'pipecat-small-webrtc-client.js');
        if (fs.existsSync(distPath)) {
          return distPath;
        }
        const found = searchInDirectory(searchPath, 'pipecat-small-webrtc-client.js');
        if (found) return found;
      }

      const found = searchInDirectory(venvPath, 'pipecat-small-webrtc-client.js');
      if (found) return found;
    }
  }

  const pythonPaths = [
    process.env.PYTHONPATH,
    process.env.PYTHONHOME ? path.join(process.env.PYTHONHOME, 'Lib', 'site-packages') : null,
    'C:\\Program Files\\Python313\\Lib\\site-packages'
  ].filter(Boolean);

  for (const pythonPath of pythonPaths) {
    if (pythonPath && fs.existsSync(pythonPath)) {
      const modulePath = path.join(pythonPath, 'pipecat_ai_small_webrtc_prebuilt', 'client', 'dist', 'pipecat-small-webrtc-client.js');
      if (fs.existsSync(modulePath)) {
        return modulePath;
      }
      const found = searchInDirectory(pythonPath, 'pipecat-small-webrtc-client.js');
      if (found) return found;
    }
  }

  return null;
}

let mainWindow;
let botProcess = null;
const BOT_PORT = 7860;
const BOT_URL = `http://localhost:${BOT_PORT}/client`;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1300,
    height: 700,
    minWidth: 1300,
    maxWidth: 1300,
    minHeight: 700,
    maxHeight: 700,
    frame: false,
    resizable: false,
    transparent: true,
    roundedCorners: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: false
    },
    backgroundColor: '#00000000',
    icon: path.join(__dirname, '..', 'assets', 'icon.png')
  });

  const staticPath = path.join(__dirname, '..', 'statics', 'src', 'index.html');
  if (fs.existsSync(staticPath)) {
    mainWindow.loadFile(staticPath, {
      query: { basePath: path.join(__dirname, '..', 'statics', 'src').replace(/\\/g, '/') }
    });
  } else {
    mainWindow.loadFile(path.join(__dirname, 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.on('did-finish-load', () => {
    console.log('[PIPECAT] Window loaded, modules will be loaded from server once ready');
  });
}

function checkPortAvailable(port) {
  return new Promise((resolve) => {
    const server = http.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on('error', () => resolve(false));
  });
}

function checkServer(url, maxAttempts = 30, interval = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const check = () => {
      attempts++;
      const baseUrl = url.replace('/client', '');
      const req = http.get(baseUrl, (res) => {
        if (res.statusCode === 200 || res.statusCode === 404 || res.statusCode === 307 || res.statusCode === 308) {
          resolve(true);
        } else {
          if (attempts < maxAttempts) {
            setTimeout(check, interval);
          } else {
            reject(new Error('Server did not respond in time'));
          }
        }
      });

      req.on('error', (err) => {
        if (attempts < maxAttempts) {
          setTimeout(check, interval);
        } else {
          reject(new Error('Server not available'));
        }
      });

      req.setTimeout(1000, () => {
        req.destroy();
        if (attempts < maxAttempts) {
          setTimeout(check, interval);
        } else {
          reject(new Error('Server timeout'));
        }
      });
    };

    check();
  });
}

function createEnvFile() {
  const envPath = path.join(__dirname, '..', '.env');
  const apiKeys = db.getAllApiKeys();
  
  const envContent = [
    `DEEPGRAM_API_KEY=${apiKeys.deepgram || ''}`,
    `OPENAI_API_KEY=${apiKeys.openai || ''}`,
    `CARTESIA_API_KEY=${apiKeys.cartesia || ''}`
  ].join('\n');
  
  fs.writeFileSync(envPath, envContent, 'utf8');
  console.log('[MAIN] .env file created/updated with API keys from database');
}

function startBot() {
  return new Promise(async (resolve, reject) => {
    const portAvailable = await checkPortAvailable(BOT_PORT);
    if (!portAvailable) {
      reject(new Error(`Port ${BOT_PORT} is already in use. Please stop any other instance of the bot.`));
      return;
    }

    createEnvFile();

    const isWindows = process.platform === 'win32';
    const scriptPath = path.join(__dirname, '..', 'start_bot.py');

    if (!fs.existsSync(scriptPath)) {
      reject(new Error('start_bot.py not found'));
      return;
    }

    const pythonCmd = isWindows ? 'python' : 'python3';

    botProcess = spawn(pythonCmd, [scriptPath], {
      cwd: path.join(__dirname, '..'),
      stdio: 'pipe',
      shell: isWindows,
      env: { ...process.env }
    });

    let errorOutput = '';
    let hasStarted = false;

    botProcess.stderr.on('data', (data) => {
      const output = data.toString();
      errorOutput += output;
      if (mainWindow) {
        mainWindow.webContents.send('bot-output', output);
      }
    });

    botProcess.stdout.on('data', (data) => {
      const output = data.toString();
      if (mainWindow) {
        mainWindow.webContents.send('bot-output', output);
      }

      if (output.includes('Loading Local Smart Turn Analyzer V3')) {
        sendLoadingProcess('loading-smart-turn', 'active', 'Loading Local Smart Turn Analyzer V3');
      }
      if (output.includes('Local Smart Turn Analyzer V3 loaded')) {
        sendLoadingProcess('loading-smart-turn', 'completed', 'Local Smart Turn Analyzer V3 loaded');
      }
      if (output.includes('Loading Silero VAD model')) {
        sendLoadingProcess('loading-silero', 'active', 'Loading Silero VAD model');
      }
      if (output.includes('Silero VAD model loaded')) {
        sendLoadingProcess('loading-silero', 'completed', 'Silero VAD model loaded');
      }
      if (output.includes('Starting server') || output.includes('Uvicorn running')) {
        sendLoadingProcess('starting-server', 'active', 'Starting Pipecat server');
      }
      if (output.includes('Application startup complete')) {
        sendLoadingProcess('starting-server', 'completed', 'Server started');
      }
      if (output.includes('Bot ready') || output.includes('localhost:7860')) {
        hasStarted = true;
        sendLoadingProcess('testing-webrtc', 'active', 'Testing WebRTC server');
        setTimeout(() => {
          sendLoadingProcess('testing-webrtc', 'completed', 'WebRTC server ready');
          sendBackendReady();
        }, 1000);
      }
    });

    botProcess.on('error', (error) => {
      reject(error);
    });

    botProcess.on('exit', (code) => {
      if (code !== 0 && code !== null && !hasStarted) {
        reject(new Error(`Bot process exited with code ${code}: ${errorOutput.substring(0, 200)}`));
      }
    });

    const checkInterval = setInterval(() => {
      checkServer(BOT_URL, 1, 100)
        .then(() => {
          clearInterval(checkInterval);
          hasStarted = true;
          resolve();
        })
        .catch(() => {
        });
    }, 1000);

    setTimeout(() => {
      clearInterval(checkInterval);
      if (!hasStarted) {
        checkServer(BOT_URL)
          .then(() => {
            hasStarted = true;
            resolve();
          })
          .catch((err) => {
            if (!hasStarted) {
              reject(new Error('Bot server did not start in time'));
            }
          });
      }
    }, 30000);
  });
}

function stopBot() {
  if (botProcess) {
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', botProcess.pid, '/F', '/T'], { stdio: 'ignore' });
      } else {
        botProcess.kill('SIGTERM');
        setTimeout(() => {
          if (botProcess && !botProcess.killed) {
            botProcess.kill('SIGKILL');
          }
        }, 5000);
      }
    } catch (error) {
      console.error('Error stopping bot:', error);
    }
    botProcess = null;
  }
}

app.whenReady().then(() => {
  console.log('[MAIN] App ready, initializing database...');
  try {
    db.getDatabase();
    console.log('[MAIN] Database initialized');
  } catch (error) {
    console.error('[MAIN] Error initializing database:', error);
  }
  createWindow();

  setTimeout(async () => {
    try {
      sendLoadingProcess('starting-pipecat', 'active', 'Starting Pipecat backend...');
      await startBot();
      sendLoadingProcess('starting-pipecat', 'completed', 'Pipecat backend started');
    } catch (error) {
      sendLoadingProcess('starting-pipecat', 'error', error.message);
      console.error('Auto-start bot failed:', error);
    }
  }, 1000);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  stopBot();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopBot();
});

ipcMain.handle('start-bot', async () => {
  try {
    await startBot();
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('stop-bot', async () => {
  try {
    stopBot();
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('check-server', async () => {
  try {
    await checkServer(BOT_URL, 1, 100);
    return { success: true };
  } catch (error) {
    return { success: false };
  }
});

ipcMain.handle('open-browser', async () => {
  if (mainWindow) {
    mainWindow.loadURL(BOT_URL);
    return { success: true };
  }
  return { success: false };
});

ipcMain.handle('get-env', async (event, key) => {
  return process.env[key] || null;
});

ipcMain.handle('get-mic-permission', async () => {
  return 'granted';
});

ipcMain.handle('request-mic-permission', async () => {
  return true;
});

ipcMain.handle('get-setting', async (event, key) => {
  return db.getSetting(key);
});

ipcMain.handle('set-setting', async (event, key, value) => {
  return db.setSetting(key, value);
});

ipcMain.handle('get-user-profile', async () => {
  return db.getUserProfile();
});

ipcMain.handle('update-user-profile', async (event, profile) => {
  return db.updateUserProfile(profile);
});

ipcMain.handle('get-api-key', async (event, service) => {
  return db.getApiKey(service);
});

ipcMain.handle('set-api-key', async (event, service, apiKey) => {
  return db.setApiKey(service, apiKey);
});

ipcMain.handle('get-all-api-keys', async () => {
  return db.getAllApiKeys();
});

ipcMain.handle('is-first-install', async () => {
  return db.isFirstInstall();
});

ipcMain.handle('minimize-window', async () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

ipcMain.handle('close-window', async () => {
  if (mainWindow) {
    mainWindow.close();
  }
});

ipcMain.handle('load-pipecat-modules', async () => {
  return { success: false, error: 'Modules must be loaded from the HTTP server' };
});

function sendLoadingProcess(processName, status, detail) {
  if (mainWindow) {
    mainWindow.webContents.send('loading-process', processName, status, detail);
  }
}

function sendPipecatEvent(eventName, data) {
  if (mainWindow) {
    mainWindow.webContents.send('pipecat-event', eventName, data);
  }
}

function sendBackendReady() {
  if (mainWindow) {
    mainWindow.webContents.send('backend-ready');
  }
}
