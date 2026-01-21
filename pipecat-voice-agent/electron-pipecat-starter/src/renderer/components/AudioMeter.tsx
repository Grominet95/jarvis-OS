import React, { useEffect, useRef } from 'react';

interface AudioMeterProps {
  level: number; // 0-1 normalized audio level
  label?: string;
  color?: string;
  height?: number;
}

export const AudioMeter: React.FC<AudioMeterProps> = ({
  level,
  label = 'Audio',
  color = '#4ade80',
  height = 8,
}) => {
  const meterRef = useRef<HTMLDivElement>(null);

  // Clamp level between 0 and 1
  const normalizedLevel = Math.max(0, Math.min(1, level));

  // Convert to percentage
  const percentage = normalizedLevel * 100;

  // Apply smoothing via CSS transition
  useEffect(() => {
    if (meterRef.current) {
      meterRef.current.style.width = `${percentage}%`;
    }
  }, [percentage]);

  return (
    <div className="audio-meter">
      {label && <span className="audio-meter-label">{label}</span>}
      <div
        className="audio-meter-track"
        style={{ height: `${height}px` }}
      >
        <div
          ref={meterRef}
          className="audio-meter-fill"
          style={{
            backgroundColor: color,
            width: `${percentage}%`,
          }}
        />
        {/* Tick marks for visual reference */}
        <div className="audio-meter-ticks">
          <span className="tick" style={{ left: '25%' }} />
          <span className="tick" style={{ left: '50%' }} />
          <span className="tick" style={{ left: '75%' }} />
        </div>
      </div>
    </div>
  );
};

interface DualAudioMeterProps {
  localLevel: number;
  remoteLevel: number;
}

export const DualAudioMeter: React.FC<DualAudioMeterProps> = ({
  localLevel,
  remoteLevel,
}) => {
  return (
    <div className="dual-audio-meter">
      <AudioMeter
        level={localLevel}
        label="You"
        color="#60a5fa" // blue
        height={6}
      />
      <AudioMeter
        level={remoteLevel}
        label="Bot"
        color="#4ade80" // green
        height={6}
      />
    </div>
  );
};

export default AudioMeter;
