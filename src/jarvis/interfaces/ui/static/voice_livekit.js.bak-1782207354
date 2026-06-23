"use strict";

// ── Label voice-status ────────────────────────────────────────────────────────
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

// ── JarvisLiveKitClient ───────────────────────────────────────────────────────
class JarvisLiveKitClient {
  constructor() {
    this._room       = null;
    this._connected  = false;
    this._isSpeaking = false;
    this._agentBubble = null;
    this._btn        = document.getElementById("perm-microphone");

    // Interface window.jarvis (identique à l'ancien voice.js)
    window.jarvis = {
      get isSpeaking() { return window._voiceClient?._isSpeaking ?? false; },
      stopAudio: () => {},        // LiveKit gère l'audio nativement
      setState:  (s) => window._voiceClient?._setSphereState(s),
      appendJarvisMessage: (text) => window._voiceClient?._appendAgentText(text),
      appendUserMessage:   (text) => { if (text) addMsg("vous", text); },
    };
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  async _start() {
    // Partager la session texte courante avec l'agent vocal
    const sessionId = typeof window._jarvisSessionId === "function" ? window._jarvisSessionId() : null;
    const tokenUrl = sessionId
      ? `/api/voice/token?session_id=${encodeURIComponent(sessionId)}`
      : "/api/voice/token";

    let tokenData;
    try {
      tokenData = await fetch(tokenUrl).then((r) => r.json());
    } catch (e) {
      console.error("[LiveKit] Impossible de récupérer le token:", e);
      throw e;
    }
    const { token, url } = tokenData;
    console.log("[LiveKit] Token OK, connexion à", url);

    const { Room, RoomEvent, Track } = LivekitClient;

    this._room = new Room({ adaptiveStream: true, reconnectPolicy: { maxRetries: 5 } });

    this._room.on(RoomEvent.Connected, () => {
      this._setState("listening");
      showVoiceStatus("Jarvis en ligne");
      setTimeout(() => showVoiceStatus(""), 2000);
    });

    this._room.on(RoomEvent.Disconnected, () => {
      this._setState("idle");
      this._isSpeaking = false;
      this._setSphereState("IDLE");
      showVoiceStatus("");
    });

    // Audio de l'agent → attacher à un <audio> invisible
    this._room.on(RoomEvent.TrackSubscribed, (track, _pub, _participant) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach();
        el.dataset.livekit = "1";
        el.autoplay = true;
        document.body.appendChild(el);
      }
    });

    this._room.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((el) => el.remove());
    });

    // États sphère via activité des speakers
    this._room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      const agentSpeaking = speakers.some((s) => s.isAgent);
      const userSpeaking  = speakers.some((s) => !s.isAgent);

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

    // État THINKING via metadata de l'agent
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

    // Transcriptions
    this._room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
      for (const seg of segments) {
        if (!seg.final) continue;
        if (participant?.isAgent) {
          this._appendAgentText(seg.text);
        } else {
          if (seg.text.trim()) addMsg("vous", seg.text);
        }
      }
    });

    console.log("[LiveKit] Connexion à la room...");
    await this._room.connect(url, token, { audio: false, video: false });
    console.log("[LiveKit] Room connectée, activation du micro...");

    // Publier le micro local explicitement
    try {
      await this._room.localParticipant.setMicrophoneEnabled(true);
      console.log("[LiveKit] Micro activé.");
    } catch (e) {
      console.error("[LiveKit] Erreur activation micro:", e);
      // On continue — la room est connectée, Jarvis peut quand même parler
    }

    this._connected = true;
  }

  _stop() {
    this._room?.disconnect();
    this._room      = null;
    this._connected = false;
    this._isSpeaking = false;
    this._agentBubble = null;

    // Supprimer les éléments audio LiveKit
    document.querySelectorAll("audio[data-livekit]").forEach((el) => el.remove());

    this._setState("idle");
    this._setSphereState("IDLE");
    showVoiceStatus("");

    if (window._perms) window._perms.microphone = false;
    document.getElementById("perm-microphone")?.classList.remove("active");
  }

  // ── Texte agent (streaming ou bloc) ──────────────────────────────────────

  _appendAgentText(text) {
    if (!text?.trim()) return;
    if (!this._agentBubble) {
      this._agentBubble = addMsg("jarvis", "", true);
    }
    this._agentBubble.textContent += text + " ";
    const chat = document.getElementById("chat");
    if (chat) chat.scrollTop = chat.scrollHeight;
    // Finaliser la bulle si le texte se termine par une ponctuation de fin
    if (/[.!?]$/.test(text.trim())) {
      this._agentBubble?.classList.remove("streaming");
      if (typeof checkForMindmap === "function") checkForMindmap(this._agentBubble);
      this._agentBubble = null;
    }
  }

  // ── État sphère ───────────────────────────────────────────────────────────

  _setSphereState(state) {
    if (typeof sphereState !== "undefined") sphereState = state;
    // Pont vers l'orbe de la home (home.js expose __jarvisSetOrbState).
    // États LiveKit en MAJ (LISTENING/SPEAKING/THINKING/IDLE) -> minuscules.
    if (typeof window.__jarvisSetOrbState === "function") {
      window.__jarvisSetOrbState(String(state).toLowerCase());
    }
  }

  // ── État bouton micro ─────────────────────────────────────────────────────

  _setState(state) {
    if (!this._btn) return;
    this._btn.dataset.state = state;
    this._btn.classList.toggle("active", state !== "idle" && state !== "error");
  }

  stopAudio() {
    // LiveKit gère l'interruption nativement via barge-in
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window._voiceClient = new JarvisLiveKitClient();
});
