import React, { useEffect, useRef, useCallback } from 'react';
import SiriWave from 'siriwave';

interface SiriWaveVisualizerProps {
  amplitude?: number;
  speed?: number;
  isActive?: boolean;
  color?: string;
}

export const SiriWaveVisualizer: React.FC<SiriWaveVisualizerProps> = ({
  amplitude = 0,
  speed = 0.04,
  isActive = false,
  color = '#4FACFE',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const siriWaveRef = useRef<SiriWave | null>(null);

  const initSiriWave = useCallback(() => {
    if (!containerRef.current || siriWaveRef.current) return;

    const container = containerRef.current;
    const width = container.offsetWidth;
    const height = container.offsetHeight;

    siriWaveRef.current = new SiriWave({
      container,
      width,
      height,
      style: 'ios', // Classic iOS style
      amplitude: isActive ? amplitude : 0,
      speed,
      autostart: true,
      color,
      cover: true,
    });
  }, [amplitude, speed, isActive, color]);

  // Initialize on mount
  useEffect(() => {
    initSiriWave();

    return () => {
      if (siriWaveRef.current) {
        siriWaveRef.current.dispose();
        siriWaveRef.current = null;
      }
    };
  }, [initSiriWave]);

  // Update amplitude when props change - allow higher values for more dramatic effect
  useEffect(() => {
    if (siriWaveRef.current) {
      const targetAmplitude = isActive ? Math.max(1, amplitude) : 0;
      siriWaveRef.current.setAmplitude(targetAmplitude);
    }
  }, [amplitude, isActive]);

  // Update speed when props change
  useEffect(() => {
    if (siriWaveRef.current) {
      siriWaveRef.current.setSpeed(isActive ? speed : 0.01);
    }
  }, [speed, isActive]);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (siriWaveRef.current && containerRef.current) {
        siriWaveRef.current.dispose();
        siriWaveRef.current = null;
        initSiriWave();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [initSiriWave]);

  return (
    <div className="siriwave-container" ref={containerRef}>
      <div className="siriwave-overlay" />
    </div>
  );
};

export default SiriWaveVisualizer;
