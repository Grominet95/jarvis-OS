class PipecatAdapter {
    constructor(config, callbacks) {
        this.config = {
            transportType: config.transportType || 'small-webrtc',
            webrtcUrl: config.webrtcUrl || 'http://localhost:7860/api/offer',
            dailyRoomUrl: config.dailyRoomUrl || '',
            dailyToken: config.dailyToken || '',
            enableMic: config.enableMic !== false
        };
        
        this.callbacks = callbacks || {};
        this.client = null;
        this.transport = null;
        this.state = 'disconnected';
        this.isMicEnabled = true;
    }

    async connect() {
        if (this.state === 'connected' || this.state === 'connecting') {
            return;
        }

        try {
            this.setState('connecting');

            if (!window.pipecatModules) {
                throw new Error('Pipecat modules not available');
            }

            const { createPipecatClient } = window.pipecatModules;

            const transportOptions = {
                iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
                waitForICEGathering: true
            };

            const clientOptions = {
                enableMic: this.config.enableMic,
                enableCam: false
            };

            this.clientId = createPipecatClient(transportOptions, clientOptions);
            console.log('[PIPECAT ADAPTER] Client created with ID:', this.clientId);

            if (window.electronAPI && window.electronAPI.onPipecatEvent) {
                console.log('[PIPECAT ADAPTER] Setting up event listener');
                window.electronAPI.onPipecatEvent((eventName, data) => {
                    this.handleEvent(eventName, data);
                });
            } else {
                console.warn('[PIPECAT ADAPTER] electronAPI.onPipecatEvent not available');
            }
            
            window.addEventListener('pipecat-stub-event', (event) => {
                console.log('[PIPECAT ADAPTER] Received stub event:', event.detail);
                this.handleEvent(event.detail.eventName, event.detail.data);
            });

            const { connect } = window.pipecatModules;
            console.log('[PIPECAT ADAPTER] Connecting to:', this.config.webrtcUrl);
            
            try {
                await connect(this.clientId, {
                    webrtcUrl: this.config.webrtcUrl
                });
                console.log('[PIPECAT ADAPTER] Connect call completed, waiting for onBotReady/onBotConnected events...');
            } catch (error) {
                console.error('[PIPECAT ADAPTER] Connection error:', error);
                this.setState('disconnected');
                if (this.callbacks.onError) {
                    this.callbacks.onError(error);
                }
                throw error;
            }

        } catch (error) {
            this.setState('disconnected');
            if (this.callbacks.onError) {
                this.callbacks.onError(error);
            }
            throw error;
        }
    }

    async disconnect() {
        if (this.state === 'disconnected') {
            return;
        }

        try {
            if (this.clientId && window.pipecatModules) {
                const { disconnect } = window.pipecatModules;
                await disconnect(this.clientId);
            }
            
            if (window.electronAPI && window.electronAPI.removePipecatEventListeners) {
                window.electronAPI.removePipecatEventListeners();
            }
            
            if (window.pipecatModules && window.pipecatModules.destroyPipecatClient) {
                window.pipecatModules.destroyPipecatClient();
            }
            
            this.setState('disconnected');
        } catch (error) {
            if (this.callbacks.onError) {
                this.callbacks.onError(error);
            }
        }
    }

    async toggleMic() {
        if (this.state !== 'connected' || !this.clientId || !window.pipecatModules) {
            return this.isMicEnabled;
        }

        try {
            const { muteMic, unmuteMic, isMicEnabled } = window.pipecatModules;
            
            if (this.isMicEnabled) {
                await muteMic(this.clientId);
            } else {
                await unmuteMic(this.clientId);
            }
            
            if (isMicEnabled) {
                this.isMicEnabled = isMicEnabled(this.clientId);
            } else {
                this.isMicEnabled = !this.isMicEnabled;
            }
            
            return this.isMicEnabled;
        } catch (error) {
            if (this.callbacks.onError) {
                this.callbacks.onError(error);
            }
            return this.isMicEnabled;
        }
    }

    setMicEnabled(enabled) {
        if (this.state !== 'connected' || !this.clientId || !window.pipecatModules) {
            return;
        }

        const { muteMic, unmuteMic, isMicEnabled } = window.pipecatModules;
        
        if (enabled) {
            unmuteMic(this.clientId).then(() => {
                if (isMicEnabled) {
                    this.isMicEnabled = isMicEnabled(this.clientId);
                } else {
                    this.isMicEnabled = true;
                }
            });
        } else {
            muteMic(this.clientId).then(() => {
                if (isMicEnabled) {
                    this.isMicEnabled = isMicEnabled(this.clientId);
                } else {
                    this.isMicEnabled = false;
                }
            });
        }
    }

    handleEvent(eventName, data) {
        console.log('[PIPECAT ADAPTER] Event received:', eventName, data);
        switch (eventName) {
            case 'onBackendConnected':
            case 'onBotReady':
            case 'onBotConnected':
                if (this.state !== 'connected') {
                    console.log('[PIPECAT ADAPTER] Setting state to connected');
                    this.setState('connected');
                    
                    if (window.pipecatModules && window.pipecatModules.isMicEnabled && this.clientId) {
                        const micEnabled = window.pipecatModules.isMicEnabled(this.clientId);
                        console.log('[PIPECAT ADAPTER] isMicEnabled returned:', micEnabled);
                        this.isMicEnabled = micEnabled;
                    } else {
                        console.log('[PIPECAT ADAPTER] Setting isMicEnabled to true (default)');
                        this.isMicEnabled = true;
                    }
                    
                    if (this.config.enableMic !== false && !this.isMicEnabled) {
                        console.log('[PIPECAT ADAPTER] enableMic is true but isMicEnabled is false, forcing to true');
                        this.isMicEnabled = true;
                    }
                    
                    if (window.pipecatModules && window.pipecatModules.enableSpeaker && this.clientId) {
                        setTimeout(async () => {
                            try {
                                await window.pipecatModules.enableSpeaker(this.clientId);
                                console.log('[PIPECAT ADAPTER] Speaker enabled after connection');
                            } catch (error) {
                                console.error('[PIPECAT ADAPTER] Error enabling speaker:', error);
                            }
                        }, 500);
                    }
                }
                break;
            case 'onDisconnected':
                this.setState('disconnected');
                break;
            case 'onError':
                if (this.callbacks.onError) {
                    this.callbacks.onError(new Error(data.message || 'Unknown error'));
                }
                break;
            case 'onLocalAudioLevel':
                if (this.callbacks.onLocalAudioLevel) {
                    this.callbacks.onLocalAudioLevel(parseFloat(data.level) || 0);
                }
                break;
            case 'onRemoteAudioLevel':
                if (this.callbacks.onRemoteAudioLevel) {
                    this.callbacks.onRemoteAudioLevel(parseFloat(data.level) || 0);
                }
                break;
            case 'onBotStartedSpeaking':
                if (this.callbacks.onBotStartedSpeaking) {
                    this.callbacks.onBotStartedSpeaking();
                }
                break;
            case 'onBotStoppedSpeaking':
                if (this.callbacks.onBotStoppedSpeaking) {
                    this.callbacks.onBotStoppedSpeaking();
                }
                break;
            case 'onUserStartedSpeaking':
                if (this.callbacks.onUserStartedSpeaking) {
                    this.callbacks.onUserStartedSpeaking();
                }
                break;
            case 'onUserStoppedSpeaking':
                if (this.callbacks.onUserStoppedSpeaking) {
                    this.callbacks.onUserStoppedSpeaking();
                }
                break;
            case 'onUserTranscript':
                if (this.callbacks.onUserTranscript) {
                    this.callbacks.onUserTranscript(data.text || '', data.final || false);
                }
                break;
            case 'onBotOutput':
                if (this.callbacks.onBotTranscript) {
                    this.callbacks.onBotTranscript(data.text || '');
                }
                break;
            case 'onBotAudioTrack':
                console.log('[PIPECAT ADAPTER] Bot audio track received:', data.trackId);
                break;
        }
    }

    setState(newState) {
        if (this.state !== newState) {
            this.state = newState;
            if (this.callbacks.onStateChange) {
                this.callbacks.onStateChange(newState);
            }
        }
    }

    destroy() {
        this.disconnect();
        this.client = null;
        this.transport = null;
        this.clientId = null;
    }

    get adapterId() {
        return this.clientId;
    }
}

window.PipecatAdapter = PipecatAdapter;
