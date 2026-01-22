class LoadingManager {
    constructor() {
        this.processes = new Map();
        this.loadingOverlay = document.getElementById('loading-overlay');
        this.loadingMessage = document.getElementById('loading-message');
        this.loadingProcesses = document.getElementById('loading-processes');
        this.allProcessesReady = false;
        this.voiceTimeoutId = null;
        this.voiceTimeoutStarted = false;
    }

    init() {
        console.log('[LOADING] Initializing LoadingManager');
        this.addProcess('electron', 'electron main.js');
        this.addProcess('setup-uv', 'Verification de uv');
        this.addProcess('setup-python', 'Installation de Python');
        this.addProcess('setup-sync', 'Installation des dependances');
        this.addProcess('starting-pipecat', 'Demarrage du backend Pipecat');
        this.addProcess('loading-smart-turn', 'Loading Local Smart Turn Analyzer V3');
        this.addProcess('loading-silero', 'Loading Silero VAD Model');
        this.addProcess('start-server', 'Start server process');
        this.addProcess('starting-server', 'Starting Pipecat server');
        this.addProcess('loading-models', 'Loading models and imports');
        this.addProcess('testing-webrtc', 'Testing WebRTC server');
        
        console.log('[LOADING] Processes added:', Array.from(this.processes.keys()));
        console.log('[LOADING] electronAPI available?', !!window.electronAPI);
        console.log('[LOADING] onLoadingProcess available?', !!(window.electronAPI && window.electronAPI.onLoadingProcess));
        
        if (window.electronAPI && window.electronAPI.onLoadingProcess) {
            window.electronAPI.onLoadingProcess((processName, status, detail) => {
                console.log('[LOADING] IPC Process update received:', processName, status, detail);
                this.updateProcess(processName, status, detail);
            });
        } else {
            console.warn('[LOADING] electronAPI.onLoadingProcess not available');
        }
    }

    translateDetail(detail) {
        if (!detail) return null;
        let t = detail;
        if (t.includes('Uvicorn running on')) t = t.replace('Uvicorn running on', 'Uvicorn en cours d\'execution sur');
        if (t.includes('Local Smart Turn Analyzer V3 loaded')) return 'Local Smart Turn Analyzer V3 charge';
        if (t.includes('Silero VAD model loaded')) return 'Modele Silero VAD charge';
        if (t.includes('Application startup complete')) return 'Demarrage de l\'application termine';
        if (t === 'uv pret' || t === 'Python installe' || t === 'Dependances installees') return t;
        if (t.includes('Verification de uv')) return t;
        if (t.includes('Installation de Python')) return t;
        if (t.includes('Installation des dependances')) return t;
        return t;
    }

    addProcess(name, label) {
        const process = {
            name,
            label,
            status: 'pending'
        };
        this.processes.set(name, process);
        this.renderProcess(process);
    }

    updateProcess(name, status, detail = null) {
        const process = this.processes.get(name);
        if (process) {
            const oldStatus = process.status;
            process.status = status;
            if (detail) {
                process.label = this.translateDetail(detail) || detail;
            }
            console.log(`[LOADING] Updating ${name}: ${oldStatus} -> ${status} (${detail || 'no detail'})`);
            console.log(`[LOADING] All processes status:`, Array.from(this.processes.entries()).map(([n, p]) => `${n}:${p.status}`).join(', '));
            this.renderProcess(process);
            
            if (name === 'testing-webrtc' && status === 'completed') {
                console.log('[LOADING] WebRTC is ready, closing overlay immediately');
                if (!this.allProcessesReady) {
                    this.allProcessesReady = true;
                    if (this.voiceTimeoutId) {
                        clearTimeout(this.voiceTimeoutId);
                        this.voiceTimeoutId = null;
                    }
                    setTimeout(() => {
                        this.hide();
                    }, 200);
                }
            }
            
            this.checkAllReady();
        } else {
            console.warn(`[LOADING] Process ${name} not found, available processes:`, Array.from(this.processes.keys()));
        }
    }

    renderProcess(process) {
        const activeProcess = Array.from(this.processes.values()).find(p => p.status === 'active');
        
        if (!activeProcess) {
            const pendingProcess = Array.from(this.processes.values()).find(p => p.status === 'pending');
            if (pendingProcess && pendingProcess.name === process.name) {
                return;
            }
            if (process.status === 'pending') {
                return;
            }
        } else if (process.name !== activeProcess.name && process.status !== 'active') {
            return;
        }

        const processToShow = activeProcess || process;
        
        let processEl = document.getElementById(`loading-process-current`);
        
        if (!processEl) {
            processEl = document.createElement('div');
            processEl.id = `loading-process-current`;
            processEl.className = 'loading-process';
            const spinnerEl = document.createElement('div');
            spinnerEl.className = 'loading-process-icon loading-process-spinner';
            const checkEl = document.createElement('div');
            checkEl.className = 'loading-process-icon loading-process-check';
            checkEl.textContent = '\u2713';
            const textEl = document.createElement('div');
            textEl.className = 'loading-process-text';
            const iconWrap = document.createElement('div');
            iconWrap.className = 'loading-process-icon-wrap';
            iconWrap.appendChild(spinnerEl);
            iconWrap.appendChild(checkEl);
            processEl.appendChild(iconWrap);
            processEl.appendChild(textEl);
            this.loadingProcesses.innerHTML = '';
            this.loadingProcesses.appendChild(processEl);
        }

        const iconWrap = processEl.querySelector('.loading-process-icon-wrap');
        const spinnerEl = processEl.querySelector('.loading-process-spinner');
        const checkEl = processEl.querySelector('.loading-process-check');
        const textEl = processEl.querySelector('.loading-process-text');
        textEl.textContent = processToShow.label;

        processEl.className = 'loading-process';
        spinnerEl.style.display = 'none';
        checkEl.style.display = 'none';
        
        if (processToShow.status === 'active') {
            processEl.classList.add('active');
            spinnerEl.style.display = '';
            this.loadingMessage.textContent = processToShow.label;
        } else if (processToShow.status === 'completed') {
            processEl.classList.add('completed');
            checkEl.style.display = '';
            this.loadingMessage.textContent = processToShow.label;
        }

        if (!iconWrap.parentElement) {
            processEl.insertBefore(iconWrap, textEl);
        }
    }

    checkAllReady() {
        const webrtcProcess = this.processes.get('testing-webrtc');
        const allCompleted = Array.from(this.processes.values()).every(p => p.status === 'completed');
        const statuses = Array.from(this.processes.values()).map(p => `${p.name}:${p.status}`).join(', ');
        console.log(`[LOADING] Checking if all ready: ${allCompleted} (${statuses})`);
        console.log(`[LOADING] allProcessesReady flag: ${this.allProcessesReady}`);
        console.log(`[LOADING] WebRTC status: ${webrtcProcess ? webrtcProcess.status : 'not found'}`);
        
        if (webrtcProcess && webrtcProcess.status === 'completed' && !this.allProcessesReady) {
            console.log('[LOADING] WebRTC is completed, closing overlay NOW');
            this.allProcessesReady = true;
            if (this.voiceTimeoutId) {
                clearTimeout(this.voiceTimeoutId);
                this.voiceTimeoutId = null;
            }
            setTimeout(() => {
                this.hide();
            }, 100);
        } else if (allCompleted && !this.allProcessesReady) {
            this.allProcessesReady = true;
            if (this.voiceTimeoutId) {
                clearTimeout(this.voiceTimeoutId);
                this.voiceTimeoutId = null;
            }
            console.log('[LOADING] All processes completed, hiding overlay');
            this.hide();
        } else if (!allCompleted) {
            const missing = Array.from(this.processes.values())
                .filter(p => p.status !== 'completed')
                .map(p => `${p.name}:${p.status}`);
            console.log(`[LOADING] Not all ready yet. Missing:`, missing.join(', '));
            
            const webrtcProcess = this.processes.get('testing-webrtc');
            if (webrtcProcess && webrtcProcess.status === 'active' && !this.voiceTimeoutStarted) {
                this.voiceTimeoutStarted = true;
                console.log('[LOADING] WebRTC process is active, starting 5s timeout to force complete');
                this.voiceTimeoutId = setTimeout(() => {
                    const wp = this.processes.get('testing-webrtc');
                    if (wp && wp.status !== 'completed') {
                        console.log('[LOADING] TIMEOUT: Force completing WebRTC process');
                        this.updateProcess('testing-webrtc', 'completed', 'PipecatClient - Connecté');
                    }
                    this.voiceTimeoutId = null;
                    this.voiceTimeoutStarted = false;
                }, 5000);
            }
            
            const allButWebRTC = Array.from(this.processes.entries())
                .filter(([name]) => name !== 'testing-webrtc')
                .every(([, p]) => p.status === 'completed');
            
            if (allButWebRTC && webrtcProcess && webrtcProcess.status === 'completed') {
                console.log('[LOADING] All processes including WebRTC are completed');
                if (!this.allProcessesReady) {
                    this.allProcessesReady = true;
                    console.log('[LOADING] Hiding overlay immediately');
                    setTimeout(() => {
                        this.hide();
                    }, 300);
                }
            }
        }
    }

    hide() {
        console.log('[LOADING] hide() called');
        if (this.loadingOverlay) {
            console.log('[LOADING] Hiding overlay immediately');
            this.loadingOverlay.style.opacity = '0';
            this.loadingOverlay.style.pointerEvents = 'none';
            this.loadingOverlay.classList.add('hidden');
            this.loadingOverlay.style.display = 'none';
            this.loadingOverlay.style.visibility = 'hidden';
            console.log('[LOADING] Overlay hidden');
        } else {
            console.warn('[LOADING] loadingOverlay not found');
        }
    }
}

const loadingManager = new LoadingManager();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        loadingManager.init();
        loadingManager.updateProcess('electron', 'completed');
    });
} else {
    loadingManager.init();
    loadingManager.updateProcess('electron', 'completed');
}

window.loadingManager = loadingManager;
