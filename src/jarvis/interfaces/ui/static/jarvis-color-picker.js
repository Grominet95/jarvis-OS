/**
 * jarvis-color-picker.js — color picker custom pour l'UI Jarvis
 * Usage :
 *   const p = new JarvisColorPicker({ value: '#4A9EFF', onChange: hex => ... });
 *   container.appendChild(p.el);
 *   p.destroy(); // cleanup
 */
(function (global) {
  'use strict';

  const PRESETS = [
    '#4A9EFF','#36D399','#B8963E','#E5484D',
    '#A78BFA','#F59E0B','#FF6B6B','#06080D','#DCE8FF','#ffffff',
  ];

  function hexToHsv(hex) {
    let r = parseInt(hex.slice(1,3),16)/255;
    let g = parseInt(hex.slice(3,5),16)/255;
    let b = parseInt(hex.slice(5,7),16)/255;
    const max = Math.max(r,g,b), min = Math.min(r,g,b), d = max - min;
    let h = 0, s = max === 0 ? 0 : d/max, v = max;
    if (d !== 0) {
      if      (max === r) h = ((g-b)/d + (g<b?6:0)) / 6;
      else if (max === g) h = ((b-r)/d + 2) / 6;
      else                h = ((r-g)/d + 4) / 6;
    }
    return { h: h*360, s, v };
  }

  function hsvToHex(h, s, v) {
    h = h / 60;
    const i = Math.floor(h) % 6;
    const f = h - Math.floor(h);
    const p = v*(1-s), q = v*(1-f*s), t = v*(1-(1-f)*s);
    const sets = [[v,t,p],[q,v,p],[p,v,t],[p,q,v],[t,p,v],[v,p,q]];
    const [r,g,b] = sets[i];
    return '#' + [r,g,b].map(x => Math.round(x*255).toString(16).padStart(2,'0')).join('');
  }

  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }

  function JarvisColorPicker(opts) {
    this._onChange = opts.onChange || function(){};
    const hsv = hexToHsv(opts.value || '#4A9EFF');
    this._h = hsv.h; this._s = hsv.s; this._v = hsv.v;
    this._build();
    this._drawAll();
  }

  JarvisColorPicker.prototype._build = function () {
    const self = this;

    // Conteneur principal
    const root = document.createElement('div');
    root.className = 'jcp-root';
    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = 'display:block;margin-left:auto;background:none;border:none;color:var(--fg-2);font-size:0.875rem;cursor:pointer;padding:0 2px 6px;line-height:1;';
    closeBtn.addEventListener('click', () => self.hide());
    root.style.position = 'relative';
    root.appendChild(closeBtn);
    root.style.cssText = 'display:none; flex-direction:column; gap:10px; padding:12px; background:var(--bg-1); border:0.5px solid var(--line-2); border-radius:10px; margin-top:8px; width:240px;';

    // Canvas spectre SV
    const specWrap = document.createElement('div');
    specWrap.style.cssText = 'position:relative; border-radius:6px; overflow:hidden; cursor:crosshair; user-select:none;';
    const spec = document.createElement('canvas');
    spec.width = 200; spec.height = 110;
    spec.style.cssText = 'display:block; width:100%; height:140px;';
    const specCursor = document.createElement('div');
    specCursor.style.cssText = 'position:absolute; width:12px; height:12px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1px rgba(0,0,0,0.5); pointer-events:none; transform:translate(-50%,-50%);';
    specWrap.appendChild(spec);
    specWrap.appendChild(specCursor);

    // Canvas hue
    const hueWrap = document.createElement('div');
    hueWrap.style.cssText = 'position:relative; height:12px;';
    const hueBar = document.createElement('canvas');
    hueBar.width = 200; hueBar.height = 10;
    hueBar.style.cssText = 'display:block; width:100%; height:12px; border-radius:6px; cursor:pointer;';
    const hueThumb = document.createElement('div');
    hueThumb.style.cssText = 'position:absolute; top:50%; width:14px; height:14px; border-radius:50%; background:#fff; border:2px solid #fff; box-shadow:0 0 0 1px rgba(0,0,0,0.4); transform:translate(-50%,-50%); pointer-events:none;';
    hueWrap.appendChild(hueBar);
    hueWrap.appendChild(hueThumb);

    // Hex row
    const hexRow = document.createElement('div');
    hexRow.style.cssText = 'display:flex; align-items:center; gap:8px;';
    const swatch = document.createElement('div');
    swatch.style.cssText = 'width:28px; height:28px; border-radius:6px; border:0.5px solid var(--line-2); flex-shrink:0;';
    const hexInput = document.createElement('input');
    hexInput.type = 'text';
    hexInput.maxLength = 7;
    hexInput.style.cssText = 'flex:1; background:var(--bg-2,#0F141F); border:0.5px solid var(--line-2); border-radius:6px; color:var(--fg-2); font-family:var(--mono); font-size:0.6875rem; padding:5px 8px; letter-spacing:0.08em; outline:none;';
    hexRow.appendChild(swatch);
    hexRow.appendChild(hexInput);

    // Presets
    const presetsEl = document.createElement('div');
    presetsEl.style.cssText = 'display:flex; flex-wrap:wrap; gap:5px;';
    PRESETS.forEach(c => {
      const d = document.createElement('div');
      d.style.cssText = `width:18px; height:18px; border-radius:4px; background:${c}; border:0.5px solid var(--line-2); cursor:pointer; flex-shrink:0;`;
      d.addEventListener('click', () => { const hsv = hexToHsv(c); self._h=hsv.h; self._s=hsv.s; self._v=hsv.v; self._drawAll(); self._emit(); });
      presetsEl.appendChild(d);
    });

    root.appendChild(specWrap);
    root.appendChild(hueWrap);
    root.appendChild(hexRow);
    root.appendChild(presetsEl);

    // Refs
    this._root = root;
    this._spec = spec;
    this._specCursor = specCursor;
    this._hueBar = hueBar;
    this._hueThumb = hueThumb;
    this._swatch = swatch;
    this._hexInput = hexInput;

    // Events spectre
    let draggingSpec = false;
    const onSpecMove = e => {
      const r = spec.getBoundingClientRect();
      const cx = e.touches ? e.touches[0].clientX : e.clientX;
      const cy = e.touches ? e.touches[0].clientY : e.clientY;
      self._s = clamp((cx - r.left) / r.width, 0, 1);
      self._v = clamp(1 - (cy - r.top) / r.height, 0, 1);
      self._drawAll(); self._emit();
    };
    specWrap.addEventListener('mousedown', e => { draggingSpec = true; onSpecMove(e); e.preventDefault(); });
    specWrap.addEventListener('touchstart', e => { draggingSpec = true; onSpecMove(e); }, { passive: true });
    document.addEventListener('mousemove', e => { if (draggingSpec) onSpecMove(e); });
    document.addEventListener('touchmove', e => { if (draggingSpec) onSpecMove(e); }, { passive: true });
    document.addEventListener('mouseup',  () => { draggingSpec = false; });
    document.addEventListener('touchend', () => { draggingSpec = false; });

    // Events hue
    let draggingHue = false;
    const onHueMove = e => {
      const r = hueBar.getBoundingClientRect();
      const cx = e.touches ? e.touches[0].clientX : e.clientX;
      self._h = clamp((cx - r.left) / r.width, 0, 1) * 360;
      self._drawAll(); self._emit();
    };
    hueBar.addEventListener('mousedown', e => { draggingHue = true; onHueMove(e); e.preventDefault(); });
    hueBar.addEventListener('touchstart', e => { draggingHue = true; onHueMove(e); }, { passive: true });
    document.addEventListener('mousemove', e => { if (draggingHue) onHueMove(e); });
    document.addEventListener('touchmove', e => { if (draggingHue) onHueMove(e); }, { passive: true });
    document.addEventListener('mouseup',  () => { draggingHue = false; });
    document.addEventListener('touchend', () => { draggingHue = false; });

    // Hex input
    hexInput.addEventListener('input', () => {
      const v = hexInput.value;
      if (/^#[0-9a-fA-F]{6}$/.test(v)) {
        const hsv = hexToHsv(v);
        self._h = hsv.h; self._s = hsv.s; self._v = hsv.v;
        self._drawSpec(); self._updateUI(); self._emit();
      }
    });

    this.el = root;
  };

  JarvisColorPicker.prototype._drawSpec = function () {
    const canvas = this._spec;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const gW = ctx.createLinearGradient(0, 0, W, 0);
    gW.addColorStop(0, '#fff');
    gW.addColorStop(1, `hsl(${this._h}, 100%, 50%)`);
    ctx.fillStyle = gW;
    ctx.fillRect(0, 0, W, H);
    const gB = ctx.createLinearGradient(0, 0, 0, H);
    gB.addColorStop(0, 'rgba(0,0,0,0)');
    gB.addColorStop(1, '#000');
    ctx.fillStyle = gB;
    ctx.fillRect(0, 0, W, H);
  };

  JarvisColorPicker.prototype._drawHue = function () {
    const canvas = this._hueBar;
    const ctx = canvas.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, canvas.width, 0);
    for (let i = 0; i <= 12; i++) g.addColorStop(i/12, `hsl(${i*30}, 100%, 50%)`);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  };

  JarvisColorPicker.prototype._updateUI = function () {
    const hex = hsvToHex(this._h, this._s, this._v);
    this._swatch.style.background = hex;
    this._hexInput.value = hex;
    // Cursor position
    const sw = this._spec.getBoundingClientRect().width || this._spec.width;
    const sh = this._spec.getBoundingClientRect().height || this._spec.height;
    this._specCursor.style.left = (this._s * 100) + '%';
    this._specCursor.style.top  = ((1 - this._v) * 100) + '%';
    // Hue thumb
    this._hueThumb.style.left = (this._h / 360 * 100) + '%';
  };

  JarvisColorPicker.prototype._drawAll = function () {
    this._drawSpec();
    this._drawHue();
    this._updateUI();
  };

  JarvisColorPicker.prototype._emit = function () {
    this._onChange(hsvToHex(this._h, this._s, this._v));
  };

  JarvisColorPicker.prototype.setValue = function (hex) {
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return;
    const hsv = hexToHsv(hex);
    this._h = hsv.h; this._s = hsv.s; this._v = hsv.v;
    this._drawAll();
  };

  JarvisColorPicker.prototype.show = function () {
    this._root.style.display = 'flex';
    this._drawAll(); // redraw au cas où le canvas était caché
  };

  JarvisColorPicker.prototype.hide = function () {
    this._root.style.display = 'none';
  };

  JarvisColorPicker.prototype.toggle = function () {
    if (this._root.style.display === 'none' || !this._root.style.display) this.show();
    else this.hide();
  };

  JarvisColorPicker.prototype.destroy = function () {
    if (this._root.parentNode) this._root.parentNode.removeChild(this._root);
  };

  global.JarvisColorPicker = JarvisColorPicker;

})(window);
