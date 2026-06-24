/**
 * mission_control.js — Jarvis UI v2 (slim)
 *
 * Responsabilités :
 *  1. Appliquer le thème sauvegardé (localStorage) au boot sur toutes les pages
 *  2. Injecter le bouton Home flottant sur les pages hors home
 *  3. Rediriger openMissionControl() vers /mc
 *
 * PAS de logique overlay, PAS de panneau Interface ici.
 * Tout ça est dans mc.js (page /mc).
 */

(function () {
  'use strict';

  const LS_THEME_KEY = 'jarvis_theme_v1';

  const THEME_VARS = [
    '--bg-0', '--bg-2', '--accent', '--fg-0',
    '--grain-opacity', '--vignette-opacity',
  ];

  /* ── Appliquer le thème sauvegardé ───────────────────────────────────── */

  function loadTheme() {
    try { return JSON.parse(localStorage.getItem(LS_THEME_KEY) || '{}'); }
    catch (e) { return {}; }
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    THEME_VARS.forEach(k => {
      if (theme[k] !== undefined) root.style.setProperty(k, theme[k]);
    });
    if (theme['--base-font-size']) {
      root.style.setProperty('font-size', theme['--base-font-size'] + 'px');
    }
    if (theme['--accent'] && theme['--accent'].startsWith('#') && theme['--accent'].length === 7) {
      const r = parseInt(theme['--accent'].slice(1,3),16);
      const g = parseInt(theme['--accent'].slice(3,5),16);
      const b = parseInt(theme['--accent'].slice(5,7),16);
      root.style.setProperty('--accent-soft', `rgba(${r},${g},${b},0.14)`);
      root.style.setProperty('--accent-line', `rgba(${r},${g},${b},0.32)`);
    }
    if (theme['--fg-0'] && theme['--fg-0'].startsWith('#') && theme['--fg-0'].length === 7) {
      const r = parseInt(theme['--fg-0'].slice(1,3),16);
      const g = parseInt(theme['--fg-0'].slice(3,5),16);
      const b = parseInt(theme['--fg-0'].slice(5,7),16);
      root.style.setProperty('--fg-1', `rgba(${r},${g},${b},0.78)`);
      root.style.setProperty('--fg-2', `rgba(${r},${g},${b},0.55)`);
      root.style.setProperty('--fg-3', `rgba(${r},${g},${b},0.36)`);
      root.style.setProperty('--fg-4', `rgba(${r},${g},${b},0.20)`);
    }
  }

  applyTheme(loadTheme());

  /* Injecter la couleur accent pour l'orbe (lu par sphereStyle.js) */
  (function () {
    try {
      const t = JSON.parse(localStorage.getItem('jarvis_theme_v1') || '{}');
      if (t['--accent'] && /^#[0-9a-fA-F]{6}$/.test(t['--accent'])) {
        window.JARVIS_ACCENT_COLOR = t['--accent'];
      }
    } catch (e) {}
  })();

  /* ── Rediriger openMissionControl vers /mc ───────────────────────────── */

  if (window.Jarvis) {
    Jarvis.openMissionControl  = function () { window.location.href = '/mc'; };
    Jarvis.closeMissionControl = function () {};
  }

  /* Bouton Home supprimé — le logo Jarvis dans la topbar /mc joue ce rôle */

})();
