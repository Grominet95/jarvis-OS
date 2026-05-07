/* settings-charts.js — SVG charts vanilla pour la page Conso
 * Expose: window.JarvisCharts.{donut, areaStack, heatRow}
 */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  function svg(w, h) {
    const s = document.createElementNS(NS, "svg");
    s.setAttribute("width", w); s.setAttribute("height", h);
    s.setAttribute("viewBox", "0 0 " + w + " " + h);
    return s;
  }
  function n(tag, attrs) {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  /* Donut */
  function donut(data, opts) {
    opts = opts || {};
    const size = opts.size || 140;
    const thickness = opts.thickness || 20;
    const r = (size - thickness) / 2;
    const cx = size / 2, cy = size / 2;
    const total = data.reduce((s, d) => s + d.value, 0) || 1;
    const root = svg(size, size);

    let a0 = -Math.PI / 2;
    data.forEach(d => {
      const frac = d.value / total;
      const a1 = a0 + frac * Math.PI * 2;
      const large = frac > 0.5 ? 1 : 0;
      const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
      const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
      const path = n("path", {
        d: `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`,
        fill: "none", stroke: d.color, "stroke-width": thickness, "stroke-linecap": "butt",
      });
      root.appendChild(path);
      a0 = a1;
    });
    // Center text
    const total$ = "$" + total.toFixed(0);
    const t = n("text", { x: cx, y: cy - 2, "text-anchor": "middle", "font-family": "var(--serif)", "font-size": "22", "font-weight": "300", fill: "var(--fg-0)" });
    t.textContent = total$; root.appendChild(t);
    const t2 = n("text", { x: cx, y: cy + 14, "text-anchor": "middle", "font-family": "var(--mono)", "font-size": "9.5", "letter-spacing": "0.16em", fill: "var(--fg-3)" });
    t2.textContent = "TOTAL"; root.appendChild(t2);
    return root;
  }

  /* Stacked area */
  function areaStack(series, opts) {
    opts = opts || {};
    const w = opts.width || 900, h = opts.height || 220;
    const padL = 36, padR = 8, padT = 8, padB = 22;
    const innerW = w - padL - padR, innerH = h - padT - padB;
    const len = (series[0] && series[0].data.length) || 0;
    if (!len) return svg(w, h);

    // Compute stacked totals at each step
    const stacked = series.map(() => new Array(len).fill(0));
    const totals = new Array(len).fill(0);
    for (let i = 0; i < len; i++) {
      let cum = 0;
      series.forEach((s, si) => {
        cum += s.data[i] || 0;
        stacked[si][i] = cum;
        if (cum > totals[i]) totals[i] = cum;
      });
    }
    const maxY = Math.max.apply(null, totals) * 1.05 || 1;
    const x = i => padL + (i / (len - 1)) * innerW;
    const y = v => padT + innerH - (v / maxY) * innerH;

    const root = svg(w, h);

    // Grid
    [0.25, 0.5, 0.75, 1].forEach(p => {
      root.appendChild(n("line", {
        x1: padL, x2: padL + innerW,
        y1: padT + innerH * (1 - p), y2: padT + innerH * (1 - p),
        stroke: "var(--line-1)", "stroke-dasharray": "2 4",
      }));
    });

    // Stacked areas (back to front)
    for (let si = series.length - 1; si >= 0; si--) {
      const s = series[si];
      const upper = stacked[si];
      const lower = si === 0 ? new Array(len).fill(0) : stacked[si - 1];
      let d = "";
      for (let i = 0; i < len; i++) d += (i === 0 ? "M " : "L ") + x(i) + " " + y(upper[i]) + " ";
      for (let i = len - 1; i >= 0; i--) d += "L " + x(i) + " " + y(lower[i]) + " ";
      d += "Z";
      root.appendChild(n("path", { d, fill: s.color, "fill-opacity": "0.35", stroke: s.color, "stroke-width": "1", "stroke-opacity": "0.85" }));
    }

    // Y axis labels
    [0.25, 0.5, 0.75, 1].forEach(p => {
      const v = maxY * p;
      const t = n("text", { x: padL - 8, y: padT + innerH * (1 - p) + 3, "text-anchor": "end", "font-family": "var(--mono)", "font-size": "9.5", fill: "var(--fg-3)" });
      t.textContent = "$" + v.toFixed(0);
      root.appendChild(t);
    });
    // X axis labels (J-29, J-15, J-1)
    ["J-29","J-15","J-1"].forEach((lbl, idx) => {
      const i = idx === 0 ? 0 : idx === 1 ? Math.floor(len / 2) : len - 1;
      const t = n("text", { x: x(i), y: h - 4, "text-anchor": "middle", "font-family": "var(--mono)", "font-size": "9.5", fill: "var(--fg-3)" });
      t.textContent = lbl;
      root.appendChild(t);
    });
    return root;
  }

  /* Heat row (24h hourly) */
  function heatRow(values, opts) {
    opts = opts || {};
    const h = opts.height || 20;
    const color = opts.color || "var(--accent)";
    const max = Math.max.apply(null, values) || 1;
    const wrap = document.createElement("div");
    wrap.style.display = "grid";
    wrap.style.gridTemplateColumns = "repeat(" + values.length + ", 1fr)";
    wrap.style.gap = "2px";
    values.forEach(v => {
      const cell = document.createElement("div");
      cell.style.height = h + "px";
      cell.style.borderRadius = "2px";
      cell.style.background = color;
      cell.style.opacity = (0.15 + (v / max) * 0.85).toFixed(2);
      wrap.appendChild(cell);
    });
    return wrap;
  }

  window.JarvisCharts = { donut, areaStack, heatRow };
})();
