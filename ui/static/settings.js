/* settings.js — Page Système (vanilla)
 * Sessions · Mémoire · Outils · Conso · Paramètres · Système (logs)
 */
(function () {
  "use strict";
  const J = window.Jarvis, el = J.el;
  const Charts = window.JarvisCharts;

  /* ───────── Mocks (TODO: replace with API) ───────── */
  const SESSIONS = [
    { id: "s_8a14", agent: "librarian",  start: "14:08:42", dur: "00:24:18", calls: 142, tok: "184.2k", status: "RUN",  cls: "ok" },
    { id: "s_8a13", agent: "editor",     start: "13:51:09", dur: "00:41:03", calls: 86,  tok: "312.0k", status: "RUN",  cls: "ok" },
    { id: "s_8a12", agent: "scheduler",  start: "13:42:00", dur: "00:08:11", calls: 24,  tok: "12.4k",  status: "WAIT", cls: "warn" },
    { id: "s_8a11", agent: "finops",     start: "12:00:00", dur: "02:32:18", calls: 412, tok: "44.1k",  status: "RUN",  cls: "ok" },
    { id: "s_8a10", agent: "digest",     start: "09:00:00", dur: "00:01:42", calls: 6,   tok: "8.2k",   status: "DONE", cls: "info" },
    { id: "s_8a0f", agent: "triager",    start: "08:14:22", dur: "00:00:54", calls: 12,  tok: "4.4k",   status: "DONE", cls: "info" },
  ];
  const MEM_GROUPS = [
    { id: "global",  label: "Global" },
    { id: "prefs",   label: "Préférences" },
    { id: "tools",   label: "Par outil" },
    { id: "context", label: "Contexte long-terme" },
  ];
  const MEM_FILES = [
    { id:"m1", group:"global",  name:"identity.md",        path:"global/identity.md",        size:"4.2 KB", pin:true,
      body:{ title:"identity.md", fm:{Type:"global",Updated:"2026-04-28",Pinned:"true",Tokens:"1,142"}, sections:[
        {p:["Marc, 32 ans, basé à Paris. Créateur de contenu YouTube (414K subs) sur la tech, l'IA et la productivité. Travaille en solo, full-remote."]},
        {h:"Style de communication", p:["Direct, peu de fioritures, jamais de small talk inutile. Préfère les réponses denses au verbiage. Tutoiement par défaut."]},
        {h:"Préférences", list:["Travaille mieux le matin (06:00 — 12:00)","Sport : 17:00 — 18:30 (ne pas planifier dessus)","Pas de réunion le vendredi"]},
      ]}},
    { id:"m2", group:"global",  name:"objectives-q2.md",   path:"global/objectives-q2.md",   size:"2.8 KB", pin:true,
      body:{ title:"objectives-q2.md", fm:{Type:"global",Updated:"2026-04-12",Pinned:"true",Tokens:"784"}, sections:[
        {h:"Objectifs Q2 2026", list:["Atteindre 500K subs YouTube (actuel : 414K)","Lancer la formation 'Build Your Own Jarvis' en juin","Réduire le temps email à <30 min/jour"]},
        {h:"Note", p:["Réviser fin mai. Si en retard sur subs, pivoter sur les shorts."]},
      ]}},
    { id:"m3", group:"prefs",   name:"writing-style.md",   path:"preferences/writing-style.md", size:"3.1 KB",
      body:{ title:"writing-style.md", fm:{Type:"preference",Updated:"2026-05-02",Used:"editor, digest"}, sections:[
        {h:"Voix", p:["Phrases courtes. Une idée par phrase. Éviter les adverbes faibles."]},
        {h:"À bannir", list:["Les listes à 7+ points","Les conclusions qui résument l'article","Les questions rhétoriques"]},
        {h:"À utiliser", list:["Métaphores concrètes, jamais abstraites","Exemples avec chiffres précis","Anecdotes personnelles datées"]},
      ]}},
    { id:"m4", group:"prefs",   name:"coding.md",          path:"preferences/coding.md",        size:"1.8 KB",
      body:{ title:"coding.md", fm:{Type:"preference",Updated:"2026-03-18",Used:"editor, planner"}, sections:[
        {h:"Stack par défaut", list:["TypeScript + Bun","Tailwind v4","SQLite local-first quand possible"]},
        {h:"Style", p:["2 espaces, pas de point-virgule. Components en kebab-case."]},
      ]}},
    { id:"m5", group:"tools",   name:"email.md",           path:"tools/email.md",               size:"5.4 KB",
      body:{ title:"email.md", fm:{Type:"tool-memory",Tool:"email.imap",Updated:"il y a 12 min"}, sections:[
        {h:"Triage automatique", list:["Newsletters → archive après 7j","Sponsors YouTube → label 'biz' + notif","Famille → toujours top inbox"]},
        {h:"Brouillons fréquents", p:["Réponses sponsor : tarif 2026 = 8K€/intégration. Brief 7j avant, droit de refus."]},
      ]}},
    { id:"m6", group:"tools",   name:"calendar.md",        path:"tools/calendar.md",            size:"2.2 KB",
      body:{ title:"calendar.md", fm:{Type:"tool-memory",Tool:"calendar",Updated:"il y a 3h"}, sections:[
        {h:"Règles de scheduling", list:["Pas de meeting avant 10:00","Buffer 15 min entre meetings","Vendredi = 0 meeting"]},
        {h:"Récurrents", list:["Lundi 11:00 — review hebdo","Mercredi 15:00 — sync éditeur vidéo"]},
      ]}},
    { id:"m7", group:"tools",   name:"youtube.md",         path:"tools/youtube.md",             size:"4.1 KB",
      body:{ title:"youtube.md", fm:{Type:"tool-memory",Tool:"youtube.api",Updated:"hier"}, sections:[
        {h:"Patterns de titre qui marchent", list:["Ne pas commencer par 'Comment'","Inclure un chiffre concret","Tension dans les 3 premiers mots"]},
        {h:"Thumbnails", p:["Visage à gauche, texte à droite, max 4 mots. Pas de flèche rouge."]},
      ]}},
    { id:"m8", group:"tools",   name:"finops.md",          path:"tools/finops.md",              size:"1.4 KB",
      body:{ title:"finops.md", fm:{Type:"tool-memory",Tool:"finops",Updated:"il y a 6h"}, sections:[
        {h:"Budgets", list:["OpenAI : $200/mois (alerte $180)","Anthropic : $250/mois (alerte $220)","Cumulé infra : $500/mois max"]},
      ]}},
    { id:"m9", group:"context", name:"projects-active.md", path:"context/projects-active.md",   size:"6.8 KB",
      body:{ title:"projects-active.md", fm:{Type:"context",Updated:"il y a 2j",Tokens:"1,940"}, sections:[
        {h:"Formation BYO Jarvis", p:["Lancement 12 juin 2026. 8 modules, 14h. Tarif early-bird : 297€."]},
        {h:"Refonte site perso",   p:["Stack : Astro + Tailwind v4. Maquettes faites. Après la formation."]},
      ]}},
    { id:"m10", group:"context",name:"learnings.md",       path:"context/learnings.md",         size:"12.4 KB",
      body:{ title:"learnings.md", fm:{Type:"context",Updated:"il y a 4j",Tokens:"3,420"}, sections:[
        {h:"Insights", list:["Les vidéos >12 min performent moins depuis mars 2026","Newsletter ouverte 2x plus si envoyée jeudi 09:00","Sleep <7h ⇒ output créatif /2 le lendemain"]},
      ]}},
  ];
  const TOOLS = [
    { glyph:"fs",  name:"filesystem",        sub:"read · write · search local files", calls:1842, lat:"12 ms",  on:true  },
    { glyph:"wb",  name:"web · browser",     sub:"playwright headless · 6 sessions",   calls:412,  lat:"1.2 s",  on:true  },
    { glyph:"em",  name:"email · imap",      sub:"Gmail OAuth · 4 mailboxes",          calls:287,  lat:"340 ms", on:true  },
    { glyph:"cal", name:"calendar",          sub:"Google Calendar · read+write",       calls:92,   lat:"180 ms", on:true  },
    { glyph:"yt",  name:"youtube · api",     sub:"v3 · stats + uploads",               calls:41,   lat:"240 ms", on:true  },
    { glyph:"x",   name:"x · twitter",       sub:"posting + analytics · OAuth2",       calls:28,   lat:"410 ms", on:false },
    { glyph:"vec", name:"vector · pinecone", sub:"ix-personal · 1536d",                calls:2104, lat:"48 ms",  on:true  },
    { glyph:"fin", name:"finance · plaid",   sub:"3 comptes liés · read-only",         calls:14,   lat:"1.1 s",  on:false },
  ];
  const PROVIDERS = [
    { name:"Anthropic",  color:"#D97757", cost:"$184.20", tok:"12.4M" },
    { name:"OpenAI",     color:"#10A37F", cost:"$112.80", tok:"8.2M"  },
    { name:"Pinecone",   color:"#4A9EFF", cost:"$32.40",  tok:"—"     },
    { name:"ElevenLabs", color:"#B8963E", cost:"$24.10",  tok:"1.8M"  },
    { name:"Mapbox",     color:"#36D399", cost:"$18.00",  tok:"—"     },
  ];
  function genSeries(base, vol, len) {
    const out=[]; let v=base;
    for (let i=0;i<len;i++){ v=Math.max(0,v+(Math.random()-0.45)*vol); out.push(Number(v.toFixed(2))); }
    return out;
  }
  const CONSO_SERIES = [
    { name:"Anthropic",  color:"#D97757", data: genSeries(5.5,1.6,30) },
    { name:"OpenAI",     color:"#10A37F", data: genSeries(3.6,1.2,30) },
    { name:"Pinecone",   color:"#4A9EFF", data: genSeries(1.2,0.4,30) },
    { name:"ElevenLabs", color:"#B8963E", data: genSeries(0.8,0.3,30) },
    { name:"Mapbox",     color:"#36D399", data: genSeries(0.6,0.2,30) },
  ];
  const USAGE_TYPES = [
    { name:"Échange direct",        sub:"chat synchrone · Marc ↔ Jarvis",  pct:0.34, cost:"$126.30", tok:"6.4M",  color:"#4A9EFF" },
    { name:"Agents en arrière-plan",sub:"missions autonomes · 24/7",       pct:0.41, cost:"$152.10", tok:"9.8M",  color:"#D97757" },
    { name:"Indexation & embeddings",sub:"vector store · batch nightly",   pct:0.14, cost:"$52.00",  tok:"2.1M",  color:"#B8963E" },
    { name:"Voice · STT/TTS",       sub:"transcription + synthèse",        pct:0.08, cost:"$28.40",  tok:"—",     color:"#36D399" },
    { name:"Outils · web/scrape",   sub:"playwright + parsing",            pct:0.03, cost:"$12.70",  tok:"—",     color:"rgba(220,232,255,0.55)" },
  ];
  const HOURLY = Array.from({length:24},(_,i)=>{ const peak=i>=8&&i<=19?1:0.3; return Math.round((Math.random()*0.5+0.5)*peak*100); });
  const LOG_SEED = [
    { lv:"ok",   parts:[{t:"agent.librarian",cls:"accent"},{t:" · indexed 96/142 documents "},{t:"(cosine ≥ 0.78)",cls:"dim"}] },
    { lv:"info", parts:[{t:"scheduler",cls:"accent"},{t:" · proposed 3 reschedule slots "},{t:"awaiting human",cls:"dim"}] },
    { lv:"info", parts:[{t:"tool "},{t:"vector.pinecone",cls:"accent"},{t:" · 412 upserts "},{t:"batch 8/8",cls:"dim"}] },
    { lv:"warn", parts:[{t:"rate-limit nearing on "},{t:"openai.gpt5",cls:"accent"},{t:" "},{t:"(82% of 10k req/min)",cls:"dim"}] },
    { lv:"ok",   parts:[{t:"finops",cls:"accent"},{t:" · daily spend within budget "},{t:"($12.40 / $20.00)",cls:"dim"}] },
    { lv:"info", parts:[{t:"memory page "},{t:"0x4F",cls:"accent"},{t:" evicted "},{t:"(LRU · cold for 7d)",cls:"dim"}] },
    { lv:"err",  parts:[{t:"tool "},{t:"x.twitter",cls:"accent"},{t:" · auth refresh failed "},{t:"(401 · re-link required)",cls:"dim"}] },
    { lv:"ok",   parts:[{t:"editor",cls:"accent"},{t:" · draft saved "},{t:"v3 · 1842 words",cls:"dim"}] },
  ];

  /* ───────── Card / sec helpers ───────── */
  function card(opts, children) {
    const c = el("div", { class: "card" });
    if (opts.title || opts.right) {
      c.appendChild(el("div", { class: "card-hd" }, [
        el("div", {}, [
          el("div", { class: "card-title", text: opts.title }),
          opts.sub ? el("div", { class: "card-sub", text: opts.sub }) : null,
        ]),
        opts.right || null,
      ]));
    }
    (Array.isArray(children) ? children : [children]).forEach(ch => ch && c.appendChild(ch));
    return c;
  }
  function secHd(num, title, display, right) {
    return el("div", { class: "sec-hd" }, [
      el("div", { class: "sec-hd-l" }, [
        el("div", { class: "sec-hd-row" }, [
          el("span", { class: "sec-hd-num", text: num }),
          el("span", { class: "sec-hd-title", text: title }),
        ]),
        el("span", { class: "sec-hd-disp", text: display }),
      ]),
      right ? el("div", { class: "sec-hd-r", text: right }) : null,
    ]);
  }

  /* ───────── Sessions ───────── */
  async function renderSessions(root) {
    // SHAPE EXPECTED: [{ id, agent (=preview/title), start (=date), dur, calls (=message_count), tok, status, cls }]
    // Backend GET /api/sessions → [{ id, date, preview, title, message_count }]
    // No live calls/tokens count in backend — shows message_count as "msgs"
    root.innerHTML = '<div class="surface"><div class="j-loading">Chargement…</div></div>';
    let sessions = SESSIONS;
    try {
      const raw = await J.api.get("/api/sessions");
      if (raw && raw.length) {
        sessions = raw.map(s => ({
          id:     s.id ? s.id.slice(0, 6) : "?",
          agent:  s.title || s.preview || "session",
          start:  s.date || "—",
          dur:    "—",
          calls:  s.message_count || 0,
          tok:    "—",
          status: "DONE",
          cls:    "info",
        }));
      }
    } catch (_) { /* keep mock */ }

    root.innerHTML = "";
    root.appendChild(secHd("01", "Sessions", "Historique des conversations", sessions.length + " sessions"));
    const list = el("div");
    list.appendChild(el("div", {
      class: "row-tab",
      style: { borderTop:"0", paddingTop:"0", paddingBottom:"10px", color:"var(--fg-3)", fontFamily:"var(--mono)", fontSize:"10px", letterSpacing:".1em", textTransform:"uppercase" },
    }, [
      el("span", { text: "ID" }),
      el("span", { text: "Titre · date" }),
      el("span", { style:{textAlign:"right"}, text: "Msgs" }),
      el("span", { style:{textAlign:"right"}, text: "Tokens" }),
      el("span", { style:{textAlign:"right"}, text: "State" }),
    ]));
    sessions.forEach(s => {
      list.appendChild(el("div", { class: "row-tab" }, [
        el("span", { class: "rt-id", text: s.id }),
        el("span", { class: "rt-name" }, [
          document.createTextNode(s.agent),
          el("span", { class: "rt-sub", text: "started " + s.start + " · " + s.dur }),
        ]),
        el("span", { class: "rt-num", text: s.calls }),
        el("span", { class: "rt-num", text: s.tok }),
        el("span", { class: "rt-status", style: { color: s.cls === "ok" ? "var(--green)" : s.cls === "warn" ? "var(--gold)" : "var(--fg-3)" }, text: "● " + s.status }),
      ]));
    });
    root.appendChild(card({
      title: "Sessions", sub: sessions.length + " sessions · historique",
      right: el("button", { class: "btn-ghost", text: "Stream live ●" }),
    }, list));
  }

  /* ───────── Markdown renderer ───────── */
  function mdToHtml(text) {
    function esc(s) {
      return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function inline(s) {
      s = esc(s);
      s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
      s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
      return s;
    }
    const lines = text.split("\n");
    const out = [];
    let inList = false;
    for (const raw of lines) {
      const line = raw.trimEnd();
      const t = line.trim();
      if (t.startsWith("### ")) {
        if (inList) { out.push("</ul>"); inList = false; }
        out.push("<h3>" + inline(t.slice(4)) + "</h3>");
      } else if (t.startsWith("## ")) {
        if (inList) { out.push("</ul>"); inList = false; }
        out.push("<h2>" + inline(t.slice(3)) + "</h2>");
      } else if (t.startsWith("# ")) {
        if (inList) { out.push("</ul>"); inList = false; }
        out.push("<h1>" + inline(t.slice(2)) + "</h1>");
      } else if (t.startsWith("- ") || t.startsWith("* ")) {
        if (!inList) { out.push("<ul>"); inList = true; }
        out.push("<li>" + inline(t.slice(2)) + "</li>");
      } else if (!t) {
        if (inList) { out.push("</ul>"); inList = false; }
      } else {
        if (inList) { out.push("</ul>"); inList = false; }
        out.push("<p>" + inline(t) + "</p>");
      }
    }
    if (inList) out.push("</ul>");
    return out.join("");
  }

  /* ───────── Memory ───────── */
  async function renderMemory(root) {
    // SHAPE EXPECTED (MEM_FILES): [{ id, group, name, path, size, pin, body:{title,fm,sections} }]
    // Backend GET /api/memory/topics → [{ name, size, mtime }]
    // Backend GET /api/memory/topics/{name} → { name, content }
    // Transformation: topics are flat (no groups), displayed in a single "global" group
    // body (viewer content) is loaded on-demand when a file is selected
    root.innerHTML = '<div class="surface"><div class="j-loading">Chargement…</div></div>';
    let memFiles = MEM_FILES;
    try {
      const raw = await J.api.get("/api/memory/topics");
      if (raw && raw.length) {
        memFiles = raw.map((t, i) => ({
          id:    "t" + i,
          group: "global",
          name:  t.name,
          path:  t.name,
          size:  t.size > 1024 ? (t.size / 1024).toFixed(1) + " KB" : t.size + " B",
          pin:   false,
          body:  null,  // loaded on-demand
        }));
      }
    } catch (_) { /* keep mock */ }

    root.innerHTML = "";
    root.appendChild(secHd("02", "Mémoire", "Ce que Jarvis sait de toi", memFiles.length + " fichiers"));

    const firstId = memFiles.length > 0 ? memFiles[0].id : null;
    let selectedId = firstId, query = "";
    const cardEl = card({
      title: "Mémoire", sub: memFiles.length + " fichiers · markdown",
      right: el("div", { style: { display: "flex", gap: "6px" } }, [
        el("button", { class: "btn-ghost", text: "+ New" }),
        el("button", { class: "btn-ghost", text: "Reindex" }),
      ]),
    });

    // Stats
    const stats = el("div", { class: "mem-stats" });
    [
      ["Fichiers", String(memFiles.length), memFiles.length + " fichiers",null],
      ["Pinnés",   "—",   "non implémenté","var(--gold)"],
    ].forEach(([lbl,val,sub,col]) => {
      stats.appendChild(el("div", { class: "mem-stat" }, [
        el("div", { class: "ms-lbl", text: lbl }),
        el("div", { class: "ms-val", style: col?{color:col}:{}, text: val }),
        el("div", { class: "ms-sub", text: sub }),
      ]));
    });
    cardEl.appendChild(stats);

    const layout = el("div", { class: "mem-layout" });
    const listCol = el("div", { class: "mem-list" });
    const viewCol = el("div", { class: "mem-view" });

    // Use a flat group for API-sourced files (no groups metadata from backend)
    const groups = [{ id: "global", label: "Topics" }];
    const filesWithGroup = memFiles.map(f => Object.assign({ group: "global" }, f));

    async function loadFileContent(file) {
      if (file.body) return;
      try {
        const data = await J.api.get("/api/memory/topics/" + encodeURIComponent(file.name));
        file.body = {
          title: file.name,
          fm: { Fichier: file.name, Taille: file.size },
          raw: data.content || "",
        };
      } catch (_) {
        file.body = { title: file.name, fm: {}, raw: "_Contenu non disponible._" };
      }
    }

    async function rerenderViewer() {
      const file = filesWithGroup.find(f => f.id === selectedId) || filesWithGroup[0];
      if (!file) { viewCol.innerHTML = '<div class="j-empty">Aucun fichier sélectionné.</div>'; return; }
      if (!file.body) {
        viewCol.innerHTML = '<div class="j-loading">Chargement…</div>';
        await loadFileContent(file);
      }
      viewCol.innerHTML = "";
      const vhd = el("div", { class: "mem-view-hd" }, [
        el("div", { class: "mem-view-hd-l" }, [
          el("span", { class: "mvh-name", text: file.body.title }),
          el("span", { class: "mvh-meta" }, [
            el("span", { text: file.path }),
            el("span", { text: "·" }),
            el("span", { text: file.size }),
            file.pin ? el("span", { text: "·" }) : null,
            file.pin ? el("span", { style:{color:"var(--gold)"}, text: "● PINNED" }) : null,
          ]),
        ]),
        el("div", { class: "mem-view-hd-r" }, [
          el("button", { class: "btn-ghost", text: "Edit" }),
          el("button", { class: "btn-ghost", text: "⋯" }),
        ]),
      ]);
      viewCol.appendChild(vhd);
      const md = el("div", { class: "mem-md" });
      if (Object.keys(file.body.fm).length > 0) {
        const dl = el("dl", { class: "frontmatter" });
        Object.keys(file.body.fm).forEach(k => {
          dl.appendChild(el("dt", { text: k }));
          const v = file.body.fm[k];
          if (k === "Pinned" && v === "true") dl.appendChild(el("dd", {}, [el("span", { class: "pin", text: "● true" })]));
          else dl.appendChild(el("dd", { text: v }));
        });
        md.appendChild(dl);
      }
      const content = el("div", { class: "mem-md-body" });
      content.innerHTML = mdToHtml(file.body.raw || "");
      md.appendChild(content);
      viewCol.appendChild(md);
    }

    function rerender() {
      listCol.innerHTML = "";
      const hd = el("div", { class: "mem-list-hd" }, [
        el("div", { class: "t-eyebrow" }, [
          el("span", { text: "memory · topics" }),
          el("span", { text: filesWithGroup.length }),
        ]),
        el("input", { class: "mem-search", placeholder: "⌘ rechercher…", value: query,
          oninput: (e) => { query = e.target.value; rerender(); } }),
      ]);
      listCol.appendChild(hd);
      const scroll = el("div", { class: "scroll-y", style: { flex:"1" } });
      groups.forEach(g => {
        const items = filesWithGroup.filter(f => f.group === g.id && (!query || (f.name+f.path).toLowerCase().indexOf(query.toLowerCase()) >= 0));
        const grp = el("div", { class: "mem-group" });
        grp.appendChild(el("div", { class: "mem-group-hd" }, [
          el("span", { text: g.label }),
          el("span", { text: items.length }),
        ]));
        items.forEach(f => {
          grp.appendChild(el("div", {
            class: "mem-file" + (selectedId === f.id ? " is-on" : ""),
            onclick: () => { selectedId = f.id; rerender(); rerenderViewer(); },
          }, [
            el("span", { class: "mf-glyph", text: f.pin ? "●" : "md" }),
            el("span", { class: "mf-name" }, [
              el("span", { style:{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}, text: f.name }),
              el("span", { class: "mf-path", text: f.path }),
            ]),
            el("span", { class: "mf-size", text: f.size }),
          ]));
        });
        scroll.appendChild(grp);
      });
      listCol.appendChild(scroll);
    }
    rerender();
    rerenderViewer();
    layout.appendChild(listCol); layout.appendChild(viewCol);
    cardEl.appendChild(layout);
    root.appendChild(cardEl);
  }

  /* ───────── Tools ───────── */
  async function renderTools(root) {
    root.innerHTML = '<div class="surface"><div class="j-loading">Chargement…</div></div>';

    // Fetch installed skills + catalog in parallel
    let installed = [], catalog = [], offline = false;
    try {
      const [instRes, catRes] = await Promise.all([
        J.api.get("/api/skills/installed"),
        J.api.get("/api/skills/catalog"),
      ]);
      installed = (instRes && instRes.skills) ? instRes.skills : [];
      catalog   = (catRes  && catRes.skills)  ? catRes.skills  : [];
      offline   = !!(catRes && catRes.offline);
    } catch (_) { /* keep empty */ }

    root.innerHTML = "";

    /* ─── Section 1 : Skills actifs ─────────────────────────── */
    const reloadBtn = el("button", { class: "btn-ghost", text: "↺ Recharger" });
    root.appendChild(secHd("01", "Skills actifs", "Extensions chargées par Jarvis", installed.length + " actif(s)"));

    const activeList = el("div");
    const searchInput = el("input", {
      class: "mem-search",
      placeholder: "Rechercher un skill…",
      style: { width: "100%", marginBottom: "12px", boxSizing: "border-box" },
    });

    function renderInstalled() {
      activeList.innerHTML = "";
      if (!installed.length) {
        activeList.appendChild(el("div", {
          class: "card-sub",
          style: { padding: "12px 0", opacity: "0.6" },
          text: "Aucun skill installé. Utilisez la Marketplace ci-dessous.",
        }));
        return;
      }
      installed.forEach(s => {
        const requiresEnv  = s.requires_env  || [];
        const envStatus    = s.env_status    || {};
        const configured   = s.configured !== false || !requiresEnv.length;

        const confirmWrap = el("div", { style: { display: "none", gap: "8px" } });
        const confirmBtn  = el("button", { class: "btn-ghost", style: { color: "var(--red, #f55)" }, text: "Confirmer" });
        const cancelBtn   = el("button", { class: "btn-ghost", text: "Annuler" });
        confirmWrap.appendChild(confirmBtn);
        confirmWrap.appendChild(cancelBtn);

        const uninstallBtn = el("button", { class: "btn-ghost", text: "Désinstaller" });
        uninstallBtn.onclick = () => {
          uninstallBtn.style.display = "none";
          confirmWrap.style.display  = "flex";
        };
        cancelBtn.onclick = () => {
          confirmWrap.style.display  = "none";
          uninstallBtn.style.display = "";
        };
        confirmBtn.onclick = async () => {
          confirmBtn.disabled = true;
          confirmBtn.textContent = "…";
          try {
            const r = await fetch("/api/skills/uninstall/" + encodeURIComponent(s.name), { method: "DELETE" });
            const data = await r.json();
            if (data.success) {
              J.notify({ kind: "info", text: "Skill désinstallé : " + s.name });
              installed = installed.filter(x => x.name !== s.name);
              catalog = catalog.map(c => c.name === s.name ? Object.assign({}, c, { installed: false }) : c);
              renderInstalled();
              renderMarket(searchInput.value.trim().toLowerCase());
            } else {
              J.notify({ kind: "error", text: data.message || "Erreur désinstallation" });
              confirmBtn.disabled = false;
              confirmBtn.textContent = "Confirmer";
              confirmWrap.style.display  = "none";
              uninstallBtn.style.display = "";
            }
          } catch (e) {
            J.notify({ kind: "error", text: "Erreur réseau : " + e.message });
          }
        };

        const tagsWrap = el("div", { style: { display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "4px" } });
        (s.tags || []).forEach(t => tagsWrap.appendChild(el("span", {
          style: { background: "var(--surface-2,rgba(255,255,255,.06))", borderRadius: "4px", padding: "1px 6px", fontSize: "10px", color: "var(--fg-3)" },
          text: t,
        })));

        // Badge config status
        const badge = requiresEnv.length
          ? el("span", {
              class: "skill-status-badge " + (configured ? "ok" : "warn"),
              text: configured ? "✓ Configuré" : "⚠ Configuration requise",
            })
          : null;

        // Inline env config section
        const SVG_EYE     = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
        const SVG_EYE_OFF = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
        const SVG_SAVE    = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;

        const envVals = s.env_values || {};
        const configSection = el("div", { class: "skill-config" });
        const statusIcons = {};

        requiresEnv.forEach(varKey => {
          const isSet    = envStatus[varKey] === true;
          const curValue = envVals[varKey] || "";

          const statusIcon = el("span", {
            class: "skill-config-status " + (isSet ? "ok" : "warn"),
            text: isSet ? "✓" : "⚠",
          });
          statusIcons[varKey] = statusIcon;

          const inputEl = document.createElement("input");
          inputEl.className = "skill-config-input";
          inputEl.type = "password";
          inputEl.placeholder = varKey;
          inputEl.value = curValue;

          const inputWrap = el("div", { class: "skill-config-input-wrap" });
          inputWrap.appendChild(inputEl);

          const revealBtn = document.createElement("button");
          revealBtn.className = "skill-config-reveal";
          revealBtn.title = "Afficher / masquer";
          revealBtn.innerHTML = SVG_EYE;
          let revealed = false;
          revealBtn.onclick = () => {
            revealed = !revealed;
            inputEl.type = revealed ? "text" : "password";
            revealBtn.innerHTML = revealed ? SVG_EYE_OFF : SVG_EYE;
          };
          inputWrap.appendChild(revealBtn);

          const saveBtn = document.createElement("button");
          saveBtn.className = "skill-config-save";
          saveBtn.title = "Sauvegarder";
          saveBtn.innerHTML = SVG_SAVE;
          saveBtn.onclick = async () => {
            const val = inputEl.value.trim();
            if (!val) return;
            saveBtn.disabled = true;
            try {
              await J.api.post("/api/settings/update", { key: varKey, value: val });
              const statusRes = await J.api.get(
                "/api/settings/env-status?keys=" + requiresEnv.join(",")
              );
              requiresEnv.forEach(k => {
                const nowSet = !!statusRes[k];
                if (statusIcons[k]) {
                  statusIcons[k].className = "skill-config-status " + (nowSet ? "ok" : "warn");
                  statusIcons[k].textContent = nowSet ? "✓" : "⚠";
                }
              });
              if (badge) {
                const allSet = requiresEnv.every(k => !!statusRes[k]);
                badge.className = "skill-status-badge " + (allSet ? "ok" : "warn");
                badge.textContent = allSet ? "✓ Configuré" : "⚠ Configuration requise";
              }
              J.notify({ kind: "success", text: varKey + " sauvegardé" });
              inputEl.type = "password";
              revealed = false;
              revealBtn.innerHTML = SVG_EYE;
            } catch (e) {
              J.notify({ kind: "error", text: "Erreur : " + e.message });
            }
            saveBtn.disabled = false;
          };

          const labelEl = el("span", { class: "skill-config-label", text: varKey });
          const row = el("div", { class: "skill-config-row" });
          row.appendChild(statusIcon);
          row.appendChild(labelEl);
          row.appendChild(inputWrap);
          row.appendChild(saveBtn);
          configSection.appendChild(row);
        });

        const infoCol = el("div", { style: { flex: 1 } });
        infoCol.appendChild(el("span", { style: { color: "var(--fg-0)" }, text: s.name }));
        infoCol.appendChild(el("span", { class: "tn-sub", text: " v" + (s.version || "1.0.0") + " · " + (s.author || "—") }));
        infoCol.appendChild(el("span", { class: "tn-sub", text: s.description || "" }));
        infoCol.appendChild(tagsWrap);
        if (badge) infoCol.appendChild(badge);
        if (requiresEnv.length) infoCol.appendChild(configSection);

        activeList.appendChild(el("div", { class: "tool-row", style: { alignItems: "start" } }, [
          el("div", { class: "tg", text: (s.name || "sk").slice(0, 2).toUpperCase() }),
          infoCol,
          el("div", { style: { display: "flex", flexDirection: "column", gap: "4px", alignItems: "flex-end" } }, [
            uninstallBtn,
            confirmWrap,
          ]),
        ]));
      });
    }

    reloadBtn.onclick = async () => {
      reloadBtn.disabled = true;
      reloadBtn.textContent = "…";
      try {
        const r = await J.api.post("/api/skills/reload", null);
        J.notify({ kind: "success", text: "Skills rechargés (" + (r.loaded || 0) + " actifs)" });
        const res = await J.api.get("/api/skills/installed");
        installed = (res && res.skills) ? res.skills : [];
        renderInstalled();
      } catch (e) {
        J.notify({ kind: "error", text: "Erreur reload : " + e.message });
      }
      reloadBtn.disabled = false;
      reloadBtn.textContent = "↺ Recharger";
    };

    renderInstalled();
    root.appendChild(card({
      title: "Skills actifs",
      sub:   installed.length + " / " + catalog.length + " skills disponibles",
      right: reloadBtn,
    }, activeList));

    /* ─── Section 2 : Marketplace ───────────────────────────── */
    root.appendChild(secHd("02", "Marketplace", "Catalogue jarvis-skills", ""));

    const onlineBadge = el("span", {
      style: { fontSize: "11px", opacity: "0.7" },
      text: offline ? "● Hors ligne" : "● En ligne",
    });
    if (offline) onlineBadge.title = "Catalogue local — repo GitHub inaccessible";

    const marketList = el("div");

    let marketTypeFilter = "all";

    const filterTabs = el("div", { style: { display: "flex", gap: "6px", marginBottom: "10px" } });
    ["Tous", "Skills", "Routines"].forEach(label => {
      const id = label === "Tous" ? "all" : label.toLowerCase();
      const btn = el("button", {
        class: "btn-ghost",
        text: label,
        style: { fontSize: "11px", opacity: id === "all" ? "1" : "0.5" },
      });
      btn.onclick = () => {
        marketTypeFilter = id;
        filterTabs.querySelectorAll("button").forEach(b => b.style.opacity = "0.5");
        btn.style.opacity = "1";
        renderMarket(searchInput.value.trim().toLowerCase());
      };
      filterTabs.appendChild(btn);
    });

    function renderMarket(filter) {
      marketList.innerHTML = "";
      let filtered = catalog;
      if (marketTypeFilter === "skills") {
        filtered = filtered.filter(s => (s.type || "conversational") !== "routine");
      } else if (marketTypeFilter === "routines") {
        filtered = filtered.filter(s => s.type === "routine");
      }
      if (filter) {
        filtered = filtered.filter(s =>
          s.name.toLowerCase().includes(filter) ||
          (s.description || "").toLowerCase().includes(filter) ||
          (s.tags || []).some(t => t.toLowerCase().includes(filter))
        );
      }

      if (!filtered.length) {
        marketList.appendChild(el("div", {
          class: "card-sub",
          style: { padding: "12px 0", opacity: "0.6" },
          text: filter ? "Aucun skill trouvé." : "Catalogue vide.",
        }));
        return;
      }

      filtered.forEach(s => {
        const isInst = s.installed || installed.some(i => i.name === s.name);
        const isRoutine = s.type === "routine";
        const actionBtn = el("button", {
          class: "btn-ghost",
          style: isInst ? { opacity: "0.5", cursor: "default" } : {},
          text: isInst ? "Installé ✓" : "Installer",
          disabled: isInst,
        });
        if (!isInst) {
          actionBtn.onclick = async () => {
            actionBtn.disabled = true;
            actionBtn.textContent = "…";
            try {
              const r = await J.api.post("/api/skills/install/" + encodeURIComponent(s.name), null);
              if (r.success) {
                J.notify({ kind: "success", text: "Skill installé ✓ : " + s.name });
                catalog = catalog.map(c => c.name === s.name ? Object.assign({}, c, { installed: true }) : c);
                const res = await J.api.get("/api/skills/installed");
                installed = (res && res.skills) ? res.skills : [];
                renderInstalled();
                renderMarket(searchInput.value.trim().toLowerCase());
              } else {
                J.notify({ kind: "error", text: r.message || "Erreur installation" });
                actionBtn.disabled = false;
                actionBtn.textContent = "Installer";
              }
            } catch (e) {
              J.notify({ kind: "error", text: "Erreur réseau : " + e.message });
              actionBtn.disabled = false;
              actionBtn.textContent = "Installer";
            }
          };
        }

        const tagsWrap = el("div", { style: { display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "4px" } });
        (s.tags || []).forEach(t => tagsWrap.appendChild(el("span", {
          style: { background: "var(--surface-2,rgba(255,255,255,.06))", borderRadius: "4px", padding: "1px 6px", fontSize: "10px", color: "var(--fg-3)" },
          text: t,
        })));

        const requiresCol = el("div", {});
        if (s.requires_env && s.requires_env.length) {
          requiresCol.appendChild(el("span", {
            class: "skill-requires",
            text: "Env : " + s.requires_env.join(", "),
          }));
        }
        if (s.requires_tools && s.requires_tools.length) {
          requiresCol.appendChild(el("span", {
            class: "skill-requires",
            text: "Outils : " + s.requires_tools.join(", "),
          }));
        }

        const mktInfoCol = el("div", { style: { flex: 1 } });
        mktInfoCol.appendChild(el("span", { style: { color: "var(--fg-0)" }, text: s.name }));
        mktInfoCol.appendChild(el("span", { class: "tn-sub", text: " · " + (s.author || "—") }));
        if (isRoutine) {
          mktInfoCol.appendChild(el("span", {
            class: "badge badge--accent",
            style: { fontSize: "9px", padding: "1px 5px", marginLeft: "5px", verticalAlign: "middle" },
            text: "ROUTINE",
          }));
        }
        mktInfoCol.appendChild(el("span", { class: "tn-sub", text: s.description || "" }));
        if (isRoutine && (s.platforms || []).length) {
          mktInfoCol.appendChild(el("span", { class: "tn-sub", text: "Plateformes : " + s.platforms.join(", ") }));
        }
        if (isRoutine && (s.triggers || []).length) {
          const trigText = s.triggers.slice(0, 2).map(t => `"${t}"`).join(", ");
          mktInfoCol.appendChild(el("span", { class: "tn-sub", text: trigText }));
        }
        mktInfoCol.appendChild(tagsWrap);
        if (requiresCol.children.length) mktInfoCol.appendChild(requiresCol);

        const glyphText = isRoutine ? "▶" : (s.name || "sk").slice(0, 2).toUpperCase();
        marketList.appendChild(el("div", { class: "tool-row", style: { alignItems: "start" } }, [
          el("div", { class: "tg", text: glyphText }),
          mktInfoCol,
          actionBtn,
        ]));
      });
    }

    searchInput.oninput = () => renderMarket(searchInput.value.trim().toLowerCase());
    renderMarket("");

    const refreshBtn = el("button", { class: "btn-ghost", text: "↻ Actualiser" });
    refreshBtn.onclick = async () => {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "…";
      try {
        const catRes = await J.api.get("/api/skills/catalog");
        catalog = (catRes && catRes.skills) ? catRes.skills : [];
        offline  = !!(catRes && catRes.offline);
        onlineBadge.textContent = offline ? "● Hors ligne" : "● En ligne";
        renderMarket(searchInput.value.trim().toLowerCase());
        J.notify({ kind: "info", text: "Catalogue actualisé — " + catalog.length + " skill(s)" });
      } catch (e) {
        J.notify({ kind: "error", text: "Erreur catalogue : " + e.message });
      }
      refreshBtn.disabled = false;
      refreshBtn.textContent = "↻ Actualiser";
    };

    const mktRight = el("div", { style: { display: "flex", gap: "10px", alignItems: "center" } });
    mktRight.appendChild(onlineBadge);
    mktRight.appendChild(refreshBtn);

    root.appendChild(card({
      title: "Marketplace",
      sub:   catalog.length + " skills disponibles",
      right: mktRight,
    }, [filterTabs, searchInput, marketList]));

    /* ─── Section 3 : Outils runtime ────────────────────────── */
    let tools = TOOLS.map(t => Object.assign({}, t));
    try {
      const raw = await J.api.get("/api/tools");
      if (raw && raw.length) {
        tools = raw.map(t => ({
          glyph: t.name ? t.name.slice(0, 3).toLowerCase() : "?",
          name:  t.name || "outil",
          sub:   t.description || "",
          calls: 0,
          lat:   "—",
          on:    true,
        }));
      }
    } catch (_) { /* keep mock */ }

    root.appendChild(secHd("03", "Outils runtime", "Capabilities branchées", tools.filter(t => t.on).length + " actifs"));
    const toolList = el("div");
    const toolState = tools;
    function rerenderTools() {
      toolList.innerHTML = "";
      toolState.forEach((t, i) => {
        toolList.appendChild(el("div", { class: "tool-row" }, [
          el("div", { class: "tg", text: t.glyph }),
          el("div", {}, [
            el("span", { style: { color: "var(--fg-0)" }, text: t.name }),
            el("span", { class: "tn-sub", text: t.sub }),
          ]),
          el("div", { class: "tnum", text: t.calls.toLocaleString() }),
          el("div", { class: "tlat", text: t.lat }),
          el("div", {
            class: "toggle" + (t.on ? " on" : ""),
            style: { justifySelf: "end" },
            onclick: () => {
              toolState[i].on = !toolState[i].on;
              rerenderTools();
              J.notify({ kind: toolState[i].on ? "success" : "info", text: t.name + (toolState[i].on ? " · activé" : " · désactivé") });
            },
          }),
        ]));
      });
    }
    rerenderTools();
    root.appendChild(card({
      title: "Outils",
      sub: toolState.filter(t => t.on).length + " / " + toolState.length + " actifs · runtime",
    }, toolList));
  }

  /* ───────── Conso ───────── */
  async function renderConso(root) {
    // SHAPE EXPECTED: PROVIDERS, CONSO_SERIES (area chart), USAGE_TYPES, HOURLY
    // Backend:
    //   GET /api/conso/session → { total_cost_usd, total_tokens, providers: {name: {cost_usd, tokens}} }
    //   GET /api/conso/daily   → [{ date, cost_usd, tokens }]  (last 7 days)
    //   GET /api/conso/monthly → { month, cost_usd, tokens }
    // Transformation: daily → CONSO_SERIES (single provider "Jarvis"), session → hero totals
    // CONSO_SERIES multi-provider breakdown: TODO no endpoint yet — keeps mock per-provider series
    root.innerHTML = '<div class="surface"><div class="j-loading">Chargement…</div></div>';
    let heroTotal = "$0.00", heroBudget = "$500", heroPct = 0;
    let heroToday = "$0.00", heroTokens = "0M", heroForecast = "$0";
    let consoSeries = CONSO_SERIES;
    let providers = PROVIDERS;
    let usageTypes = USAGE_TYPES;
    try {
      const [sessResult, monthResult, dailyResult] = await Promise.allSettled([
        J.api.get("/api/conso/session"),
        J.api.get("/api/conso/monthly"),
        J.api.get("/api/conso/daily"),
      ]);
      const sess  = sessResult.status  === "fulfilled" ? sessResult.value  : null;
      const month = monthResult.status === "fulfilled" ? monthResult.value : null;
      const daily = dailyResult.status === "fulfilled" ? dailyResult.value : null;

      if (month) {
        heroTotal  = "$" + (month.cost_usd || 0).toFixed(2);
        heroTokens = Math.round((month.tokens || 0) / 1e6 * 10) / 10 + "M";
        // Providers from monthly breakdown (correct field: cost_usd)
        if (month.providers && month.providers.length > 0) {
          providers = month.providers.map(p => ({
            name:  p.name,
            color: { anthropic: "#D97757", elevenlabs: "#A78BFA", openai: "#10A37F", deepgram: "#4A9EFF" }[p.name] || "#6B7280",
            cost:  "$" + (p.cost_usd || 0).toFixed(2),
            tok:   p.tokens > 0 ? Math.round(p.tokens / 1e6 * 10) / 10 + "M"
                 : p.chars  > 0 ? Math.round(p.chars / 1000) + "K c"
                 : "—",
          }));
        }
        if (month.by_type && month.by_type.length > 0) {
          usageTypes = month.by_type.map(t => ({
            name:  t.label,
            sub:   t.sub,
            color: t.color,
            cost:  "$" + (t.cost_usd || 0).toFixed(2),
            pct:   t.pct,
            tok:   Math.round((t.cost_usd || 0) / (month.cost_usd || 1) * (month.tokens || 0) / 1e6 * 10) / 10 + "M",
          }));
        }
        heroPct = Math.min(100, Math.round((month.cost_usd || 0) / 500 * 100));
      }
      if (sess) {
        heroToday = "$" + (sess.total_cost_usd || 0).toFixed(2);
      }
      if (daily && daily.length > 0) {
        // Build single-series area chart from daily data
        const vals = daily.map(d => Number((d.cost_usd || 0).toFixed(2)));
        consoSeries = [{ name: "Jarvis", color: "#4A9EFF", data: vals }];
        // Forecast: linear regression on last 14 days
        const recent = vals.slice(-14);
        if (recent.length > 1) {
          const avg = recent.reduce((a, b) => a + b, 0) / recent.length;
          const daysLeft = 30 - new Date().getDate();
          heroForecast = "$" + (parseFloat(heroTotal.replace("$", "")) + avg * daysLeft).toFixed(0);
        }
      }
    } catch (_) { /* keep mocks */ }

    root.innerHTML = "";
    root.appendChild(secHd("04", "Conso", "Coûts & tokens", heroTotal + " ce mois"));

    // Mini grid
    const mini = el("div", { class: "conso-mini-grid" });
    const heroBox = el("div", { class: "conso-mini", style: { padding: "22px" } }, [
      el("div", { class: "cm-lbl", text: "Total · ce mois" }),
      el("div", { style: { display:"flex", alignItems:"baseline", gap:"14px" } }, [
        el("span", { class: "num-hero", text: heroTotal }),
        el("span", { class: "kpi-delta up", text: "ce mois" }),
      ]),
      el("div", { class: "cm-sub", text: "budget mensuel · " + heroBudget + " · " + heroPct + "% consommé" }),
      el("div", { class: "src-bar", style: { marginTop: "6px" } }, [
        el("div", { style: { width: heroPct + "%", background: "var(--accent)" } }),
      ]),
    ]);
    mini.appendChild(heroBox);

    function miniBox(lbl, val, valStyle, spark, sub, subStyle, inspect) {
      const box = el("div", { class: "conso-mini" }, [
        el("div", { class: "cm-lbl", text: lbl }),
        el("div", { class: "cm-val", style: valStyle || {}, dataset: inspect ? { inspect } : null }, val),
      ]);
      if (spark) box.appendChild(spark);
      if (sub) box.appendChild(el("div", { class: "cm-sub", style: subStyle || {}, text: sub }));
      return box;
    }
    mini.appendChild(miniBox("Aujourd'hui", heroToday, null,
      J.sparkline(consoSeries[0] ? consoSeries[0].data.slice(-7) : [0],{width:140,height:24,color:"var(--accent)"}),
      "session courante", null, "Cumul UTC · reset à 00:00"));
    const tokParts = heroTokens.replace("M","").replace("K","");
    mini.appendChild(miniBox("Tokens · mois",
      [document.createTextNode(tokParts), el("span",{class:"u",text: heroTokens.includes("M") ? "M" : "K"})],
      null,
      J.sparkline(consoSeries[0] ? consoSeries[0].data.slice(-7) : [0],{width:140,height:24,color:"var(--green)"}),
      "input + output · tous providers", null, "Input + output · tous providers"));
    const fbox = miniBox("Forecast fin de mois", heroForecast, { color: "var(--gold)" }, null,
      "extrapolation linéaire", null, "Régression linéaire sur 14j · IC 95%");
    fbox.appendChild(el("div", { class: "cm-sub", style: { color: "var(--gold)" }, text: "● extrapolé" }));
    mini.appendChild(fbox);

    root.appendChild(mini);

    // Evolution chart
    const chartCard = card({}, []);
    chartCard.classList.add("conso-area-card");
    chartCard.appendChild(el("div", { class: "card-hd" }, [
      el("div", {}, [
        el("div", { class: "card-title", text: "Évolution · 30 derniers jours" }),
        el("div", { class: "card-sub", style: { marginTop: "6px" }, text: "stack par provider · USD / jour" }),
      ]),
      el("div", { style: { display: "flex", gap: "6px" } }, [
        el("span", { class: "badge badge--solid", text: "USD" }),
        el("button", { class: "btn-ghost", text: "7j" }),
        el("button", { class: "btn-ghost", style: { color: "var(--fg-0)", background: "rgba(220,232,255,0.06)" }, text: "30j" }),
        el("button", { class: "btn-ghost", text: "90j" }),
      ]),
    ]));
    chartCard.appendChild(Charts.areaStack(consoSeries, { width: 900, height: 220 }));
    const legend = el("div", { class: "conso-legend" });
    consoSeries.forEach(s => {
      const sum = s.data.reduce((a,b) => a+b, 0);
      legend.appendChild(el("span", { class: "lg" }, [
        el("span", { class: "sw", style: { background: s.color } }),
        el("span", { text: s.name }),
        el("span", { class: "v", text: "$" + sum.toFixed(0) }),
      ]));
    });
    chartCard.appendChild(legend);
    root.appendChild(chartCard);

    // Donut + usage
    const grid = el("div", { class: "conso-grid" });
    const usageCard = card({ title: "Répartition par type d'usage", sub: "où part vraiment l'argent" });
    const ut = el("div", { class: "usage-types" });
    usageTypes.forEach(u => {
      ut.appendChild(el("div", { class: "utype" }, [
        el("span", { class: "ut-sw", style: { background: u.color } }),
        el("div", {}, [
          el("div", { class: "ut-name", text: u.name }),
          el("span", { class: "ut-sub", text: u.sub }),
          el("div", { class: "src-bar", style: { marginTop: "8px" } }, [
            el("div", { style: { width: (u.pct*100)+"%", background: u.color, opacity: ".85" } }),
          ]),
        ]),
        el("div", {}, [
          el("div", { class: "ut-num", text: u.cost }),
          el("span", { class: "ut-sub", style: { textAlign: "right", display: "block" }, text: (u.pct*100).toFixed(0) + "% · " + u.tok }),
        ]),
      ]));
    });
    usageCard.appendChild(ut);
    grid.appendChild(usageCard);

    const provCard = card({ title: "Par provider", sub: "part du total" });
    provCard.style.display = "flex"; provCard.style.flexDirection = "column"; provCard.style.gap = "18px";
    const provRow = el("div", { style: { display: "flex", alignItems: "center", gap: "22px" } });
    provRow.appendChild(Charts.donut(providers.map(p => ({ value: parseFloat(p.cost.replace("$","")), color: p.color })), { size: 140, thickness: 20 }));
    const legendBlock = el("div", { style: { display: "flex", flexDirection: "column", gap: "8px", flex: "1", minWidth: "0" } });
    providers.forEach(p => {
      legendBlock.appendChild(el("div", {
        style: { display: "grid", gridTemplateColumns: "12px 1fr auto", gap: "10px", alignItems: "center", fontSize: "12px" },
      }, [
        el("span", { style: { width: "10px", height: "10px", borderRadius: "2px", background: p.color } }),
        el("span", { style: { color: "var(--fg-1)" }, text: p.name }),
        el("span", { class: "t-mono", style: { color: "var(--fg-0)", fontSize: "11.5px" }, text: p.cost }),
      ]));
    });
    provRow.appendChild(legendBlock);
    provCard.appendChild(provRow);

    const heat = el("div", { class: "heat-block" }, [
      el("div", { class: "hb-lbl" }, [
        el("span", { text: "USAGE · 24h · $/heure" }),
        el("span", { style: { color: "var(--fg-1)" }, text: "peak 14:00 · $1.42" }),
      ]),
    ]);
    heat.appendChild(Charts.heatRow(HOURLY, { height: 20 }));
    heat.appendChild(el("div", { class: "hb-lbl" }, [
      el("span", { text: "00:00" }), el("span", { text: "06:00" }), el("span", { text: "12:00" }), el("span", { text: "18:00" }), el("span", { text: "23:59" }),
    ]));
    provCard.appendChild(heat);
    grid.appendChild(provCard);

    root.appendChild(grid);
  }

  /* ───────── Settings (sub-pages) ───────── */
  const SETTINGS_NAV = [
    { id: "keys",       label: "API Keys",    meta: "",  eyebrow: "clefs d'accès",   title: "API Keys" },
    { id: "audio",      label: "Audio & Vidéo", meta: "", eyebrow: "input / output", title: "Audio & Vidéo" },
    { id: "modeles",    label: "Modèles",     meta: "",  eyebrow: "IA & voix",       title: "Modèles" },
    { id: "connectors", label: "Connecteurs", meta: "",  eyebrow: "intégrations",    title: "Connecteurs" },
    { id: "musique",    label: "Musique",     meta: "",  eyebrow: "fournisseur",     title: "Musique" },
    { id: "autonomy",   label: "Autonomie",   meta: "",  eyebrow: "comportement",    title: "Autonomie" },
    { id: "appearance", label: "Apparence",   meta: "",  eyebrow: "interface",       title: "Apparence" },
  ];

  function setRow(title, sub, control, status) {
    return el("div", { class: "set-row" }, [
      el("div", { class: "set-l" }, [
        el("span", { class: "set-l-title", text: title }),
        el("span", { class: "set-l-sub", text: sub }),
      ]),
      control || el("span"),
      status || el("span"),
    ]);
  }

  function comingSoon(c) {
    c.appendChild(el("div", { class: "j-empty", style: { margin: "32px 0" }, text: "À venir — pas encore développé." }));
  }

  function saveSetting(key, value) {
    return fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value: String(value) }),
    }).catch(() => {});
  }

  function renderSettingsKeys(c) {
    const KEY_META = {
      ANTHROPIC_API_KEY:    { name: "Anthropic",        sub: "Claude — LLM principal" },
      OPENAI_API_KEY:       { name: "OpenAI",           sub: "Whisper STT / fallback LLM" },
      ELEVENLABS_API_KEY:   { name: "ElevenLabs",       sub: "TTS — voix de Jarvis" },
      ELEVENLABS_VOICE_ID:  { name: "ElevenLabs Voice ID", sub: "ID de voix par défaut" },
      GOOGLE_API_KEY:       { name: "Google",           sub: "Gemini · Calendar · Drive" },
      LIVEKIT_URL:          { name: "LiveKit URL",      sub: "serveur agent vocal temps réel" },
      LIVEKIT_API_KEY:      { name: "LiveKit API Key",  sub: "auth LiveKit" },
      LIVEKIT_API_SECRET:   { name: "LiveKit Secret",   sub: "auth LiveKit" },
      NOTION_TOKEN:         { name: "Notion",           sub: "intégration workspace" },
      SPOTIFY_CLIENT_ID:    { name: "Spotify Client ID",sub: "OAuth Spotify" },
      DEEPGRAM_API_KEY:     { name: "Deepgram",         sub: "STT alternatif" },
      MISTRAL_API_KEY:      { name: "Mistral",          sub: "LLM alternatif" },
    };
    c.appendChild(el("div", { class: "j-loading", text: "Chargement…" }));
    J.api.get("/api/settings").then(data => {
      c.innerHTML = "";
      const keys = data.api_keys || {};
      Object.keys(KEY_META).forEach(envKey => {
        const meta = KEY_META[envKey];
        const masked = keys[envKey] || "";
        const isSet = masked.length > 0;
        const inp = el("input", {
          class: "input-mono", type: "password",
          value: masked, placeholder: isSet ? "" : "non configuré",
          style: { opacity: isSet ? "1" : "0.4" },
        });
        inp.addEventListener("blur", () => {
          const v = inp.value.trim();
          if (v && !v.includes("•")) saveSetting(envKey, v);
        });
        const showBtn = el("button", { class: "btn-ghost", text: "Afficher" });
        showBtn.addEventListener("click", () => {
          inp.type = inp.type === "password" ? "text" : "password";
          showBtn.textContent = inp.type === "password" ? "Afficher" : "Masquer";
        });
        c.appendChild(setRow(meta.name, meta.sub, inp,
          el("div", { style: { display: "flex", gap: "6px", alignItems: "center" } }, [
            el("span", { class: "t-mono", style: { fontSize: "10px", color: isSet ? "var(--green)" : "var(--fg-3)" }, text: isSet ? "● OK" : "○ vide" }),
            showBtn,
          ])
        ));
      });
    }).catch(() => { c.innerHTML = ""; c.appendChild(el("div", { class: "j-empty", text: "Impossible de charger les clés." })); });
  }

  function renderSettingsAudio(c) {
    // Devices from browser
    function buildDeviceSel(kind, savedKey) {
      const sel = el("select", { class: "select-mono" });
      el("option", { text: "Détection…" });
      if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        navigator.mediaDevices.enumerateDevices().then(devs => {
          sel.innerHTML = "";
          devs.filter(d => d.kind === kind).forEach(d => {
            sel.appendChild(el("option", { value: d.deviceId, text: d.label || d.deviceId.slice(0, 20) }));
          });
          if (!sel.options.length) sel.appendChild(el("option", { text: "Aucun détecté" }));
        }).catch(() => { sel.innerHTML = ""; sel.appendChild(el("option", { text: "Non disponible" })); });
      }
      return sel;
    }

    c.appendChild(setRow("Microphone", "capture par défaut", buildDeviceSel("audioinput"),
      el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "audio input" })));
    c.appendChild(setRow("Sortie audio", "où Jarvis parle", buildDeviceSel("audiooutput"),
      el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "audio output" })));
    c.appendChild(setRow("Caméra", "video input", buildDeviceSel("videoinput"),
      el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "video" })));

    // Wake session (facial control)
    const wakeToggle = el("div", { class: "toggle" });
    fetch("/api/wakeup/status").then(r => r.json()).then(d => {
      if (d.enabled) wakeToggle.classList.add("on");
    }).catch(() => {});
    wakeToggle.addEventListener("click", () => {
      const isOn = wakeToggle.classList.toggle("on");
      saveSetting("WAKEUP_ENABLED", isOn ? "true" : "false");
    });
    c.appendChild(setRow("Séance Wake", "activation + contrôle facial au démarrage", el("span"), wakeToggle));

    // Quebec mode
    const quebecToggle = el("div", { class: "toggle" });
    J.api.get("/api/settings").then(d => {
      if (d.jarvis?.quebec_mode) quebecToggle.classList.add("on");
    }).catch(() => {});
    quebecToggle.addEventListener("click", () => {
      const isOn = quebecToggle.classList.toggle("on");
      saveSetting("QUEBEC_MODE", isOn ? "true" : "false");
    });
    c.appendChild(setRow("Mode Québécois", "accent + dialecte québécois · voix dédiée ElevenLabs", el("span"), quebecToggle));
  }

  function renderSettingsModeles(c) {
    c.appendChild(el("div", { class: "j-loading", text: "Chargement…" }));
    J.api.get("/api/settings").then(data => {
      c.innerHTML = "";
      const llm = data.llm || {};
      const audio = data.audio || {};

      function sel(opts, current, key) {
        const s = el("select", { class: "select-mono" });
        opts.forEach(o => s.appendChild(el("option", { value: o, text: o, selected: o === current ? "" : null })));
        s.addEventListener("change", () => saveSetting(key, s.value));
        return s;
      }

      const ANTHROPIC_MODELS = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"];
      const LLM_PROVIDERS    = ["anthropic", "openai", "gemini"];
      const TTS_PROVIDERS    = ["elevenlabs", "local", "deepgram"];
      const WHISPER_MODELS   = ["tiny", "base", "small", "medium", "large"];

      c.appendChild(setRow("LLM Provider", "moteur de raisonnement principal",
        sel(LLM_PROVIDERS, llm.llm_provider, "LLM_PROVIDER"),
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "LLM_PROVIDER" })));

      c.appendChild(setRow("Modèle Anthropic", "utilisé pour le chat et les missions",
        sel(ANTHROPIC_MODELS, llm.anthropic_model, "ANTHROPIC_MODEL"),
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "ANTHROPIC_MODEL" })));

      c.appendChild(setRow("Modèle vocal", "Claude utilisé dans le pipeline voix",
        sel(ANTHROPIC_MODELS, llm.voice_anthropic_model, "VOICE_ANTHROPIC_MODEL"),
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "VOICE_ANTHROPIC_MODEL" })));

      c.appendChild(setRow("TTS Provider", "moteur de synthèse vocale",
        sel(TTS_PROVIDERS, audio.tts_provider, "TTS_PROVIDER"),
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "TTS_PROVIDER" })));

      const elevInp = el("input", { class: "input-mono", value: audio.elevenlabs_model || "", placeholder: "ex: eleven_turbo_v2_5" });
      elevInp.addEventListener("blur", () => saveSetting("ELEVENLABS_MODEL", elevInp.value.trim()));
      c.appendChild(setRow("ElevenLabs Model", "modèle ElevenLabs utilisé pour la synthèse",
        elevInp,
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "ELEVENLABS_MODEL" })));

      c.appendChild(setRow("Whisper Model", "taille du modèle STT local",
        sel(WHISPER_MODELS, audio.whisper_model, "WHISPER_MODEL"),
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "WHISPER_MODEL" })));

    }).catch(() => { c.innerHTML = ""; c.appendChild(el("div", { class: "j-empty", text: "Impossible de charger les paramètres." })); });
  }

  function renderSettingsMusique(c) {
    const PROVIDERS = [
      { id: "spotify", label: "Spotify",       sub: "Premium · Web Playback SDK" },
      { id: "deezer",  label: "Deezer",         sub: "Premium · OAuth" },
      { id: "local",   label: "Lecture locale", sub: "macOS · nowplaying-cli · toutes applications" },
    ];

    function keyInp(envKey, placeholder, type) {
      const inp = el("input", { class: "input-mono", type: type || "text", placeholder });
      fetch("/api/settings").then(r => r.json()).then(d => {
        const v = (d.api_keys || {})[envKey] || "";
        inp.value = v;
        inp.style.opacity = v ? "1" : "0.4";
      }).catch(() => {});
      inp.addEventListener("blur", () => {
        const v = inp.value.trim();
        if (v && !v.includes("•")) { saveSetting(envKey, v); inp.style.opacity = "1"; }
      });
      return inp;
    }

    function orSep() {
      return el("div", { style: { display: "flex", alignItems: "center", gap: "10px", margin: "6px 16px" } }, [
        el("div", { style: { flex: "1", height: "1px", background: "var(--border)" } }),
        el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)", flexShrink: "0" }, text: "OU" }),
        el("div", { style: { flex: "1", height: "1px", background: "var(--border)" } }),
      ]);
    }

    c.appendChild(el("div", { class: "j-loading", text: "Chargement…" }));

    J.api.get("/api/settings").then(data => {
      c.innerHTML = "";
      const current = (data.music || {}).music_provider || "";

      const sel = el("select", { class: "select-mono" });
      sel.appendChild(el("option", { value: "", text: "— Aucun —", selected: !current ? "" : null }));
      PROVIDERS.forEach(p => sel.appendChild(el("option", { value: p.id, text: p.label, selected: p.id === current ? "" : null })));
      sel.addEventListener("change", () => { saveSetting("MUSIC_PROVIDER", sel.value); renderDetails(); });
      c.appendChild(setRow("Fournisseur de musique", "source affichée dans le widget de la page d'accueil", sel));

      const detailsDiv = el("div", { style: { marginTop: "4px" } });
      c.appendChild(detailsDiv);

      function renderDetails() {
        detailsDiv.innerHTML = "";
        const provId = sel.value;

        if (provId === "spotify") {
          fetch("/api/music/provider-status").then(r => r.json()).then(s => {
            const connected = s.connected;
            const statusEl = el("span", { class: "t-mono", style: { fontSize: "10.5px", color: connected ? "var(--green)" : "var(--fg-3)" }, text: connected ? "● CONNECTÉ" : "○ NON LIÉ" });
            const connectBtn = el("a", { href: "/api/spotify/auth", class: "btn-ghost", text: "Se connecter avec son compte →", style: { fontSize: "12px" } });
            detailsDiv.appendChild(setRow("Spotify", "si abonnement Spotify Premium", connectBtn, statusEl));
            detailsDiv.appendChild(orSep());
            detailsDiv.appendChild(setRow("Spotify Client ID", "depuis developer.spotify.com",
              keyInp("SPOTIFY_CLIENT_ID", "ex: d70b227e6e8d402e…")));
            detailsDiv.appendChild(setRow("Spotify Client Secret", "",
              keyInp("SPOTIFY_CLIENT_SECRET", "ex: bad37c5e5d634206…", "password")));
          }).catch(() => {});

        } else if (provId === "deezer") {
          fetch("/api/music/provider-status").then(r => r.json()).then(s => {
            const connected = s.connected;
            const statusEl = el("span", { class: "t-mono", style: { fontSize: "10.5px", color: connected ? "var(--green)" : "var(--fg-3)" }, text: connected ? "● CONNECTÉ" : "○ NON LIÉ" });
            const connectBtn = el("a", { href: "/api/deezer/auth", class: "btn-ghost", text: "Se connecter avec son compte →", style: { fontSize: "12px" } });
            detailsDiv.appendChild(setRow("Deezer", "si abonnement Deezer Premium", connectBtn, statusEl));
            detailsDiv.appendChild(orSep());
            detailsDiv.appendChild(setRow("Deezer App ID", "depuis developers.deezer.com",
              keyInp("DEEZER_APP_ID", "ex: 123456")));
            detailsDiv.appendChild(setRow("Deezer App Secret", "",
              keyInp("DEEZER_APP_SECRET", "ex: abc123…", "password")));
          }).catch(() => {});

        } else if (provId === "local") {
          fetch("/api/local-music/player").then(r => r.json()).then(d => {
            const ok = d.connected !== false;
            const statusEl = el("span", { class: "t-mono", style: { fontSize: "10.5px", color: ok ? "var(--green)" : "var(--gold)" }, text: ok ? "● DISPONIBLE" : "○ NON TROUVÉ" });
            const hint = ok
              ? el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "lit le Now Playing macOS" })
              : el("code", { text: "brew install nowplaying-cli", style: { fontSize: "11px", color: "var(--fg-3)" } });
            detailsDiv.appendChild(setRow("nowplaying-cli", "contrôle système · toutes applications audio", hint, statusEl));
          }).catch(() => {
            detailsDiv.appendChild(el("div", { class: "set-section-hint", text: "Installer : brew install nowplaying-cli" }));
          });
        }
      }

      renderDetails();
    }).catch(() => { c.innerHTML = ""; c.appendChild(el("div", { class: "j-empty", text: "Erreur de chargement." })); });
  }

  function renderSettingsConnectors(c) {
    c.appendChild(el("div", { class: "j-loading", text: "Chargement…" }));
    J.api.get("/api/settings/connectors").then(conns => {
      c.innerHTML = "";
      const STATUS = {
        on:      { col: "var(--green)", lbl: "CONNECTÉ" },
        expired: { col: "var(--gold)",  lbl: "EXPIRÉ" },
        off:     { col: "var(--fg-3)",  lbl: "NON LIÉ" },
      };
      conns.forEach(conn => {
        const s = STATUS[conn.status] || STATUS.off;
        c.appendChild(setRow(conn.name, conn.sub,
          conn.status === "expired" ? el("span", { class: "t-mono", style: { fontSize: "10px", color: "var(--fg-3)" }, text: "renouveler" }) : el("span"),
          el("span", { class: "t-mono", style: { color: s.col, fontSize: "10.5px" }, text: "● " + s.lbl })
        ));
      });
    }).catch(() => { c.innerHTML = ""; c.appendChild(el("div", { class: "j-empty", text: "Impossible de charger." })); });
  }

  const SETTINGS_RENDERERS = {
    keys: renderSettingsKeys,
    audio: renderSettingsAudio,
    modeles: renderSettingsModeles,
    connectors: renderSettingsConnectors,
    musique: renderSettingsMusique,
    autonomy: comingSoon,
    appearance: comingSoon,
  };

  function renderSettings(root) {
    root.innerHTML = "";
    root.appendChild(secHd("05", "Paramètres", "Configuration", SETTINGS_NAV.length + " sections"));

    let page = window._pendingSettingsSection || "keys";
    window._pendingSettingsSection = null;
    const shell = el("div", { class: "settings-shell" });
    const nav = el("div", { class: "settings-nav" });
    const content = el("div", { class: "settings-content" });

    function rerender() {
      nav.innerHTML = "";
      nav.appendChild(el("div", { class: "sn-eyebrow", text: "configuration" }));
      SETTINGS_NAV.forEach(s => {
        nav.appendChild(el("div", {
          class: "sn-item" + (page === s.id ? " is-on" : ""),
          onclick: () => { page = s.id; rerender(); },
        }, [
          el("span", { text: s.label }),
          el("span", { class: "sn-meta", text: s.meta }),
        ]));
      });

      const cur = SETTINGS_NAV.find(s => s.id === page);
      content.innerHTML = "";
      content.appendChild(el("div", { class: "sc-hd" }, [
        el("div", { class: "sc-hd-l" }, [
          el("span", { class: "sc-hd-eyebrow", text: cur.eyebrow }),
          el("span", { class: "sc-hd-title", text: cur.title }),
        ]),
        el("button", { class: "btn-ghost", text: "Sauvegarder", onclick: () => J.notify({ kind: "success", text: "Paramètres · sauvegardés" }) }),
      ]));
      const inner = el("div", { style: { marginTop: "8px" } });
      SETTINGS_RENDERERS[page](inner);
      content.appendChild(inner);
    }
    rerender();
    shell.appendChild(nav); shell.appendChild(content);
    root.appendChild(shell);
  }

  /* ───────── Système (logs + actions) ───────── */
  function renderSysteme(root) {
    root.innerHTML = "";
    root.appendChild(secHd("06", "Système", "Stream & actions", "live · 14d uptime"));

    const grid = el("div", { class: "sys-grid" });

    // Logs
    const logsCard = card({
      title: "Système", sub: "event stream · live",
      right: el("div", { style: { display: "flex", gap: "6px" } }, [
        el("span", { class: "badge", text: "all" }),
        el("span", { class: "badge badge--accent" }, [el("span",{class:"pri-dot"}), document.createTextNode("info")]),
        el("span", { class: "badge badge--gold", text: "warn" }),
        el("span", { class: "badge badge--red",  text: "err" }),
      ]),
    });
    const logScroll = el("div", { class: "scroll-y", style: { maxHeight: "280px" } });
    function rebuildLogs() {
      logScroll.innerHTML = "";
      const now = new Date();
      LOG_SEED.forEach((l, i) => {
        const t = new Date(now.getTime() - i * 14000);
        const pad = (n) => String(n).padStart(2, "0");
        const tStr = pad(t.getHours()) + ":" + pad(t.getMinutes()) + ":" + pad(t.getSeconds());
        const lm = el("span", { class: "lm" });
        l.parts.forEach(p => {
          if (p.cls) lm.appendChild(el("span", { class: p.cls, text: p.t }));
          else lm.appendChild(document.createTextNode(p.t));
        });
        logScroll.appendChild(el("div", { class: "log-line" }, [
          el("span", { class: "lt", text: tStr }),
          el("span", { class: "lv " + l.lv, text: l.lv }),
          lm,
        ]));
      });
    }
    rebuildLogs();
    // Replace setInterval stub with real WebSocket /ws/logs
    // Format: { lv: "ok"|"info"|"warn"|"err", parts: [{t: string, cls?: "accent"|"dim"}] }
    try {
      const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
      const wsLogs = new WebSocket(wsProto + "//" + location.host + "/ws/logs");
      wsLogs.onmessage = (ev) => {
        try {
          const log = JSON.parse(ev.data);
          LOG_SEED.unshift(log);
          if (LOG_SEED.length > 50) LOG_SEED.pop();
          rebuildLogs();
        } catch (_) {}
      };
      wsLogs.onerror = () => setInterval(rebuildLogs, 2400);  // fallback si WS échoue
    } catch (_) {
      setInterval(rebuildLogs, 2400);
    }
    logsCard.appendChild(logScroll);
    grid.appendChild(logsCard);

    // Actions
    const actionsCard = card({ title: "Actions système", sub: "opérations runtime" });
    const actGrid = el("div", { class: "action-grid" });
    [
      { t: "Recharger config",    s: "soft-reload · 0 downtime", cls: "" },
      { t: "Vider cache",          s: "~ 124 MB · libère mémoire", cls: "" },
      { t: "Reindex mémoire",      s: "~ 9.8 s · vector store",    cls: "" },
      { t: "Restart agents",       s: "interrompt 6 sessions",     cls: "is-warn" },
      { t: "Snapshot complet",     s: "backup · ~ 480 MB",         cls: "is-warn" },
      { t: "Wipe sessions",        s: "destructif · confirm requis", cls: "is-danger" },
    ].forEach(a => {
      actGrid.appendChild(el("div", {
        class: "act " + a.cls,
        onclick: () => {
          const kind = a.cls === "is-danger" ? "error" : a.cls === "is-warn" ? "warn" : "success";
          J.notify({ kind, text: a.t + " · exécuté" });
        },
      }, [
        el("span", { class: "a-title", text: a.t }),
        el("span", { class: "a-sub",   text: a.s }),
      ]));
    });
    actionsCard.appendChild(actGrid);
    grid.appendChild(actionsCard);

    root.appendChild(grid);
  }

  /* ───────── Routing ───────── */
  const SECTIONS = [
    { id: "sessions",  label: "Sessions",    meta: "6"      },
    { id: "memoire",   label: "Mémoire",     meta: "10"     },
    { id: "outils",    label: "Outils",      meta: "skills" },
    { id: "conso",     label: "Conso",       meta: "…"      },
    { id: "settings",  label: "Paramètres",  meta: "6"      },
    { id: "systeme",   label: "Système",     meta: "live"   },
  ];
  const RENDERERS = {
    sessions: renderSessions, memoire: renderMemory, outils: renderTools,
    conso: renderConso, settings: renderSettings, systeme: renderSysteme,
  };
  const state = { active: "sessions" };

  function refreshSidebar() {
    document.querySelectorAll(".sb-item").forEach(b => {
      b.classList.toggle("is-on", b.dataset.id === state.active);
    });
  }
  function mountSidebar() {
    J.mountSidebar({
      activeId: state.active,
      onNav: (id) => { state.active = id; renderActive(); refreshSidebar(); },
      sections: [{ label: "Système", items: SECTIONS }],
      footer: { spend: "$3.42", cpu: "14%", ramPct: 0.65 },
    });
  }
  function renderActive() {
    const root = document.getElementById("page-root");
    root.innerHTML = '<div class="surface"><div class="j-loading">Chargement…</div></div>';
    const surface = el("section", { class: "surface page-in", dataset: { screenLabel: "system-" + state.active } });
    try { RENDERERS[state.active](surface); }
    catch (err) { surface.appendChild(el("div", { class: "j-empty", text: "Erreur : " + err.message })); }
    root.innerHTML = ""; root.appendChild(surface);
  }
  function registerCommands() {
    J.registerCommands([
      { kind: "nav", group: "Aller à", title: "Sessions",   glyph: "01", run: () => { state.active = "sessions";  renderActive(); refreshSidebar(); } },
      { kind: "nav", group: "Aller à", title: "Mémoire",    glyph: "02", run: () => { state.active = "memoire";   renderActive(); refreshSidebar(); } },
      { kind: "nav", group: "Aller à", title: "Outils",     glyph: "03", run: () => { state.active = "outils";    renderActive(); refreshSidebar(); } },
      { kind: "nav", group: "Aller à", title: "Conso",      glyph: "04", run: () => { state.active = "conso";     renderActive(); refreshSidebar(); } },
      { kind: "nav", group: "Aller à", title: "Paramètres", glyph: "05", run: () => { state.active = "settings";  renderActive(); refreshSidebar(); } },
      { kind: "nav", group: "Aller à", title: "Système",    glyph: "06", run: () => { state.active = "systeme";   renderActive(); refreshSidebar(); } },
      { kind: "nav", group: "Pages",   title: "Keypad Studio", glyph: "⌨", sub: "/keypad", run: () => { window.location.href = "/keypad"; } },
      { kind: "nav", group: "Pages",   title: "Dashboard",  glyph: "→",  sub: "control", run: () => { window.handleDashboardClick && window.handleDashboardClick(); } },
      { kind: "slash", group: "Commandes", title: "restart", glyph: ">", sub: "redémarre le runtime", run: () => J.notify({ kind: "warn", text: "Runtime · restart envoyé" }) },
      { kind: "slash", group: "Commandes", title: "logs",    glyph: ">", sub: "saute aux logs",       run: () => { state.active = "systeme"; renderActive(); refreshSidebar(); } },
      { kind: "slash", group: "Commandes", title: "spend",   glyph: ">", sub: "saute à conso",        run: () => { state.active = "conso";   renderActive(); refreshSidebar(); } },
    ]);
  }

  function boot() {
    J.mountAtmosphere();
    mountSidebar();
    J.mountTopbar({ pageTitle: "Système", crumb: "/ system" });
    J.mountBottomNav({ active: "system" });
    registerCommands();
    renderActive();
    // Update conso meta in sidebar with real monthly total
    J.api.get("/api/conso/monthly").then(m => {
      const sec = SECTIONS.find(s => s.id === "conso");
      if (sec && m && m.cost_usd != null) {
        sec.meta = "$" + m.cost_usd.toFixed(0);
        document.querySelectorAll(".sb-item[data-id='conso'] .sb-meta").forEach(el => {
          el.textContent = sec.meta;
        });
      }
    }).catch(() => {});
  }
  window.Settings = { boot };
})();
