"use strict";

function showVoiceStatus(text, duration = 0) {
  const el = document.getElementById("voice-status");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("visible", text.length > 0);
  if (duration > 0 && text.length > 0) {
    setTimeout(() => {
      if (el.textContent === text) el.classList.remove("visible");
    }, duration);
  }
}

function bindMicButton(client) {
  const homeBtn = document.getElementById("hc-mic");
  const legacyBtn = document.getElementById("perm-microphone");
  client._btn = homeBtn || legacyBtn || client._btn;
}

class JarvisLiveKitClient {
  constructor() {
    this._room = null;
    this._connected = false;
    this._isSpeaking = false;
    this._agentBubble = null;
    this._btn = document.getElementById("perm-microphone") || document.getElementById("hc-mic");
    this._onActiveChange = null;

    window.jarvis = {
      get isSpeaking() { return window._voiceClient?._isSpeaking ?? false; },
      stopAudio: () => {},
      setState: (s) => window._voiceClient?._setSphereState(s),
      appendJarvisMessage: (text) => window._voiceClient?._appendAgentText(text),
      appendUserMessage: (text) => { if (text) addMsg("vous", text); },
    };
  }

  async _fetchToken() {
    const sessionId = typeof window._jarvisSessionId === "function" ? window._jarvisSessionId() : null;
    const tokenUrl = sessionId
      ? `/api/voice/token?session_id=${encodeURIComponent(sessionId)}`
      : "/api/voice/token";
    const headers = window.Jarvis && Jarvis.authHeaders ? Jarvis.authHeaders() : {};
    const resp = await fetch(tokenUrl, { headers });
    if (!resp.ok) {
      let msg = "Mode vocal indisponible — vérifie que LiveKit et l'agent vocal tournent (jarvis.ps1 run).";
      try {
        const data = await resp.json();
        if (typeof data.detail === "string") msg = data.detail;
      } catch (_) {}
      throw new Error(msg);
    }
    const data = await resp.json();
    if (!data.token || !data.url) {
      throw new Error("Réponse token invalide — LiveKit est-il démarré ?");
    }
    return data;
  }

  _micCaptureOptions() {
    const deviceId = window.JarvisMic && JarvisMic.getSelectedDeviceId();
    return deviceId ? { deviceId } : undefined;
  }

  async _start() {
    if (this._connected) return;
    if (typeof LivekitClient === "undefined") {
      throw new Error("Client LiveKit non chargé — vérifie ta connexion réseau.");
    }

    bindMicButton(this);
    showVoiceStatus("Connexion…");

    const { token, url } = await this._fetchToken();
    const { Room, RoomEvent, Track } = LivekitClient;

    this._room = new Room({ adaptiveStream: true, reconnectPolicy: { maxRetries: 5 } });

    this._room.on(RoomEvent.Connected, () => {
      this._setState("listening");
      showVoiceStatus("Jarvis en ligne");
      setTimeout(() => showVoiceStatus(""), 2000);
      if (this._onActiveChange) this._onActiveChange(true);
    });

    this._room.on(RoomEvent.Disconnected, () => {
      this._setState("idle");
      this._isSpeaking = false;
      this._setSphereState("IDLE");
      showVoiceStatus("");
      if (this._connected && this._onActiveChange) this._onActiveChange(false);
      this._connected = false;
    });

    this._room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const audioEl = track.attach();
        audioEl.dataset.livekit = "1";
        audioEl.autoplay = true;
        document.body.appendChild(audioEl);
      }
    });

    this._room.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((el) => el.remove());
    });

    this._room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      const agentSpeaking = speakers.some((s) => s.isAgent);
      const userSpeaking = speakers.some((s) => !s.isAgent);

      if (userSpeaking) {
        this._setSphereState("LISTENING");
        showVoiceStatus("...");
      } else if (agentSpeaking) {
        this._isSpeaking = true;
        this._setSphereState("SPEAKING");
        showVoiceStatus("");
      } else {
        this._isSpeaking = false;
        this._setSphereState("IDLE");
        showVoiceStatus("");
      }
    });

    this._room.on(RoomEvent.ParticipantMetadataChanged, (metadata, participant) => {
      if (!participant?.isAgent) return;
      try {
        const data = JSON.parse(metadata || "{}");
        if (data.state === "thinking") {
          this._setSphereState("THINKING");
          showVoiceStatus("Jarvis réfléchit...");
        }
      } catch (_) {}
    });

    this._room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
      for (const seg of segments) {
        if (!seg.final) continue;
        if (participant?.isAgent) {
          this._appendAgentText(seg.text);
        } else if (seg.text.trim()) {
          addMsg("vous", seg.text);
        }
      }
    });

    await this._room.connect(url, token, { audio: false, video: false });

    try {
      await this._room.localParticipant.setMicrophoneEnabled(true, this._micCaptureOptions());
    } catch (e) {
      await this._room.disconnect();
      this._room = null;
      showVoiceStatus("");
      throw new Error(
        "Micro inaccessible — autorise le micro dans le navigateur et vérifie le périphérique dans Réglages → Audio & voix.",
      );
    }

    this._connected = true;
  }

  _stop() {
    if (this._room) this._room.disconnect();
    this._room = null;
    this._connected = false;
    this._isSpeaking = false;
    this._agentBubble = null;

    document.querySelectorAll("audio[data-livekit]").forEach((el) => el.remove());

    this._setState("idle");
    this._setSphereState("IDLE");
    showVoiceStatus("");

    if (window._perms) window._perms.microphone = false;
    document.getElementById("perm-microphone")?.classList.remove("active");
    if (this._onActiveChange) this._onActiveChange(false);
  }

  _appendAgentText(text) {
    if (!text?.trim()) return;
    if (!this._agentBubble) {
      this._agentBubble = addMsg("jarvis", "", true);
    }
    this._agentBubble.textContent += text + " ";
    const chat = document.getElementById("chat");
    if (chat) chat.scrollTop = chat.scrollHeight;
    if (/[.!?]$/.test(text.trim())) {
      this._agentBubble?.classList.remove("streaming");
      if (typeof checkForMindmap === "function") checkForMindmap(this._agentBubble);
      this._agentBubble = null;
    }
  }

  _setSphereState(state) {
    if (typeof sphereState !== "undefined") sphereState = state;
    if (typeof window.__jarvisSetOrbState === "function") {
      window.__jarvisSetOrbState(String(state).toLowerCase());
    }
  }

  _setState(state) {
    bindMicButton(this);
    if (!this._btn) return;
    this._btn.dataset.state = state;
    this._btn.classList.toggle("active", state !== "idle" && state !== "error");
  }

  stopAudio() {}
}

function initVoiceClient() {
  if (!window._voiceClient) {
    window._voiceClient = new JarvisLiveKitClient();
  }
  bindMicButton(window._voiceClient);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initVoiceClient);
} else {
  initVoiceClient();
}
