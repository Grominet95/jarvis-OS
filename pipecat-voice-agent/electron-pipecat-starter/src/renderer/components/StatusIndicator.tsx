import React from 'react';
import { ConnectionState } from '../lib/pipecatAdapter';

interface StatusIndicatorProps {
  state: ConnectionState;
  isBotSpeaking?: boolean;
  isUserSpeaking?: boolean;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  state,
  isBotSpeaking = false,
  isUserSpeaking = false,
}) => {
  const getStatusConfig = () => {
    switch (state) {
      case 'connected':
        return {
          color: '#4ade80', // green
          text: 'Connected',
          pulse: false,
        };
      case 'connecting':
        return {
          color: '#fbbf24', // yellow
          text: 'Connecting...',
          pulse: true,
        };
      case 'error':
        return {
          color: '#ef4444', // red
          text: 'Error',
          pulse: false,
        };
      case 'disconnected':
      default:
        return {
          color: '#6b7280', // gray
          text: 'Disconnected',
          pulse: false,
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div className="status-indicator">
      <div className="status-main">
        <span
          className={`status-dot ${config.pulse ? 'pulse' : ''}`}
          style={{ backgroundColor: config.color }}
        />
        <span className="status-text">{config.text}</span>
      </div>

      {state === 'connected' && (
        <div className="speaking-indicators">
          {isUserSpeaking && (
            <span className="speaking-badge user">You are speaking</span>
          )}
          {isBotSpeaking && (
            <span className="speaking-badge bot">Bot is speaking</span>
          )}
        </div>
      )}
    </div>
  );
};

export default StatusIndicator;
