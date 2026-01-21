/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PIPECAT_URL: string;
  readonly VITE_TRANSPORT_TYPE: 'small-webrtc' | 'daily';
  readonly VITE_DAILY_ROOM_URL?: string;
  readonly VITE_DAILY_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
