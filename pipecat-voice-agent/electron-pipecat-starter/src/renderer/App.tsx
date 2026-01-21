import React, { useState, useEffect, useCallback, useRef } from 'react';
import { SiriWaveVisualizer, CameraPanel, MessagePanel, Message } from './components';
import {
  PipecatAdapter,
  ConnectionState,
  TransportType,
} from './lib/pipecatAdapter';
import './styles/App.css';

// Configuration from environment variables
const getConfig = () => ({
  pipecatUrl: import.meta.env.VITE_PIPECAT_URL || 'http://localhost:7860/api/offer',
  transportType: (import.meta.env.VITE_TRANSPORT_TYPE || 'small-webrtc') as TransportType,
  dailyRoomUrl: import.meta.env.VITE_DAILY_ROOM_URL || '',
  dailyToken: import.meta.env.VITE_DAILY_TOKEN || '',
});

const App: React.FC = () => {
  // State
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [isMicEnabled, setIsMicEnabled] = useState(true);
  const [isBotSpeaking, setIsBotSpeaking] = useState(false);
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [localAudioLevel, setLocalAudioLevel] = useState(0);
  const [remoteAudioLevel, setRemoteAudioLevel] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Refs
  const adapterRef = useRef<PipecatAdapter | null>(null);
  const userTranscriptRef = useRef<string>('');
  const botTranscriptRef = useRef<string>('');

  // Add message
  const addMessage = useCallback((sender: 'user' | 'assistant', text: string) => {
    if (!text.trim()) return;
    setMessages((prev) => [
      ...prev,
      {
        id: `${sender}-${Date.now()}`,
        sender,
        text: text.trim(),
        timestamp: new Date(),
      },
    ]);
  }, []);

  // Flush user transcript
  const flushUserTranscript = useCallback(() => {
    if (userTranscriptRef.current.trim()) {
      addMessage('user', userTranscriptRef.current);
      userTranscriptRef.current = '';
    }
  }, [addMessage]);

  // Flush bot transcript
  const flushBotTranscript = useCallback(() => {
    if (botTranscriptRef.current.trim()) {
      addMessage('assistant', botTranscriptRef.current);
      botTranscriptRef.current = '';
    }
  }, [addMessage]);

  // Initialize adapter
  useEffect(() => {
    const config = getConfig();

    adapterRef.current = new PipecatAdapter(
      {
        transportType: config.transportType,
        webrtcUrl: config.pipecatUrl,
        dailyRoomUrl: config.dailyRoomUrl,
        dailyToken: config.dailyToken,
        enableMic: true,
      },
      {
        onStateChange: setConnectionState,
        onLocalAudioLevel: setLocalAudioLevel,
        onRemoteAudioLevel: setRemoteAudioLevel,
        onBotStartedSpeaking: () => setIsBotSpeaking(true),
        onBotStoppedSpeaking: () => {
          setIsBotSpeaking(false);
          flushBotTranscript();
        },
        onUserStartedSpeaking: () => setIsUserSpeaking(true),
        onUserStoppedSpeaking: () => {
          setIsUserSpeaking(false);
          flushUserTranscript();
        },
        onUserTranscript: (text, isFinal) => {
          userTranscriptRef.current = text;
          if (isFinal) {
            flushUserTranscript();
          }
        },
        onBotTranscript: (text) => {
          botTranscriptRef.current += text;
        },
        onError: (err) => setError(err.message),
      }
    );

    return () => {
      adapterRef.current?.destroy();
    };
  }, [flushUserTranscript, flushBotTranscript]);

  // Handlers
  const handleConnect = useCallback(async () => {
    setError(null);
    try {
      await adapterRef.current?.connect();
    } catch {
      // Error handled via callback
    }
  }, []);

  const handleDisconnect = useCallback(async () => {
    await adapterRef.current?.disconnect();
    flushBotTranscript();
    flushUserTranscript();
  }, [flushBotTranscript, flushUserTranscript]);

  const handleToggleMic = useCallback(async () => {
    const newState = await adapterRef.current?.toggleMic();
    if (newState !== undefined) {
      setIsMicEnabled(newState);
    }
  }, []);

  const isConnected = connectionState === 'connected';
  const isConnecting = connectionState === 'connecting';

  // Calculate wave amplitude based on audio levels - much more reactive
  const waveAmplitude = isConnected
    ? isBotSpeaking
      ? Math.min(0.3 + remoteAudioLevel * 12, 2.5)
      : isUserSpeaking
        ? Math.min(0.3 + localAudioLevel * 12, 2.5)
        : 0.15
    : 0;

  return (
    <div className="app">
      {/* Header Bar */}
      <header className="header-bar">
        <div className="header-left">
          <h1 className="app-title">Jarvis</h1>
          {isConnected && (
            <span className="status-pill connected">
              <span className="status-dot" />
              Connecté
            </span>
          )}
        </div>

        <div className="header-controls">
          <button
            className={`control-btn mic-btn ${!isMicEnabled ? 'muted' : ''}`}
            onClick={handleToggleMic}
            disabled={!isConnected}
            title={isMicEnabled ? 'Couper le micro' : 'Activer le micro'}
          >
            {isMicEnabled ? <MicOnIcon /> : <MicOffIcon />}
          </button>

          <button
            className={`control-btn connect-btn ${isConnected ? 'disconnect' : ''}`}
            onClick={isConnected ? handleDisconnect : handleConnect}
            disabled={isConnecting}
          >
            {isConnecting ? (
              <>
                <span className="spinner" />
                Connexion...
              </>
            ) : isConnected ? (
              'Déconnecter'
            ) : (
              'Se connecter'
            )}
          </button>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Main Content */}
      <main className="main-content">
        {/* SiriWave Visualizer */}
        <section className="visualizer-section">
          <SiriWaveVisualizer
            amplitude={waveAmplitude}
            speed={isBotSpeaking ? 0.2 : isUserSpeaking ? 0.15 : 0.05}
            isActive={isConnected}
            color="#4FACFE"
          />
          {!isConnected && (
            <div className="visualizer-overlay">
              <p>Cliquez sur "Se connecter" pour démarrer</p>
            </div>
          )}
        </section>

        {/* Bottom Panels */}
        <section className="panels-section">
          <CameraPanel />
          <MessagePanel messages={messages} />
        </section>
      </main>
    </div>
  );
};

// Icons
const MicOnIcon: React.FC = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

const MicOffIcon: React.FC = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="1" y1="1" x2="23" y2="23" />
    <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
    <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

export default App;
