import React, { useRef, useState, useEffect, useCallback } from 'react';

interface CameraPanelProps {
  onCameraToggle?: (enabled: boolean) => void;
}

export const CameraPanel: React.FC<CameraPanelProps> = ({ onCameraToggle }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isEnabled, setIsEnabled] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startCamera = useCallback(async () => {
    try {
      setError(null);
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
      });

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }

      setStream(mediaStream);
      setIsEnabled(true);
      onCameraToggle?.(true);
    } catch (err) {
      console.error('Camera error:', err);
      setError('Camera access denied');
      setIsEnabled(false);
    }
  }, [onCameraToggle]);

  const stopCamera = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      setStream(null);
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setIsEnabled(false);
    onCameraToggle?.(false);
  }, [stream, onCameraToggle]);

  const toggleCamera = useCallback(() => {
    if (isEnabled) {
      stopCamera();
    } else {
      startCamera();
    }
  }, [isEnabled, startCamera, stopCamera]);

  // Assign stream to video element when both are available
  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream, isEnabled]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [stream]);

  return (
    <div className="camera-panel">
      <div className="panel-header">
        <span className="panel-title">Input Visuel</span>
      </div>

      <div className="camera-viewport">
        {isEnabled ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="camera-video"
          />
        ) : (
          <div className="camera-placeholder">
            {error ? (
              <span className="camera-error">{error}</span>
            ) : (
              <CameraIcon />
            )}
          </div>
        )}
      </div>

      <button
        className={`camera-toggle-btn ${isEnabled ? 'active' : ''}`}
        onClick={toggleCamera}
      >
        {isEnabled ? 'Désactiver' : 'Activer la caméra'}
      </button>
    </div>
  );
};

const CameraIcon: React.FC = () => (
  <svg
    width="48"
    height="48"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
    <circle cx="12" cy="13" r="4" />
  </svg>
);

export default CameraPanel;
