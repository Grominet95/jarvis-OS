import React, { useEffect, useRef } from 'react';

export interface TranscriptEntry {
  id: string;
  speaker: 'user' | 'bot';
  text: string;
  timestamp: Date;
  isFinal?: boolean;
}

interface TranscriptPanelProps {
  entries: TranscriptEntry[];
  maxHeight?: number;
}

export const TranscriptPanel: React.FC<TranscriptPanelProps> = ({
  entries,
  maxHeight = 200,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [entries]);

  const formatTime = (date: Date): string => {
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="transcript-panel">
      <div className="transcript-panel-header">
        <span>Conversation</span>
      </div>
      <div
        ref={containerRef}
        className="transcript-panel-content"
        style={{ maxHeight: `${maxHeight}px` }}
      >
        {entries.length === 0 ? (
          <div className="transcript-empty">
            Conversation will appear here...
          </div>
        ) : (
          entries.map((entry) => (
            <div
              key={entry.id}
              className={`transcript-entry ${entry.speaker} ${
                entry.isFinal === false ? 'interim' : ''
              }`}
            >
              <div className="transcript-header">
                <span className="transcript-speaker">
                  {entry.speaker === 'user' ? 'You' : 'Bot'}
                </span>
                <span className="transcript-time">
                  {formatTime(entry.timestamp)}
                </span>
              </div>
              <div className="transcript-text">{entry.text}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default TranscriptPanel;
