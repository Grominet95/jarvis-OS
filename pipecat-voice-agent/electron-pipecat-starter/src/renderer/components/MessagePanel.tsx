import React, { useEffect, useRef } from 'react';

export interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: Date;
}

interface MessagePanelProps {
  messages: Message[];
}

export const MessagePanel: React.FC<MessagePanelProps> = ({ messages }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="message-panel">
      <div className="panel-header">
        <span className="panel-title">Conversation</span>
      </div>

      <div ref={containerRef} className="messages-container">
        {messages.length === 0 ? (
          <div className="messages-empty">
            <p>Les messages apparaîtront ici...</p>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`message ${message.sender}`}
            >
              <div className="message-bubble">
                <p className="message-text">{message.text}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default MessagePanel;
