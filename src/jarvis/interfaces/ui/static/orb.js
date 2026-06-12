/* orb.js — Jarvis Three.js sphere (vanilla JS, spec v2)
 *
 * window.createJarvisOrb(canvas, opts) → { setState, setAudioLevel, resize, destroy }
 * window.JarvisOrb(canvas)             → same (backwards compat with home.js `new JarvisOrb(…)`)
 *
 * Requires Three.js loaded before this script.
 */
(function () {
  "use strict";

  function createOrbInternal(canvas) {
    const THREE = window.THREE;
    const S     = window.SPHERE_STYLE;

    let destroyed = false;
    let state = "idle";
    let lastState = "idle";
    let audioLevel = 0;

    // ── Renderer ─────────────────────────────────────────────────────
    let w = canvas.offsetWidth  || 720;
    let h = canvas.offsetHeight || 720;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, S.RENDER.PIXEL_RATIO_MAX));
    renderer.setSize(w, h, false);
    renderer.setClearColor(S.RENDER.ORB_CLEAR_COLOR_HEX, S.RENDER.ORB_CLEAR_ALPHA);

    // ── Camera ───────────────────────────────────────────────────────
    const camera = new THREE.PerspectiveCamera(S.CAMERA.FOV, w / h, S.CAMERA.NEAR, S.CAMERA.FAR);
    camera.position.z = S.CAMERA.ZCAM;
    let cameraZ       = S.CAMERA.ZCAM;
    let cameraZTarget = S.CAMERA.ZCAM;

    const scene = new THREE.Scene();

    // ── Sprite (circular particle, avoids square quads) ──────────────
    const sprite = (() => {
      const sz = S.SPRITE.SIZE_PX;
      const c = document.createElement("canvas");
      c.width = sz; c.height = sz;
      const cc = c.getContext("2d");
      const grad = cc.createRadialGradient(sz / 2, sz / 2, 0, sz / 2, sz / 2, sz / 2);
      S.SPRITE.STOPS.forEach(([offset, color]) => grad.addColorStop(offset, color));
      cc.fillStyle = grad;
      cc.fillRect(0, 0, sz, sz);
      return new THREE.CanvasTexture(c);
    })();

    // ── Particles ────────────────────────────────────────────────────
    const N = S.GEOMETRY.PARTICLE_COUNT;
    const pos   = new Float32Array(N * 3);
    const vel   = new Float32Array(N * 3);
    const phase = new Float32Array(N);

    for (let i = 0; i < N; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi   = Math.acos(2 * Math.random() - 1);
      const r     = S.GEOMETRY.SHELL_R_MIN + Math.random() * S.GEOMETRY.SHELL_THICKNESS;
      pos[i*3]   = r * Math.sin(phi) * Math.cos(theta);
      pos[i*3+1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i*3+2] = r * Math.cos(phi);
      phase[i]   = Math.random() * 1000;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));

    const mat = new THREE.PointsMaterial({
      color: S.COLOR.BASE_HEX,
      size: 0.6,                              // valeur de boot (1 frame) ; mat.size est réécrit chaque frame vers POINT_SIZE_IDLE
      transparent: S.MATERIAL.TRANSPARENT,
      opacity: 0.8,                           // valeur de boot (1 frame) ; mat.opacity est réécrit chaque frame vers OPACITY_IDLE
      sizeAttenuation: S.MATERIAL.SIZE_ATTENUATION,
      blending: THREE.AdditiveBlending,
      depthWrite: S.MATERIAL.DEPTH_WRITE,
      map: sprite,
      alphaTest: S.MATERIAL.ALPHA_TEST,
    });
    const points = new THREE.Points(geo, mat);
    scene.add(points);


    // ── Lines ────────────────────────────────────────────────────────
    const MAX_LINES = 8000;
    const linePos = new Float32Array(MAX_LINES * 6);
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
    lineGeo.setDrawRange(0, 0);

    const lineMat = new THREE.LineBasicMaterial({
      color: S.COLOR.BASE_HEX,
      transparent: true,
      opacity: 0.0,
      blending: THREE.AdditiveBlending,
      depthWrite: S.MATERIAL.DEPTH_WRITE,
    });
    const lines = new THREE.LineSegments(lineGeo, lineMat);
    scene.add(lines);

    // ── Electrons ────────────────────────────────────────────────────
    const electronGeo = new THREE.BufferGeometry();
    const electronPos = new Float32Array(200 * 3);
    electronGeo.setAttribute("position", new THREE.BufferAttribute(electronPos, 3));
    electronGeo.setDrawRange(0, 0);

    const electronMat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 1.2,
      transparent: true,
      opacity: 1.0,
      sizeAttenuation: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      map: sprite,
      alphaTest: 0.001,
    });
    const electronPoints = new THREE.Points(electronGeo, electronMat);
    scene.add(electronPoints);

    const activeElectrons   = [];
    const activeConnections = [];
    let lastElectronSpawn   = 0;

    // ── Lerped state parameters ───────────────────────────────────────
    // Valeurs initiales = buffers de boot ; les cibles idle/listening/thinking/speaking
    // sont fixées dans le switch d'animate() ci-dessous.
    let targetRadius = 28,     currentRadius = 28;
    let targetSpeed  = 0.2,    currentSpeed  = 0.2;
    let targetBright = 0.74,   currentBright = 0.74;
    let targetSize   = 0.58,   currentSize   = 0.58;
    let targetLineAmount   = 0.15, currentLineAmount   = 0.15;
    let targetElectronRate = 0,    electronSpawnRate   = 0;
    let targetGlow = 0.45,     currentGlow = 0.45;

    // ── Music beat ───────────────────────────────────────────────────
    let musicTempo  = 0;   // BPM, 0 = pas de musique
    let musicEnergy = 0;   // 0-1
    let musicBeatPhase = 0;

    // ── Rotation / drag ──────────────────────────────────────────────
    let autoRotY = 0;
    let dragRotX = 0, dragRotY = 0;
    let dragVelX = 0, dragVelY = 0;
    let dragging = false, lastDragX = 0, lastDragY = 0;

    // ── Zoom ─────────────────────────────────────────────────────────
    let zoomImpulse = 0;

    // ── Breath / cloud Z ─────────────────────────────────────────────
    let cloudZ = 0, cloudZVel = 0;

    // ── Time ─────────────────────────────────────────────────────────
    let t = 0;

    // ── Event handlers (stored for cleanup) ──────────────────────────
    function onMouseDown(e) {
      dragging = true;
      lastDragX = e.clientX; lastDragY = e.clientY;
      canvas.style.cursor = "grabbing";
    }
    function onMouseMove(e) {
      if (!dragging) return;
      const dx = e.clientX - lastDragX;
      const dy = e.clientY - lastDragY;
      dragRotY += dx * 0.006;
      dragRotX += dy * 0.006;
      dragRotX = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, dragRotX));
      dragVelX += dy * 0.0015;
      dragVelY += dx * 0.0015;
      lastDragX = e.clientX; lastDragY = e.clientY;
    }
    function onMouseUp() {
      dragging = false;
      canvas.style.cursor = "grab";
    }
    function onWheel(e) {
      e.preventDefault();
      const delta = e.deltaY * 0.18;
      cameraZTarget += delta;
      cameraZTarget = Math.max(40, Math.min(180, cameraZTarget));
    }

    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup",   onMouseUp);
    canvas.addEventListener("wheel",     onWheel, { passive: false });
    canvas.style.cursor = "grab";

    // ── Resize ───────────────────────────────────────────────────────
    const resizeTarget = canvas.parentElement || canvas;
    const ro = new ResizeObserver(() => {
      const nw = resizeTarget.clientWidth  || canvas.offsetWidth;
      const nh = resizeTarget.clientHeight || canvas.offsetHeight;
      if (!nw || !nh) return;
      renderer.setSize(nw, nh, false);
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
    });
    ro.observe(resizeTarget);

    // ── Animation loop ───────────────────────────────────────────────
    function animate() {
      if (destroyed) return;
      requestAnimationFrame(animate);

      t += 0.016;

      const lerp = (a, b, k) => a + (b - a) * k;
      const LK = 0.02;

      // State targets
      switch (state) {
        case "idle":
          targetRadius = S.GEOMETRY.R;                  // 28
          targetSpeed  = 0.18;
          targetBright = S.MATERIAL.OPACITY_IDLE;       // 0.72
          targetSize   = S.MATERIAL.POINT_SIZE_IDLE;    // 0.58
          targetLineAmount   = S.ANIM_IDLE.LINE_AMOUNT_IDLE; // 0.12
          targetElectronRate = 0;
          targetGlow   = 0.42;
          break;
        case "listening":
          targetRadius = 27; targetSpeed = 0.26; targetBright = 0.80;
          targetSize = 0.61; targetLineAmount = 0.28; targetElectronRate = 0;
          targetGlow = 0.54;
          break;
        case "thinking":
          targetRadius = 25; targetSpeed = 0.38; targetBright = 0.85;
          targetSize = 0.57; targetLineAmount = 0.72; targetElectronRate = 0.012;
          targetGlow = 0.68;
          break;
        case "speaking":
          targetRadius = 27; targetSpeed = 0.20; targetBright = 0.86;
          targetSize = 0.63; targetLineAmount = 0.48; targetElectronRate = 0;
          targetGlow = 0.62;
          break;
      }

      currentRadius     = lerp(currentRadius,     targetRadius,     LK);
      currentSpeed      = lerp(currentSpeed,       targetSpeed,      LK);
      currentBright     = lerp(currentBright,      targetBright,     LK);
      currentSize       = lerp(currentSize,        targetSize,       LK);
      currentLineAmount = lerp(currentLineAmount,  targetLineAmount, LK);
      electronSpawnRate = lerp(electronSpawnRate,  targetElectronRate, LK);
      currentGlow       = lerp(currentGlow,        targetGlow,       LK);

      // Hue lerp per state
      if (state === "thinking") {
        mat.color.lerp(new THREE.Color(0x80BFFF), 0.015);   // bleu glacé, même famille
        lineMat.color.lerp(new THREE.Color(0x80BFFF), 0.015);
      } else if (state === "speaking") {
        mat.color.lerp(new THREE.Color(0x66AAFF), 0.015);   // légèrement chaud
        lineMat.color.lerp(new THREE.Color(0x66AAFF), 0.015);
      } else {
        mat.color.lerp(new THREE.Color(S.COLOR.BASE_HEX), 0.015);     // accent exact
        lineMat.color.lerp(new THREE.Color(S.COLOR.BASE_HEX), 0.015);
      }

      // ── Music beat modulation ─────────────────────────────────────
      let beatMod = 0;
      if (musicTempo > 0) {
        musicBeatPhase += (musicTempo / 60) * 0.016;
        beatMod = Math.sin(musicBeatPhase * Math.PI * 2);
      }
      const beatAmp = musicEnergy * 0.12;

      mat.size    = currentSize   + beatMod * musicEnergy * 0.03;
      mat.opacity = Math.min(1, currentBright + beatMod * beatAmp);

      // Auto-rotation + impulse decay
      autoRotY += 0.0015;
      dragVelX *= 0.88;
      dragVelY *= 0.88;

      // ── Particle simulation ────────────────────────────────────────
      const a = pos;
      const effectiveRadius = currentRadius * (1 + audioLevel * 0.15) + beatMod * musicEnergy * 1.8;

      for (let i = 0; i < N; i++) {
        const i3 = i * 3;
        const x  = a[i3], y = a[i3+1], z = a[i3+2];
        const px = phase[i];

        // 1. Noise drift (two harmonic layers, 3 axes)
        vel[i3]   += Math.sin(t * 0.05  + px)                 * 0.001  * currentSpeed;
        vel[i3+1] += Math.cos(t * 0.06  + px * 1.3)           * 0.001  * currentSpeed;
        vel[i3+2] += Math.sin(t * 0.055 + px * 0.7)           * 0.001  * currentSpeed;
        vel[i3]   += Math.sin(t * 0.02  + px * 2.1 + y * 0.1) * 0.0008 * currentSpeed;
        vel[i3+1] += Math.cos(t * 0.025 + px * 1.7 + z * 0.1) * 0.0008 * currentSpeed;
        vel[i3+2] += Math.sin(t * 0.022 + px * 0.9 + x * 0.1) * 0.0008 * currentSpeed;

        // 2. Radial spring — bidirectional Hooke around the shell
        //    pulls in from outside, pushes out from inside → no center collapse
        const dist = Math.sqrt(x*x + y*y + z*z) || 0.01;
        const spring = (dist - effectiveRadius) * 0.003;
        vel[i3]   -= (x / dist) * spring;
        vel[i3+1] -= (y / dist) * spring;
        vel[i3+2] -= (z / dist) * spring;

        // 3. Damping
        vel[i3]   *= 0.989;
        vel[i3+1] *= 0.989;
        vel[i3+2] *= 0.989;

        // 4. Drag impulse — tangential (perpendicular to radius)
        //    yaw  → tangent Y-axis: (-z,  0,  x) / r
        //    pitch → tangent X-axis: ( 0,  z, -y) / r
        if (Math.abs(dragVelX) > 0.001 || Math.abs(dragVelY) > 0.001) {
          vel[i3]   += (-z / dist) * dragVelY * 0.28;
          vel[i3+2] += ( x / dist) * dragVelY * 0.28;
          vel[i3+1] += ( z / dist) * dragVelX * 0.28;
          vel[i3+2] += (-y / dist) * dragVelX * 0.28;
        }

        // Integrate
        a[i3]   += vel[i3];
        a[i3+1] += vel[i3+1];
        a[i3+2] += vel[i3+2];
      }
      geo.attributes.position.needsUpdate = true;

      // ── Lines + active connections (for electron rails) ────────────
      const lineDistance = 8;
      const maxDistSq = lineDistance * lineDistance;
      const step = Math.max(1, Math.floor(N / 600)); // = 10 for N=6000

      let lineCount = 0;
      activeConnections.length = 0;

      for (let i = 0; i < N && lineCount < MAX_LINES; i += step) {
        const x1 = a[i*3], y1 = a[i*3+1], z1 = a[i*3+2];
        for (let j = i + step; j < N && lineCount < MAX_LINES; j += step) {
          const dx = a[j*3] - x1, dy = a[j*3+1] - y1, dz = a[j*3+2] - z1;
          if (dx*dx + dy*dy + dz*dz < maxDistSq) {
            const idx = lineCount * 6;
            linePos[idx]   = x1;       linePos[idx+1] = y1;       linePos[idx+2] = z1;
            linePos[idx+3] = a[j*3];   linePos[idx+4] = a[j*3+1]; linePos[idx+5] = a[j*3+2];
            if (activeConnections.length < 500) {
              activeConnections.push({ x1, y1, z1, x2: a[j*3], y2: a[j*3+1], z2: a[j*3+2] });
            }
            lineCount++;
          }
        }
      }
      lineGeo.setDrawRange(0, lineCount * 2);
      lineGeo.attributes.position.needsUpdate = true;
      lineMat.opacity = currentLineAmount * S.ANIM_IDLE.LINE_OPACITY_K;

      // ── Electrons (thinking only) ─────────────────────────────────
      if (activeConnections.length > 0 && electronSpawnRate > 0.005) {
        if (activeElectrons.length < 3 && (t - lastElectronSpawn) > 1.0) {
          const conn = activeConnections[Math.floor(Math.random() * activeConnections.length)];
          activeElectrons.push({
            sx: conn.x1, sy: conn.y1, sz: conn.z1,
            ex: conn.x2, ey: conn.y2, ez: conn.z2,
            t: 0,
            speed: 0.003 + Math.random() * 0.003,
          });
          lastElectronSpawn = t;
        }
      }

      let ek = 0;
      for (let e = activeElectrons.length - 1; e >= 0; e--) {
        const el = activeElectrons[e];
        el.t += el.speed;
        if (el.t >= 1) { activeElectrons.splice(e, 1); continue; }
        electronPos[ek*3]   = el.sx + (el.ex - el.sx) * el.t;
        electronPos[ek*3+1] = el.sy + (el.ey - el.sy) * el.t;
        electronPos[ek*3+2] = el.sz + (el.ez - el.sz) * el.t;
        ek++;
      }
      electronGeo.setDrawRange(0, ek);
      electronGeo.attributes.position.needsUpdate = true;


      // ── Breath Z — amplitudes très faibles, pas de zoom visible ─────
      let zTarget = Math.sin(t * 0.10) * 0.8;
      if (state === "thinking")      zTarget = Math.sin(t * 0.16) * 1.4 + Math.sin(t * 0.41) * 0.5;
      else if (state === "speaking") zTarget = Math.sin(t * 0.11) * 1.0;

      cloudZVel += (zTarget - cloudZ) * 0.008;
      cloudZVel *= 0.94;
      cloudZ    += cloudZVel;

      points.position.z       = cloudZ;
      lines.position.z        = cloudZ;
      electronPoints.position.z = cloudZ;


      // ── Rotation (auto + drag) ────────────────────────────────────
      const rotY = dragRotY + autoRotY;
      const rotX = dragRotX;

      points.rotation.y         = rotY;
      lines.rotation.y          = rotY;
      electronPoints.rotation.y = rotY;
      points.rotation.x         = rotX;
      lines.rotation.x          = rotX;
      electronPoints.rotation.x = rotX;

      // ── Camera ────────────────────────────────────────────────────
      cameraZ += (cameraZTarget - cameraZ) * 0.18;
      camera.position.z = cameraZ;
      camera.position.x = Math.sin(t * S.CAMERA.OSC_X_FREQ) * S.CAMERA.OSC_X_AMPL;
      camera.position.y = Math.cos(t * S.CAMERA.OSC_Y_FREQ) * S.CAMERA.OSC_Y_AMPL;
      camera.lookAt(0, 0, cloudZ * 0.2);

      renderer.render(scene, camera);
    }

    animate();

    // ── Public API ───────────────────────────────────────────────────
    return {
      setState(s) {
        lastState = state;
        state = (s === "idle" || s === "listening" || s === "thinking" || s === "speaking") ? s : "idle";
      },
      setAudioLevel(v) {
        audioLevel = Math.max(0, Math.min(1, v));
      },
      setMusicBeat(tempo, energy) {
        musicTempo  = Math.max(0, tempo  || 0);
        musicEnergy = Math.max(0, Math.min(1, energy || 0));
        if (musicTempo === 0) musicBeatPhase = 0;
      },
      resize(nw, nh) {
        renderer.setSize(nw, nh, false);
        camera.aspect = nw / nh;
        camera.updateProjectionMatrix();
      },
      destroy() {
        destroyed = true;
        canvas.removeEventListener("mousedown", onMouseDown);
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup",   onMouseUp);
        canvas.removeEventListener("wheel",     onWheel);
        ro.disconnect();
        renderer.dispose();
        geo.dispose();
        mat.dispose();
        lineGeo.dispose();
        lineMat.dispose();
        electronGeo.dispose();
        electronMat.dispose();
        sprite.dispose();
      },
    };
  }

  window.createJarvisOrb = function (canvas, opts) {
    return createOrbInternal(canvas);
  };

  // `new JarvisOrb(canvas)` still works — constructor returning an object
  // causes `new` to return that object instead of `this`
  window.JarvisOrb = function (canvas, opts) {
    return createOrbInternal(canvas);
  };
})();
