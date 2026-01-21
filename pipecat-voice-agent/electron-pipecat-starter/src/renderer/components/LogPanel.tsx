import React, { useEffect, useRef } from 'react';
import { LogEntry } from '../lib/pipecatAdapter';

interface LogPanelProps {
  logs: LogEntry[];
  maxHeight?: number;
}

export const LogPanel: React.FC<LogPanelProps> = ({
  logs,
  maxHeight = 200,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  const getLevelColor = (level: LogEntry['level']): string => {
    switch (level) {
      case 'error':
        return '#ef4444';
      case 'warn':
        return '#fbbf24';
      case 'event':
        return '#a78bfa';
      case 'info':
      default:
        return '#94a3b8';
    }
  };

  const formatTimestamp = (date: Date): string => {
    const time = date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    const ms = date.getMilliseconds().toString().padStart(3, '0');
    return `${time}.${ms}`;
  };

  return (
    <div className="log-panel">
      <div className="log-panel-header">
        <span>Event Logs</span>
        <span className="log-count">{logs.length} events</span>
      </div>
      <div
        ref={containerRef}
        className="log-panel-content"
        style={{ maxHeight: `${maxHeight}px` }}
      >
        {logs.length === 0 ? (
          <div className="log-empty">No events yet. Click Connect to start.</div>
        ) : (
          logs.map((log, index) => (
            <div key={index} className="log-entry">
              <span className="log-timestamp">
                {formatTimestamp(log.timestamp)}
              </span>
              <span
                className="log-level"
                style={{ color: getLevelColor(log.level) }}
              >
                [{log.level.toUpperCase()}]
              </span>
              <span className="log-message">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default LogPanel;
