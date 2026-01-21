import React from 'react';
import { ConnectionState } from '../lib/pipecatAdapter';

interface ControlsProps {
  connectionState: ConnectionState;
  isMicEnabled: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onToggleMic: () => void;
  disabled?: boolean;
}

export const Controls: React.FC<ControlsProps> = ({
  connectionState,
  isMicEnabled,
  onConnect,
  onDisconnect,
  onToggleMic,
  disabled = false,
}) => {
  const isConnected = connectionState === 'connected';
  const isConnecting = connectionState === 'connecting';

  return (
    <div className="controls">
      {/* Connect/Disconnect Button */}
      <button
        className={`btn btn-primary ${isConnected ? 'btn-danger' : ''}`}
        onClick={isConnected ? onDisconnect : onConnect}
        disabled={disabled || isConnecting}
      >
        {isConnecting ? (
          <>
            <span className="spinner" /> Connecting...
          </>
        ) : isConnected ? (
          'Disconnect'
        ) : (
          'Connect'
        )}
      </button>

      {/* Mic Toggle Button */}
      <button
        className={`btn btn-secondary ${!isMicEnabled ? 'btn-muted' : ''}`}
        onClick={onToggleMic}
        disabled={!isConnected || disabled}
        title={isMicEnabled ? 'Mute microphone' : 'Unmute microphone'}
      >
        {isMicEnabled ? (
          <>
            <MicOnIcon /> Mic On
          </>
        ) : (
          <>
            <MicOffIcon /> Mic Off
          </>
        )}
      </button>
    </div>
  );
};

// Simple SVG icons
const MicOnIcon: React.FC = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

const MicOffIcon: React.FC = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="1" y1="1" x2="23" y2="23" />
    <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
    <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

export default Controls;
