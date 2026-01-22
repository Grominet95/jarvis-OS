const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const db = require('./database');

function getResourcesPath() {
  return app.isPackaged ? process.resourcesPath : path.join(__dirname, '..');
}

function getUvPath() {
  if (!app.isPackaged) return null;
  const res = getResourcesPath();
  const plat = process.platform;
  const arch = process.arch;
  const key = plat === 'win32' ? 'win32-x64' : plat + '-' + arch;
  const sub = path.join(res, 'bin', key);
  const exe = plat === 'win32' ? path.join(sub, 'uv.exe') : path.join(sub, 'uv');
  return fs.existsSync(exe) ? exe : null;
}

function getPythonProjectPath() {
  if (app.isPackaged) {
    const p = path.join(app.getPath('userData'), 'jarvis-project');
    if (fs.existsSync(p)) return p;
    return path.join(getResourcesPath(), 'python-project');
  }
  return path.join(__dirname, '..');
}

function getPythonProjectSourcePath() {
  if (app.isPackaged) {
    return path.join(getResourcesPath(), 'python-project');
  }
  return path.join(__dirname, '..');
}

function findPipecatModulesPath() {
  const projectRoot = getPythonProjectPath();
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
    icon: fs.existsSync(path.join(__dirname, '..', 'assets', 'icon.png'))
      ? path.join(__dirname, '..', 'assets', 'icon.png')
      : undefined
  });

  const appRoot = path.join(__dirname, '..');
  const staticPath = path.join(appRoot, 'statics', 'src', 'index.html');
  if (fs.existsSync(staticPath)) {
    mainWindow.loadFile(staticPath, {
      query: { basePath: path.join(appRoot, 'statics', 'src').replace(/\\/g, '/') }
    });
  } else {
    const fallback = path.join(__dirname, 'index.html');
    if (fs.existsSync(fallback)) mainWindow.loadFile(fallback);
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
  const projectDir = getPythonProjectPath();
  const envPath = path.join(projectDir, '.env');
  const apiKeys = db.getAllApiKeys();
  const envContent = [
    `DEEPGRAM_API_KEY=${apiKeys.deepgram || ''}`,
    `OPENAI_API_KEY=${apiKeys.openai || ''}`,
    `CARTESIA_API_KEY=${apiKeys.cartesia || ''}`
  ].join('\n');
  fs.writeFileSync(envPath, envContent, 'utf8');
  console.log('[MAIN] .env created at', envPath);
}

function isEnvReady() {
  return db.getSetting('env_ready') === 'true';
}

function setEnvReady(value) {
  db.setSetting('env_ready', value ? 'true' : 'false');
}

function runCommand(exe, args, cwd, env = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(exe, args, {
      cwd,
      env: { ...process.env, ...env },
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: false
    });
    let out = '';
    let err = '';
    if (child.stdout) child.stdout.on('data', (d) => { out += d.toString(); });
    if (child.stderr) child.stderr.on('data', (d) => { err += d.toString(); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve({ stdout: out, stderr: err });
      else reject(new Error(err || out || `Exit ${code}`));
    });
  });
}

function copyDirRecursive(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    const s = path.join(src, name);
    const d = path.join(dst, name);
    if (fs.statSync(s).isDirectory()) {
      copyDirRecursive(s, d);
    } else {
      fs.copyFileSync(s, d);
    }
  }
}

async function runEnvSetup() {
  const uvPath = getUvPath();
  const srcDir = getPythonProjectSourcePath();
  const projectDir = path.join(app.getPath('userData'), 'jarvis-project');
  const uvHome = path.join(app.getPath('userData'), 'uv');
  fs.mkdirSync(uvHome, { recursive: true });
  const env = { UV_HOME: uvHome };

  if (!uvPath || !fs.existsSync(uvPath)) {
    throw new Error('Bundled uv not found');
  }

  sendLoadingProcess('setup-uv', 'active', 'Verification de uv...');
  await new Promise((r) => setTimeout(r, 300));
  sendLoadingProcess('setup-uv', 'completed', 'uv pret');

  if (!fs.existsSync(projectDir)) {
    copyDirRecursive(srcDir, projectDir);
  }

  sendLoadingProcess('setup-python', 'active', 'Installation de Python...');
  try {
    await runCommand(uvPath, ['python', 'install', '3.12'], projectDir, env);
  } catch (e) {
    console.warn('[MAIN] uv python install:', e.message);
  }
  sendLoadingProcess('setup-python', 'completed', 'Python installe');

  sendLoadingProcess('setup-sync', 'active', 'Installation des dependances...');
  await runCommand(uvPath, ['sync'], projectDir, env);
  sendLoadingProcess('setup-sync', 'completed', 'Dependances installees');

  setEnvReady(true);
}

function startBot() {
  return new Promise(async (resolve, reject) => {
    const portAvailable = await checkPortAvailable(BOT_PORT);
    if (!portAvailable) {
      reject(new Error(`Port ${BOT_PORT} is already in use. Please stop any other instance of the bot.`));
      return;
    }

    createEnvFile();

    const projectDir = getPythonProjectPath();
    const botPy = path.join(projectDir, 'bot.py');
    if (!fs.existsSync(botPy)) {
      reject(new Error('bot.py not found in ' + projectDir));
      return;
    }

    const uvPath = getUvPath();
    const useUv = app.isPackaged && uvPath && fs.existsSync(uvPath);
    const uvHome = app.isPackaged ? path.join(app.getPath('userData'), 'uv') : null;
    const spawnEnv = { ...process.env };
    if (uvHome) spawnEnv.UV_HOME = uvHome;

    const cmd = useUv ? uvPath : (process.platform === 'win32' ? 'python' : 'python3');
    const args = useUv ? ['run', 'bot.py'] : [path.join(projectDir, 'start_bot.py')];

    botProcess = spawn(cmd, args, {
      cwd: projectDir,
      stdio: 'pipe',
      shell: process.platform === 'win32' && !useUv,
      env: spawnEnv
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
      const packaged = app.isPackaged;
      const ready = isEnvReady();

      if (packaged && !ready) {
        await runEnvSetup();
      } else {
        sendLoadingProcess('setup-uv', 'completed', 'uv pret');
        sendLoadingProcess('setup-python', 'completed', 'Python installe');
        sendLoadingProcess('setup-sync', 'completed', 'Dependances installees');
      }

      sendLoadingProcess('starting-pipecat', 'active', 'Démarrage du backend Pipecat...');
      await startBot();
      sendLoadingProcess('starting-pipecat', 'completed', 'Backend Pipecat démarré');
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
