class VoiceManager {
    constructor() {
        this.adapter = null;
        this.connectionState = 'disconnected';
        this.isMicEnabled = false;
        this.isBotSpeaking = false;
        this.isUserSpeaking = false;
        this.localAudioLevel = 0;
        this.remoteAudioLevel = 0;
        this.userTranscript = '';
        this.botTranscript = '';
        this.config = {
            pipecatUrl: 'http://localhost:7860/api/offer',
            transportType: 'small-webrtc',
            enableMic: true
        };
        this.selectedDevices = {
            input: null,
            output: null
        };
    }

    async init() {
        try {
            if (window.electronAPI) {
                const pipecatUrl = await window.electronAPI.getEnv('VITE_PIPECAT_URL');
                if (pipecatUrl) {
                    this.config.pipecatUrl = pipecatUrl;
                }
            }

            await this.checkMicrophonePermission();
        } catch (error) {
            console.error('Error initializing voice manager:', error);
        }
    }

    async checkMicrophonePermission() {
        if (window.electronAPI) {
            try {
                const status = await window.electronAPI.getMicPermission();
                if (status !== 'granted') {
                    const granted = await window.electronAPI.requestMicPermission();
                    if (!granted) {
                        console.warn('Microphone permission not granted');
                    }
                }
            } catch (error) {
                console.error('Error checking microphone permission:', error);
            }
        }
    }


    async connect() {
        console.log('[VOICE] connect() called, current state:', this.connectionState);
        if (this.connectionState === 'connected' || this.connectionState === 'connecting') {
            console.log('[VOICE] Already connected/connecting, skipping');
            return;
        }
        
        if (!window.pipecatModules) {
            console.log('[VOICE] Waiting for pipecat modules to load...');
            await new Promise((resolve) => {
                const checkModules = () => {
                    if (window.pipecatModules) {
                        console.log('[VOICE] Modules now available');
                        resolve();
                    } else {
                        setTimeout(checkModules, 500);
                    }
                };
                window.addEventListener('pipecat-modules-loaded', resolve, { once: true });
                setTimeout(checkModules, 100);
            });
        }
        
        try {
            console.log('[VOICE] Starting connection process...');
            if (window.loadingManager) {
                window.loadingManager.updateProcess('testing-webrtc', 'active', 'Testing WebRTC server (Connexion en cours...)');
            }

            if (!window.PipecatAdapter) {
                throw new Error('PipecatAdapter not available');
            }
            
            if (!window.pipecatModules) {
                throw new Error('Pipecat modules not available');
            }

            const pipecatUrl = this.config.pipecatUrl;
            
            this.adapter = new PipecatAdapter(
                {
                    transportType: this.config.transportType,
                    webrtcUrl: pipecatUrl,
                    enableMic: true
                },
                {
                    onStateChange: (state) => {
                        this.connectionState = state;
                        if (state === 'connected' && this.adapter) {
                            this.isMicEnabled = this.adapter.isMicEnabled;
                            console.log('[VOICE] State changed to connected, isMicEnabled:', this.isMicEnabled);
                            
                            const chatContainer = document.getElementById('chat-container');
                            if (chatContainer) {
                                const connectedMsg = document.createElement('div');
                                connectedMsg.className = 'message system-message';
                                connectedMsg.innerHTML = '<p>Connexion établie avec succès. Vous pouvez maintenant parler.</p>';
                                chatContainer.appendChild(connectedMsg);
                                chatContainer.scrollTop = chatContainer.scrollHeight;
                            }
                        }
                        this.updateConnectionUI();
                        if (state === 'connected' && window.loadingManager) {
                            window.loadingManager.updateProcess('testing-webrtc', 'completed', 'PipecatClient - Connecté');
                        }
                        if (state === 'connected') {
                            setTimeout(async () => {
                                console.log('[VOICE] Connection state changed to connected, setting up audio output...');
                                await this.setAudioOutputDevice();
                            }, 500);
                        }
                    },
                    onLocalAudioLevel: (level) => {
                        this.localAudioLevel = level;
                        this.updateVisualizer();
                    },
                    onRemoteAudioLevel: (level) => {
                        this.remoteAudioLevel = level;
                        this.updateVisualizer();
                    },
                    onBotStartedSpeaking: () => {
                        this.isBotSpeaking = true;
                        this.updateVisualizer();
                    },
                    onBotStoppedSpeaking: () => {
                        this.isBotSpeaking = false;
                        this.remoteAudioLevel = 0;
                        const chatContainer = document.getElementById('chat-container');
                        if (chatContainer) {
                            const streamingMessage = chatContainer.querySelector('.assistant-message.streaming');
                            if (streamingMessage) {
                                streamingMessage.classList.remove('streaming');
                                const messageText = streamingMessage.querySelector('p');
                                if (messageText && this.botTranscript.trim()) {
                                    messageText.textContent = this.botTranscript.trim();
                                }
                            }
                        }
                        this.flushBotTranscript();
                        this.updateVisualizer();
                    },
                    onUserStartedSpeaking: () => {
                        this.isUserSpeaking = true;
                        this.updateVisualizer();
                    },
                    onUserStoppedSpeaking: () => {
                        this.isUserSpeaking = false;
                        this.flushUserTranscript();
                        this.updateVisualizer();
                    },
                    onUserTranscript: (text, isFinal) => {
                        console.log('[VOICE] onUserTranscript called:', text, 'final:', isFinal);
                        if (text && text.trim()) {
                            if (this.userTranscript && !this.userTranscript.endsWith(' ') && !text.startsWith(' ')) {
                                this.userTranscript += ' ';
                            }
                            this.userTranscript += text;
                            if (isFinal) {
                                this.flushUserTranscript();
                            }
                        }
                    },
                    onBotTranscript: (text) => {
                        if (text && text.trim()) {
                            if (this.botTranscript && !this.botTranscript.endsWith(' ') && !text.startsWith(' ')) {
                                this.botTranscript += ' ';
                            }
                            this.botTranscript += text;
                            this.updateBotMessage();
                        }
                    },
                    onError: (error) => {
                        console.error('[VOICE] Pipecat error:', error);
                        this.showError(error.message || 'Erreur Pipecat');
                        const chatContainer = document.getElementById('chat-container');
                        if (chatContainer) {
                            const errorMsg = document.createElement('div');
                            errorMsg.className = 'message system-message';
                            errorMsg.innerHTML = `<p style="color: #ff4d4d;">Erreur: ${error.message || 'Erreur inconnue'}</p>`;
                            chatContainer.appendChild(errorMsg);
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        }
                    }
                }
            );

            console.log('[VOICE] Calling adapter.connect()...');
            await this.adapter.connect();
            console.log('[VOICE] adapter.connect() completed, state:', this.adapter.state);
            
            if (this.adapter.state === 'connected') {
                console.log('[VOICE] Already connected, setting up mic and audio');
                this.isMicEnabled = this.adapter.isMicEnabled;
                await this.setAudioOutputDevice();
            } else {
                console.log('[VOICE] Not connected yet, waiting for onBotReady/onBotConnected event...');
            }
            
            setTimeout(async () => {
                if (this.adapter && this.adapter.state === 'connected') {
                    console.log('[VOICE] Ensuring speaker is enabled after connection...');
                    await this.setAudioOutputDevice();
                }
            }, 1500);

        } catch (error) {
            this.connectionState = 'disconnected';
            this.updateConnectionUI();
            console.error('[VOICE] Connection error:', error.message || error);
            this.showError(error.message || 'Erreur de connexion');
            
            const chatContainer = document.getElementById('chat-container');
            if (chatContainer) {
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message system-message';
                errorMsg.innerHTML = `<p style="color: #ff4d4d;">Erreur de connexion: ${error.message || 'Erreur inconnue'}</p>`;
                chatContainer.appendChild(errorMsg);
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }
    }

    async disconnect() {
        try {
            if (this.adapter) {
                await this.adapter.disconnect();
                this.adapter = null;
            }
            this.cleanup();
            this.connectionState = 'disconnected';
            this.isMicEnabled = false;
            this.updateConnectionUI();
            this.flushUserTranscript();
            this.flushBotTranscript();
        } catch (error) {
            console.error('[VOICE] Disconnect error:', error);
            this.connectionState = 'disconnected';
            this.isMicEnabled = false;
            this.updateConnectionUI();
        }
    }

    async toggleMic() {
        if (!this.adapter || this.connectionState !== 'connected') {
            return false;
        }

        try {
            const newState = await this.adapter.toggleMic();
            this.isMicEnabled = newState;
            this.updateConnectionUI();
            return true;
        } catch (error) {
            console.error('[VOICE] Toggle mic error:', error);
            return false;
        }
    }

    async setupAudioAnalysis() {
        return;
    }

    async getAudioSettings() {
        try {
            if (this.selectedDevices.input || this.selectedDevices.output) {
                return {
                    inputDeviceId: this.selectedDevices.input || 'default',
                    outputDeviceId: this.selectedDevices.output || 'default'
                };
            }
            if (window.settingsManager) {
                const devices = window.settingsManager.getSelectedDevices();
                if (devices.input || devices.output) {
                    this.selectedDevices = devices;
                    return devices;
                }
            }
            if (window.electronAPI && window.electronAPI.getSetting) {
                const input = await window.electronAPI.getSetting('audioInputDevice');
                const output = await window.electronAPI.getSetting('audioOutputDevice');
                this.selectedDevices = {
                    input: input || null,
                    output: output || null
                };
                return {
                    inputDeviceId: input || 'default',
                    outputDeviceId: output || 'default'
                };
            }
            return { inputDeviceId: 'default', outputDeviceId: 'default' };
        } catch (error) {
            console.error('Error getting audio settings:', error);
            return { inputDeviceId: 'default', outputDeviceId: 'default' };
        }
    }

    async applyAudioSettings(devices) {
        this.selectedDevices = devices;
        if (this.connectionState === 'connected' && this.adapter) {
            await this.setAudioOutputDevice();
        }
    }

    async setAudioOutputDevice() {
        try {
            if (!this.adapter || !this.adapter.clientId || !window.pipecatModules) {
                console.log('[VOICE] Cannot set audio output: adapter or modules missing');
                return;
            }
            
            console.log('[VOICE] Setting up audio output device...');
            
            if (window.pipecatModules.enableSpeaker) {
                try {
                    console.log('[VOICE] Enabling speaker...');
                    await window.pipecatModules.enableSpeaker(this.adapter.clientId);
                    console.log('[VOICE] Speaker enabled successfully');
                } catch (error) {
                    console.error('[VOICE] Could not enable speaker:', error);
                }
            } else {
                console.warn('[VOICE] enableSpeaker not available');
            }
            
            if (window.pipecatModules.updateSpeaker) {
                try {
                    const audioSettings = await this.getAudioSettings();
                    if (audioSettings.outputDeviceId && audioSettings.outputDeviceId !== 'default') {
                        console.log('[VOICE] Updating speaker to device:', audioSettings.outputDeviceId);
                        await window.pipecatModules.updateSpeaker(this.adapter.clientId, audioSettings.outputDeviceId);
                        console.log('[VOICE] Speaker updated successfully');
                    } else {
                        console.log('[VOICE] Using default audio output device');
                    }
                } catch (error) {
                    console.error('[VOICE] Could not set audio output device:', error);
                }
            } else {
                console.warn('[VOICE] updateSpeaker not available');
            }
        } catch (error) {
            console.error('[VOICE] Error setting audio output device:', error);
        }
    }

    flushUserTranscript() {
        if (this.userTranscript.trim()) {
            this.addMessage('user', this.userTranscript);
            this.userTranscript = '';
        }
    }

    flushBotTranscript() {
        const trimmed = this.botTranscript.trim();
        if (trimmed) {
            const chatContainer = document.getElementById('chat-container');
            if (!chatContainer) {
                this.botTranscript = '';
                return;
            }
            
            const streamingMessage = chatContainer.querySelector('.assistant-message.streaming');
            if (streamingMessage) {
                const messageText = streamingMessage.querySelector('p');
                if (messageText) {
                    messageText.textContent = trimmed;
                }
                streamingMessage.classList.remove('streaming');
                chatContainer.scrollTop = chatContainer.scrollHeight;
                
                const allMessages = chatContainer.querySelectorAll('.assistant-message');
                const lastFinalMessage = Array.from(allMessages).reverse().find(msg => !msg.classList.contains('streaming'));
                if (lastFinalMessage && lastFinalMessage !== streamingMessage) {
                    const lastText = lastFinalMessage.querySelector('p')?.textContent.trim();
                    if (lastText === trimmed) {
                        console.log('[VOICE] Duplicate message detected, removing streaming message');
                        streamingMessage.remove();
                        this.botTranscript = '';
                        return;
                    }
                }
            } else {
                const allMessages = chatContainer.querySelectorAll('.assistant-message:not(.streaming)');
                const lastMessage = allMessages[allMessages.length - 1];
                if (lastMessage && lastMessage.querySelector('p')?.textContent.trim() === trimmed) {
                    console.log('[VOICE] Duplicate message detected, skipping');
                    this.botTranscript = '';
                    return;
                }
                this.addMessage('assistant', trimmed);
            }
            this.botTranscript = '';
        }
    }

    updateBotMessage() {
        const chatContainer = document.getElementById('chat-container');
        if (!chatContainer) return;

        let botMessage = chatContainer.querySelector('.assistant-message.streaming');
        if (!botMessage) {
            botMessage = document.createElement('div');
            botMessage.className = 'message assistant-message streaming';
            botMessage.innerHTML = '<p></p>';
            chatContainer.appendChild(botMessage);
        }

        const messageText = botMessage.querySelector('p');
        if (messageText) {
            messageText.textContent = this.botTranscript.trim();
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    }

    addMessage(sender, text) {
        const chatContainer = document.getElementById('chat-container');
        if (!chatContainer) {
            console.warn('[VOICE] chat-container not found, cannot add message');
            return;
        }

        const trimmed = text.trim();
        if (!trimmed) {
            return;
        }

        const existingMessages = chatContainer.querySelectorAll(`.${sender}-message:not(.streaming)`);
        const lastMessage = existingMessages[existingMessages.length - 1];
        if (lastMessage) {
            const lastText = lastMessage.querySelector('p')?.textContent.trim();
            if (lastText === trimmed) {
                console.log('[VOICE] Duplicate message detected in addMessage, skipping');
                return;
            }
        }

        console.log('[VOICE] Adding message:', sender, trimmed.substring(0, 50));
        const message = document.createElement('div');
        message.className = `message ${sender}-message`;
        message.innerHTML = `<p>${this.escapeHtml(trimmed)}</p>`;
        chatContainer.appendChild(message);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        console.log('[VOICE] Message added, container now has', chatContainer.children.length, 'messages');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    updateConnectionUI() {
        const micBtn = document.getElementById('voice-mic-btn');
        const connectBtn = document.getElementById('voice-connect-btn');
        const visualizer = document.getElementById('visualizer');
        
        console.log('[VOICE] updateConnectionUI called - isMicEnabled:', this.isMicEnabled, 'connectionState:', this.connectionState);

        if (connectBtn) {
            if (this.connectionState === 'connected') {
                connectBtn.innerHTML = '<span class="btn-text">Déconnexion</span>';
                connectBtn.title = 'Se déconnecter';
                connectBtn.disabled = false;
            } else if (this.connectionState === 'connecting') {
                connectBtn.innerHTML = '<span class="btn-text">Connexion...</span>';
                connectBtn.title = 'Connexion en cours';
                connectBtn.disabled = true;
            } else {
                connectBtn.innerHTML = '<span class="btn-text">Connexion</span>';
                connectBtn.title = 'Se connecter';
                connectBtn.disabled = false;
            }
        }

        if (micBtn) {
            if (this.connectionState === 'connected') {
                micBtn.disabled = false;
                micBtn.style.pointerEvents = 'auto';
                micBtn.style.cursor = 'pointer';
            } else {
                micBtn.disabled = true;
                micBtn.style.pointerEvents = 'none';
                micBtn.style.cursor = 'not-allowed';
            }
            micBtn.title = this.getMicButtonTitle();
            
            if (this.connectionState === 'connected') {
                micBtn.classList.add('connected');
                micBtn.classList.remove('disconnected', 'connecting');
                if (this.isMicEnabled) {
                    micBtn.classList.remove('muted');
                } else {
                    micBtn.classList.add('muted');
                }
            } else {
                micBtn.classList.add('disconnected');
                micBtn.classList.remove('connected', 'connecting', 'muted');
            }
            console.log('[VOICE] UI updated - Mic enabled:', this.isMicEnabled, 'State:', this.connectionState, 'Has muted class:', micBtn.classList.contains('muted'), 'Disabled:', micBtn.disabled);
        }

        if (visualizer) {
            visualizer.style.cursor = 'default';
            if (this.connectionState === 'connected') {
                visualizer.title = 'Connecté';
            } else if (this.connectionState === 'connecting') {
                visualizer.title = 'Connexion en cours...';
            } else {
                visualizer.title = 'Déconnecté';
            }
        }

        this.updateStatusIndicator();
    }

    getMicButtonTitle() {
        if (this.connectionState !== 'connected') {
            return `Microphone - ${this.connectionState === 'connecting' ? 'Connexion...' : 'Non connecté'}`;
        }
        const title = this.isMicEnabled ? 'Microphone activé - Cliquer pour désactiver' : 'Microphone désactivé - Cliquer pour activer';
        console.log('[VOICE] Mic button title:', title, 'isMicEnabled:', this.isMicEnabled);
        return title;
    }

    updateStatusIndicator() {
        let statusText = '';
        if (this.connectionState === 'connected') {
            statusText = this.isMicEnabled ? 'Connecté - Micro actif' : 'Connecté - Micro muet';
        } else if (this.connectionState === 'connecting') {
            statusText = 'Connexion en cours...';
        } else {
            statusText = 'Déconnecté';
        }

        const greeting = document.getElementById('user-greeting');
        if (greeting) {
            const userName = localStorage.getItem('jarvis_user_name') || '';
            const originalText = greeting.getAttribute('data-original') || (userName ? `Bonjour ${userName}` : '');
            if (originalText) {
                greeting.setAttribute('data-original', originalText);
                greeting.textContent = `${originalText} • ${statusText}`;
            } else {
                greeting.textContent = statusText;
            }
        }
    }

    updateMicButton() {
        this.updateConnectionUI();
    }

    updateVisualizer() {
        let amplitude = 0;
        if (this.connectionState === 'connected') {
            if (this.isBotSpeaking) {
                amplitude = Math.min(0.3 + this.remoteAudioLevel * 12, 2.5);
            } else if (this.isUserSpeaking) {
                amplitude = Math.min(0.3 + this.localAudioLevel * 12, 2.5);
            } else {
                amplitude = 0.15;
            }
        }

        if (window.updateVisualizerAmplitude) {
            window.updateVisualizerAmplitude(amplitude);
        }
    }

    showError(message) {
        console.error('Voice error:', message);
    }

    cleanup() {
        this.isBotSpeaking = false;
        this.isUserSpeaking = false;
        this.localAudioLevel = 0;
        this.remoteAudioLevel = 0;
        this.updateVisualizer();
    }
}

const voiceManager = new VoiceManager();

function initVoiceControls() {
    const micBtn = document.getElementById('voice-mic-btn');
    const connectBtn = document.getElementById('voice-connect-btn');
    const visualizer = document.getElementById('visualizer');

    if (connectBtn) {
        connectBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (voiceManager.connectionState === 'connected') {
                await voiceManager.disconnect();
            } else if (voiceManager.connectionState !== 'connecting') {
                await voiceManager.connect();
            }
        });
    }

    if (micBtn) {
        micBtn.onclick = handleMicClick;
        micBtn.addEventListener('click', handleMicClick, true);
        micBtn.style.pointerEvents = 'auto';
        micBtn.style.cursor = 'pointer';
        micBtn.style.zIndex = '1000';
        console.log('[VOICE] Mic button listener attached in initVoiceControls');
    } else {
        console.warn('[VOICE] Mic button not found in initVoiceControls');
    }

}


async function handleMicClick(e) {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    console.log('[VOICE] ===== MIC BUTTON CLICKED =====');
    console.log('[VOICE] Current state - Mic enabled:', voiceManager.isMicEnabled, 'Connection:', voiceManager.connectionState);
    const result = await voiceManager.toggleMic();
    console.log('[VOICE] Toggle mic result:', result);
    return false;
}

window.voiceManager = voiceManager;

function initializeVoice() {
    voiceManager.init().then(() => {
        initVoiceControls();
        
        if (window.electronAPI && window.electronAPI.onBackendReady) {
            window.electronAPI.onBackendReady(() => {
                console.log('[VOICE] Backend ready event received, waiting for manual connection...');
            });
        }
    }).catch(error => {
        console.error('[VOICE] Initialization error:', error);
        initVoiceControls();
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeVoice);
} else {
    initializeVoice();
}
