// Spaceshark Mission Commander — front-end.
// Round-table council + Nemotron Director + Mission Inbox + Earth-heavy mode.

(() => {
  "use strict";
  const $   = (id) => document.getElementById(id);
  const svgNS = "http://www.w3.org/2000/svg";
  const HEALTH_COLOR = {
    GREEN: "#3df0c8", YELLOW: "#ffd166", RED: "#ff6470", BLACK: "#2a2a2a",
    UNKNOWN: "#4a5663",
  };
  const ATTENTION_OF = {
    GREEN: "STABLE", YELLOW: "ROUTINE", RED: "PRIORITY", BLACK: "EOL-CANDIDATE",
    UNKNOWN: "UNASSESSED",
  };

  const els = {
    clock: $("clock"),
    inferBadge: $("infer-badge"), inferMode: $("infer-mode"), inferSub: $("infer-sub"),
    gpuName: $("gpu-name"), gpuUtil: $("gpu-util"), gpuMem: $("gpu-mem"),
    tokenBar: $("token-bar"), tokenSpent: $("token-spent"), tokenQuota: $("token-quota"),
    fhGreen: $("fh-green"), fhYellow: $("fh-yellow"), fhRed: $("fh-red"), fhBlack: $("fh-black"), fhUnknown: $("fh-unknown"),
    focusName: $("focus-name"), focusAttn: $("focus-attn"),
    layoutToggle: $("layout-toggle"),

    councilButtons: $("council-buttons"), councilDesc: $("council-desc"),

    fleetCount: $("fleet-count"), fleetList: $("fleet-list"), fleetFilters: $("fleet-filters"),
    catalogSize: $("catalog-size"),

    councilBench: $("council-bench"), rtStatus: $("rt-status"), rtTally: $("rt-tally"),

    inboxList: $("inbox-list"), inboxNew: $("inbox-new"), inboxTotal: $("inbox-total"),
    briefPanel: $("brief-panel"), brief: $("brief"), briefClose: $("brief-close"),
    btnAccept: $("btn-accept"), btnDismiss: $("btn-dismiss"),

    stars: $("stars"), continents: $("continents"), graticule: $("graticule"),
    catalogLayer: $("catalog-layer"), satLayer: $("sat-layer"), focusOverlay: $("focus-overlay"),
    earthCount: $("earth-count"),

    telSat: $("tel-sat"),
    telAlt: $("tel-alt"), telVel: $("tel-vel"), telSig: $("tel-sig"),
    telAltVal: $("tel-alt-val"), telVelVal: $("tel-vel-val"), telSigVal: $("tel-sig-val"),

    lineupSub: $("lineup-sub"), lineupTbl: $("lineup-tbl"),
  };

  const STATE = {
    sats: [],
    focused: null,
    inbox: [],
    selectedInbox: null,
    filter: "ALL",
    council_mode: "BALANCED",
    council_modes: {},
    council_seats: [],
    inference: null,
  };

  // ------------------------------------------------------------------ clock
  function tickClock() {
    const d = new Date(); const pad = (n) => String(n).padStart(2, "0");
    els.clock.textContent =
      `${d.toLocaleDateString("en-GB", { weekday: "short" }).toUpperCase()} ` +
      `${pad(d.getDate())} ${d.toLocaleDateString("en-GB", { month: "short" }).toUpperCase()} ` +
      `${d.getFullYear()} | ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
  }
  setInterval(tickClock, 1000); tickClock();

  // ------------------------------------------------------------------ layout toggle
  els.layoutToggle.addEventListener("click", () => {
    const cur = document.body.dataset.layout;
    document.body.dataset.layout = cur === "EARTH" ? "ANALYSIS" : "EARTH";
    els.layoutToggle.textContent =
      document.body.dataset.layout === "EARTH" ? "▣ ANALYSIS MODE" : "⌬ EARTH MODE";
  });

  // ------------------------------------------------------------------ council picker
  els.councilButtons.querySelectorAll(".cb-btn").forEach(b => {
    b.addEventListener("click", async () => {
      const mode = b.dataset.mode;
      await fetch("/api/council-mode", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
    });
  });
  function renderCouncilPicker(inf) {
    if (!inf) return;
    STATE.council_mode = inf.council_mode;
    STATE.council_modes = inf.council_modes || {};
    STATE.council_seats = inf.council_seats || [];
    els.councilButtons.querySelectorAll(".cb-btn").forEach(b =>
      b.classList.toggle("active", b.dataset.mode === inf.council_mode));
    const cm = (inf.council_modes || {})[inf.council_mode];
    els.councilDesc.textContent = cm ? cm.desc : "";
  }

  // ------------------------------------------------------------------ top bar
  function renderTokens(t) {
    const pct = Math.min(100, t.pct || 0);
    els.tokenBar.style.width = pct + "%";
    els.tokenSpent.textContent = (t.spent || 0).toLocaleString();
    els.tokenQuota.textContent = (t.quota || 0).toLocaleString();
  }
  function renderFleetHealth(f) {
    els.fhGreen.textContent  = f.GREEN   || 0;
    els.fhYellow.textContent = f.YELLOW  || 0;
    els.fhRed.textContent    = f.RED     || 0;
    els.fhBlack.textContent  = f.BLACK   || 0;
    if (els.fhUnknown) els.fhUnknown.textContent = f.UNKNOWN || 0;
  }
  function renderInference(inf) {
    if (!inf) return;
    STATE.inference = inf;
    const live = inf.mode === "LIVE-OLLAMA";
    els.inferBadge.classList.toggle("live", live);
    // NEO rename — Nemotron is the protagonist, not Ollama (Ollama is just the
    // runtime that hosts the Nemotron weights on RTX 5070).
    const lineup = inf.lineup || [];
    const alive = lineup.filter(m => m.alive && m.loaded);
    const nemoSeats = lineup.filter(m =>
      (m.vendor === "NVIDIA") || (m.family && m.family.toLowerCase().includes("nemotron"))
    ).length;
    if (live) {
      els.inferMode.textContent = "NEMOTRON · LIVE";
      const dirMs = inf.director_last_ms ? `· dir ${inf.director_last_ms}ms ` : "";
      els.inferSub.textContent =
        `${nemoSeats}/${lineup.length} Nemotron seats · ${inf.live_calls} local calls ${dirMs}· VRAM ${inf.host_gpu ? Math.round(100 * inf.host_gpu.mem_used_mib / inf.host_gpu.mem_total_mib) + "%" : "?"}`;
    } else {
      els.inferMode.textContent = "NEMOTRON · OFFLINE";
      els.inferSub.textContent = `${inf.available_models?.length || 0} models reachable — click to bring Nemotron live`;
    }
    if (inf.host_gpu) {
      els.gpuName.textContent = inf.host_gpu.name.replace("NVIDIA GeForce ", "");
      els.gpuUtil.textContent = inf.host_gpu.util_pct + "%";
      els.gpuMem.textContent  = `${inf.host_gpu.mem_used_mib}/${inf.host_gpu.mem_total_mib} MiB`;
    }
    renderCouncilPicker(inf);
    renderLineup(inf);
  }
  els.inferBadge.addEventListener("click", async () => {
    const prevSub = els.inferSub.textContent;
    els.inferSub.textContent = "probing local Nemotron…";
    try {
      const r = await fetch("/api/probe-ollama", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(r => r.json());
      if (r.ok) {
        els.inferSub.textContent = `Nemotron ${r.model} responded in ${Math.round(r.ms)}ms · ${r.available?.length || 0} models loaded`;
        // Clear any stale error after 8s — the state SSE stream will re-render.
        setTimeout(() => { if (els.inferSub.textContent.startsWith("Nemotron ")) renderInference(STATE.inference); }, 8000);
      } else {
        els.inferSub.textContent = r.reason || "probe failed";
      }
    } catch (err) {
      // Don't leave the stale error sticky — fall back to renderInference after 4s.
      els.inferSub.textContent = "probe error: " + (err?.message || err);
      setTimeout(() => renderInference(STATE.inference), 4000);
    }
  });

  function renderLineup(inf) {
    const active = new Set(inf.active_seats || []);
    const dir = inf.director;
    const all = (inf.primary || []).concat(inf.backup || []);
    const aliveCount = all.filter(m => m.alive && m.loaded && active.has(m.seat)).length;
    const seatCount = (inf.active_seats || []).length;
    els.lineupSub.textContent = `${aliveCount}/${seatCount} seats · DIR ${dir && dir.alive && dir.loaded ? "✓" : "—"}`;
    const fmt = (m) => {
      let state, klass;
      if (!m.loaded)              { state = "not pulled"; klass = "miss"; }
      else if (!m.alive)          { state = "DEAD";       klass = "dead"; }
      else if (m.replaced_by)     { state = "→ "+m.replaced_by; klass = "swapped"; }
      else if (m.seat && !active.has(m.seat)) { state = "BENCHED"; klass = "bench"; }
      else                        { state = m.last_label || "READY"; klass = "alive"; }
      const ms = m.last_call_ms ? ` ${m.last_call_ms}ms` : "";
      const benchedRow = m.seat && !active.has(m.seat) ? "bench" : "";
      return `<tr class="${m.alive ? "" : "dead"} ${benchedRow}">
        <td><span class="ln-dot" style="background:${m.loaded ? (m.alive ? "var(--accent)" : "var(--bad)") : "var(--ink-faint)"}"></span>
            <span class="ln-id">${escapeHtml(m.id)}</span>
            <div class="ln-seat">${escapeHtml(m.seat || "")}</div></td>
        <td class="ln-vendor">${escapeHtml(m.vendor)}${ms}</td>
        <td class="ln-state ${klass}">${escapeHtml(state)}</td>
      </tr>`;
    };
    const rows = [];
    if (dir) {
      rows.push(`<tr class="lineup-section"><td colspan="3">DIRECTOR · Nemotron</td></tr>`);
      const ds = dir.alive && dir.loaded ? "READY" : (dir.loaded ? "DEAD" : "not pulled");
      const dk = dir.alive && dir.loaded ? "alive" : (dir.loaded ? "dead" : "miss");
      const ms = dir.last_call_ms ? ` ${dir.last_call_ms}ms` : "";
      rows.push(`<tr class="director-row">
        <td><span class="ln-dot" style="background:${dir.loaded ? (dir.alive ? "var(--warn)" : "var(--bad)") : "var(--ink-faint)"}"></span>
            <span class="ln-id">${escapeHtml(dir.id)}</span>
            <div class="ln-seat">DIRECTOR</div></td>
        <td class="ln-vendor">${escapeHtml(dir.vendor)}${ms}</td>
        <td class="ln-state ${dk}">${ds}</td>
      </tr>`);
    }
    rows.push(`<tr class="lineup-section"><td colspan="3">SPECIALISTS · ${seatCount} active</td></tr>`);
    (inf.primary || []).forEach(m => rows.push(fmt(m)));
    rows.push(`<tr class="lineup-section"><td colspan="3">BACKUP POOL</td></tr>`);
    (inf.backup || []).forEach(m => rows.push(fmt(m)));
    els.lineupTbl.querySelector("tbody").innerHTML = rows.join("");
  }

  // ------------------------------------------------------------------ fleet list
  els.fleetFilters.querySelectorAll(".ff-btn").forEach(b => {
    b.addEventListener("click", () => {
      els.fleetFilters.querySelectorAll(".ff-btn").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      STATE.filter = b.dataset.filter;
      renderFleet();
    });
  });
  function matchesFilter(s) {
    const f = STATE.filter;
    if (f === "ALL")      return true;
    if (f === "Starlink") return /STRLNK|STARLINK/i.test(s.name);
    if (f === "WARN")     return s.health !== "GREEN";
    return s.regime === f;
  }
  const FLEET_RENDER_CAP = 250;   // keep DOM light at 1000-sat scale
  function renderFleet() {
    const list = STATE.sats.filter(matchesFilter);
    const order = { BLACK: 0, RED: 1, YELLOW: 2, GREEN: 3, UNKNOWN: 4 };
    list.sort((a, b) => (order[a.health] - order[b.health]) || a.name.localeCompare(b.name));
    const shown = list.slice(0, FLEET_RENDER_CAP);
    const truncated = list.length > shown.length;
    els.fleetCount.textContent =
      `${shown.length}${truncated ? " of " + list.length : ""} / ${STATE.sats.length}`;
    els.fleetList.innerHTML = shown.map(s => `
      <li data-id="${s.id}" class="${STATE.focused && STATE.focused.id === s.id ? "focused" : ""}">
        <span class="fl-dot h-${s.health}"></span>
        <div>
          <div class="fl-name">${escapeHtml(s.name)}</div>
          <div class="fl-meta">${s.regime} · ${escapeHtml(s.shell || s.operator)}</div>
        </div>
        <div class="fl-tag">${ATTENTION_OF[s.health] || s.health}</div>
      </li>`).join("") +
      (truncated ? `<li class="fl-more">… ${list.length - shown.length} more, narrow with a filter</li>` : "");
    els.fleetList.querySelectorAll("li[data-id]").forEach(li =>
      li.addEventListener("click", () => focusSat(li.dataset.id))
    );
  }

  function focusSat(id) {
    fetch("/api/focus", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sat: id }),
    });
  }

  // ------------------------------------------------------------------ council bench
  // HTML/flex layout — fits the slim strip cleanly: focused sat card on the
  // left, specialist chips in a row, Director chip on the right.
  function renderRoundTable(focused, brief) {
    if (!focused) { els.councilBench.innerHTML = ""; return; }
    const votes = (brief && brief.votes) ? brief.votes :
                  (focused.assessment ? focused.assessment.votes : []);
    const director = brief ? brief.director : (focused.assessment ? focused.assessment.arbiter : null);
    const activeSeats = (STATE.inference && STATE.inference.active_seats) || ["ORBIT","TRIAGE","EVIDENCE"];
    const n = activeSeats.length;
    const voteBySeat = {};
    votes.forEach(v => { if (v.seat) voteBySeat[v.seat] = v; });

    const attn = ATTENTION_OF[focused.health] || focused.health;
    const subjectCard = `
      <div class="bench-subject">
        <div class="bs-label">SUBJECT</div>
        <div class="bs-name">${escapeHtml(focused.name)}</div>
        <div class="bs-meta">${focused.regime}${focused.shell ? " · " + escapeHtml(focused.shell) : ""}</div>
        <div class="bs-health" style="color:${HEALTH_COLOR[focused.health] || "#fff"}">${attn}</div>
      </div>`;

    const seats = activeSeats.map((seatName) => {
      const v = voteBySeat[seatName];
      const seatTitle = (STATE.council_seats.find(s => s.seat === seatName) || {}).title || seatName;
      const roleLabel = seatTitle.toUpperCase().replace(" ANALYST", "");
      const klass = v ? `vote-${v.label}` : "thinking";
      return `<div class="bench-seat ${klass}">
        <div class="bs-role">${escapeHtml(roleLabel)}</div>
        <div class="bs-vote" style="color:${v ? HEALTH_COLOR[v.label] : "var(--info)"}">${v ? (v.label || "?")[0] : "·"}</div>
        <div class="bs-id">${escapeHtml(v ? (v.model || "—") : "deliberating")}</div>
        <div class="bs-tag">${escapeHtml(v ? (v.vendor || "") : "")}${v && v.ms ? " · " + v.ms + "ms" : ""}</div>
      </div>`;
    }).join("");

    let directorChip = `<div class="bench-director thinking">
        <div class="bs-role">DIRECTOR</div>
        <div class="bs-vote" style="color:var(--ink-faint)">·</div>
        <div class="bs-id">nemotron</div>
        <div class="bs-tag">awaiting</div>
      </div>`;
    if (director) {
      const dis = director.disagreement ? "ESCALATED" : "CONFIRMED";
      directorChip = `<div class="bench-director vote-${director.label}">
        <div class="bs-role">DIRECTOR · ${dis}</div>
        <div class="bs-vote" style="color:${HEALTH_COLOR[director.label]}">${ATTENTION_OF[director.label] || director.label}</div>
        <div class="bs-id">${escapeHtml(director.model || "nemotron")}</div>
        <div class="bs-tag">${director.ms || "?"} ms</div>
      </div>`;
    }

    els.councilBench.innerHTML = subjectCard + seats + directorChip;

    const labels = votes.map(v => v.label).filter(Boolean);
    els.rtStatus.textContent = director ?
      `${labels.length}/${n} specialists · DIRECTOR ${director.disagreement ? "escalated" : "confirmed"} → ${ATTENTION_OF[director.label]}` :
      labels.length ? `${labels.length}/${n} specialists voted` : "council deliberating…";

    renderTally(votes, director);
  }

  function renderTally(votes, director) {
    const counts = { GREEN: 0, YELLOW: 0, RED: 0, BLACK: 0 };
    votes.forEach(v => { if (v.label) counts[v.label] = (counts[v.label] || 0) + 1; });
    const total = Math.max(1, Object.values(counts).reduce((a, b) => a + b, 0));
    const bar = ["GREEN", "YELLOW", "RED", "BLACK"]
      .map(k => `<i class="b-${k}" style="width:${100 * counts[k] / total}%"></i>`).join("");
    const cells = ["GREEN", "YELLOW", "RED", "BLACK"]
      .map(k => `<span style="color:${HEALTH_COLOR[k]}">${ATTENTION_OF[k].slice(0,3)}<b>${counts[k]}</b></span>`).join("");
    els.rtTally.innerHTML = `
      <div class="rt-bar">${bar}</div>
      <div class="rt-counts">${cells}${director ? `<span style="color:var(--warn);margin-left:8px">DIR ${ATTENTION_OF[director.label]}</span>` : ""}</div>`;
  }

  // ------------------------------------------------------------------ mission inbox
  function renderInbox() {
    const inbox = STATE.inbox.slice().reverse();    // newest first
    const newCount = inbox.filter(i => i.state === "NEW").length;
    els.inboxNew.textContent   = newCount;
    els.inboxTotal.textContent = inbox.length;
    els.inboxList.innerHTML = inbox.map(it => `
      <li data-id="${it.inbox_id}" class="attn-${it.attention_level} state-${it.state}">
        <div class="ib-row1">
          <span class="ib-name">${escapeHtml(it.subject)}</span>
          <span class="ib-attn ${it.attention_level}">${it.attention_level}</span>
        </div>
        <div class="ib-state ${it.state}">${it.state}</div>
        <div class="ib-meta">${escapeHtml(it.regime)}${it.shell ? " · "+escapeHtml(it.shell) : ""} · ${escapeHtml(it.ts.replace("T"," ").replace("Z",""))}</div>
        <div class="ib-meta">${it.action}</div>
      </li>`).join("");
    els.inboxList.querySelectorAll("li").forEach(li => {
      li.addEventListener("click", () => openInboxItem(parseInt(li.dataset.id, 10)));
    });
  }
  function openInboxItem(inboxId) {
    const item = STATE.inbox.find(i => i.inbox_id === inboxId);
    if (!item) return;
    STATE.selectedInbox = item;
    // Pull the focused sat to make the round-table reflect this item.
    focusSat(item.sat_id);
    renderBrief(item);
    els.briefPanel.hidden = false;
  }
  els.briefClose.addEventListener("click", () => { els.briefPanel.hidden = true; STATE.selectedInbox = null; });
  els.btnAccept.addEventListener("click",  () => actOnInbox("accept"));
  els.btnDismiss.addEventListener("click", () => actOnInbox("dismiss"));
  async function actOnInbox(op) {
    if (!STATE.selectedInbox) return;
    await fetch(`/api/inbox/${STATE.selectedInbox.inbox_id}/${op}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
  }

  function renderBrief(item) {
    if (!item) { els.brief.innerHTML = ""; return; }
    const labelCls = `h-${item.health}`;
    const actionCls = ({ "ROUTINE REVIEW": "", "HIGH-PRIORITY REVIEW": "red", "REVIEW FOR EOL": "black", "STABLE — no action": "green" })[item.action] || "";
    const director = item.director;
    const counts = item.vote_counts || {};
    els.brief.innerHTML = `
      <div class="brief-section subject">
        <div class="brief-label">SUBJECT</div>
        <div class="brief-body"><b>${escapeHtml(item.subject)}</b> — ${item.regime}${item.shell ? " / " + escapeHtml(item.shell) : ""}</div>
      </div>
      <div class="brief-section">
        <div class="brief-label">ATTENTION LEVEL</div>
        <div class="brief-body"><b class="${labelCls}">${item.attention_level}</b></div>
      </div>
      <div class="brief-section">
        <div class="brief-label">SPECIALIST VOTES</div>
        <div class="brief-body" style="color:var(--ink-faint);font-size:10px">
          ${["GREEN","YELLOW","RED","BLACK"].map(k => `<span style="color:${HEALTH_COLOR[k]};margin-right:6px">${ATTENTION_OF[k].slice(0,3)} ${counts[k] || 0}</span>`).join("")}
        </div>
      </div>
      ${director ? `
      <div class="brief-section director">
        <div class="brief-label">MISSION DIRECTOR — ${director.disagreement ? "ESCALATED" : "CONFIRMED"}</div>
        <div class="brief-body"><b>${escapeHtml(director.model || "")}</b> → <b style="color:${HEALTH_COLOR[director.label]}">${ATTENTION_OF[director.label]}</b> in ${director.ms || "?"} ms</div>
        ${director.rationale ? `<div class="brief-body" style="color:var(--ink-dim);font-style:italic;font-size:10px">${escapeHtml(director.rationale.slice(0, 280))}</div>` : ""}
      </div>` : ""}
      <div class="brief-section action ${actionCls}">
        <div class="brief-label">RECOMMENDED REVIEW</div>
        <div class="brief-body"><b>${escapeHtml(item.action)}</b></div>
      </div>
      <div class="brief-section">
        <div class="brief-label">PROVENANCE</div>
        <div class="brief-kv">
          <div class="k">event_id</div>     <div class="v">${escapeHtml(item.provenance?.event_id || "")}</div>
          <div class="k">evidence_hash</div><div class="v">${escapeHtml((item.provenance?.evidence_hash || "").slice(0, 16))}…</div>
          <div class="k">ts</div>           <div class="v">${escapeHtml(item.provenance?.ts || "")}</div>
        </div>
      </div>`;
  }

  // ------------------------------------------------------------------ earth
  const CENTER = { x: 400, y: 260 }, R = 170;
  function buildStars() {
    const out = [];
    for (let i = 0; i < 200; i++) {
      const x = Math.random() * 800, y = Math.random() * 520;
      const dx = x - CENTER.x, dy = y - CENTER.y;
      if (dx * dx + dy * dy < (R + 30) * (R + 30)) continue;
      const r = Math.random() < 0.85 ? 0.5 : (Math.random() < 0.6 ? 0.9 : 1.4);
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="white" fill-opacity="${(0.25 + Math.random() * 0.65).toFixed(2)}"/>`);
    }
    els.stars.innerHTML = out.join("");
  }
  function buildGraticule() {
    const lines = [];
    for (let i = 1; i <= 4; i++) {
      const ry = R * Math.cos((i * Math.PI) / 10);
      lines.push(`<ellipse cx="${CENTER.x}" cy="${CENTER.y}" rx="${R}" ry="${ry}"/>`);
    }
    lines.push(`<line x1="${CENTER.x - R}" y1="${CENTER.y}" x2="${CENTER.x + R}" y2="${CENTER.y}"/>`);
    for (let i = 0; i < 8; i++) {
      const rx = R * Math.abs(Math.cos((i * Math.PI) / 8));
      lines.push(`<ellipse cx="${CENTER.x}" cy="${CENTER.y}" rx="${rx}" ry="${R}"/>`);
    }
    els.graticule.innerHTML = lines.join("");
  }
  function buildContinents() {
    const cx = CENTER.x, cy = CENTER.y;
    const paths = [
      `M${cx-12},${cy-30} q22,-6 30,18 t-8,52 q-14,18 -32,8 t-10,-50 q-2,-24 20,-28z`,
      `M${cx-72},${cy-90} q40,-12 90,4 t60,-10 q22,12 8,32 t-90,16 q-50,-2 -68,-22 z`,
      `M${cx-148},${cy-60} q-12,30 4,60 t8,80 q-18,4 -22,-30 t-16,-60 q-2,-46 26,-50z`,
      `M${cx+60},${cy+30} q24,-2 38,18 t-10,28 q-22,8 -36,-6 t-30,-22 q4,-22 38,-18z`,
    ];
    els.continents.innerHTML = paths.map(d => `<path d="${d}"/>`).join("");
  }
  // ------------------------------------------------------------------
  // 3D orbit projection — proper ECI → screen so sats spread across the
  // globe by inclination + RAAN + phase. View is from +Y axis, tilted 25°
  // up so we see Earth slightly from the equator and orbits read as 3D.
  // ------------------------------------------------------------------
  const REGIME_R  = { LEO: 195, SSO: 215, MEO: 290, GEO: 370 };
  const REGIME_SPD = { LEO: 0.14, SSO: 0.10, MEO: 0.04, GEO: 0.014 };
  const VIEW_TILT = 25 * Math.PI / 180;
  const COS_TILT = Math.cos(VIEW_TILT);
  const SIN_TILT = Math.sin(VIEW_TILT);
  const DEG = Math.PI / 180;

  function projectOrbit(sat, t = 0, animate = true) {
    const i = (sat.inclination_deg || 0) * DEG;
    const raan = (sat.raan_deg || 0) * DEG;
    const speed = animate ? (REGIME_SPD[sat.regime] || 0.1) : 0;
    const phi = ((sat.phase || 0) + t * speed) * 2 * Math.PI;
    const cosO = Math.cos(raan), sinO = Math.sin(raan);
    const cosI = Math.cos(i),    sinI = Math.sin(i);
    const cosP = Math.cos(phi),  sinP = Math.sin(phi);
    // ECI unit-sphere position for the sat's orbit plane
    const ex = cosO * cosP - sinO * sinP * cosI;
    const ey = sinO * cosP + cosO * sinP * cosI;
    const ez = sinP * sinI;
    // View from +Y, tilted up by VIEW_TILT:
    //   screen x = ex
    //   screen y = -ez * cos(tilt) + ey * sin(tilt)
    //   depth   =  ey * cos(tilt) + ez * sin(tilt)   (front if positive)
    const sx = ex;
    const sy = -ez * COS_TILT + ey * SIN_TILT;
    const depth = ey * COS_TILT + ez * SIN_TILT;
    const r = REGIME_R[sat.regime] || 200;
    return {
      x: CENTER.x + sx * r,
      y: CENTER.y + sy * r,
      behind: depth < -0.25,   // approximate Earth occlusion
      depth: depth,
    };
  }

  // (No background visual catalog — operator wants only real sats.)

  // Active triage — animated, health-coloured. This is the ONLY thing
  // rendered on the globe; every dot here is a sat the council is
  // actually assessing in round-robin.
  const satEls = {};
  function buildSats(satList) {
    els.satLayer.innerHTML = "";
    Object.keys(satEls).forEach(k => delete satEls[k]);
    satList.forEach((s) => {
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("r", s.regime === "GEO" ? 4 : s.regime === "MEO" ? 3.6 : 3.2);
      c.setAttribute("class", `sat h-${s.health}`);
      c.dataset.id = s.id;
      c.addEventListener("click", () => focusSat(s.id));
      els.satLayer.appendChild(c);
      satEls[s.id] = { dot: c, def: s };
    });
    if (els.earthCount)  els.earthCount.textContent  = satList.length.toLocaleString();
    if (els.catalogSize) els.catalogSize.textContent = satList.length.toLocaleString();
    // Re-apply at-risk band colors to the freshly-built dots
    if (typeof applyRiskBandsToGlobe === "function") applyRiskBandsToGlobe();
  }
  function animateGlobe() {
    const t = performance.now() / 1000;
    for (const id in satEls) {
      const o = satEls[id];
      const p = projectOrbit(o.def, t, true);
      o.dot.setAttribute("cx", p.x);
      o.dot.setAttribute("cy", p.y);
      o.dot.setAttribute("fill-opacity", p.behind ? "0.45" : "1");
    }
    if (STATE.focused) {
      const o = satEls[STATE.focused.id];
      if (o) {
        const p = projectOrbit(o.def, t, true);
        // Trace: 24 samples around the orbit, projected, becomes a polyline
        const pts = [];
        for (let k = 0; k <= 48; k++) {
          const sampSat = { ...o.def, phase: k / 48 };
          const sp = projectOrbit(sampSat, 0, false);
          pts.push(`${sp.x.toFixed(1)},${sp.y.toFixed(1)}`);
        }
        // Focus ring color = composite risk band if available, else LLM health
        const focusBand = SAT_RISK_BAND[STATE.focused.id];
        const focusCol = (focusBand && BAND_COLORS[focusBand]) || HEALTH_COLOR[STATE.focused.health] || "#fff";
        els.focusOverlay.innerHTML =
          `<polyline class="focus-track" points="${pts.join(" ")}" style="stroke:${focusCol}"/>` +
          `<circle class="sat focused" cx="${p.x}" cy="${p.y}" r="6" style="fill:${focusCol};stroke:${focusCol}"/>`;
      }
    }
    requestAnimationFrame(animateGlobe);
  }
  requestAnimationFrame(animateGlobe);
  buildStars(); buildGraticule(); buildContinents();

  // (Catalog fetch removed — globe shows only the assessed fleet.)

  // ------------------------------------------------------------------ telemetry
  function renderTelemetry(f) {
    if (!f || !f.telemetry) return;
    els.telSat.textContent = `${f.name} LIVE`;
    drawSpark(els.telAlt, f.telemetry.alt);
    drawSpark(els.telVel, f.telemetry.vel);
    drawSpark(els.telSig, f.telemetry.sig);
    const last = (a) => a.length ? a[a.length - 1] : "--";
    els.telAltVal.textContent = last(f.telemetry.alt);
    els.telVelVal.textContent = last(f.telemetry.vel);
    els.telSigVal.textContent = last(f.telemetry.sig);
  }
  function drawSpark(el, data) {
    if (!data || !data.length) return;
    const W = 300, H = 50;
    const min = Math.min(...data), max = Math.max(...data);
    const span = Math.max(0.001, max - min);
    const pts = data.map((v, i) =>
      `${(i / (data.length - 1) * W).toFixed(1)},${(H - 4 - ((v - min) / span) * (H - 8)).toFixed(1)}`
    ).join(" ");
    el.setAttribute("points", pts);
  }

  // ------------------------------------------------------------------ apply state
  function applySnapshot(s) {
    STATE.sats = s.sats || [];
    STATE.focused = s.focused;
    STATE.inbox = s.inbox || [];
    if (s.fleet_health) renderFleetHealth(s.fleet_health);
    if (s.tokens) renderTokens(s.tokens);
    if (s.inference) renderInference(s.inference);
    buildSats(STATE.sats);
    renderFleet();
    renderInbox();
    if (STATE.focused) {
      els.focusName.textContent = STATE.focused.name;
      els.focusAttn.textContent = ATTENTION_OF[STATE.focused.health] || STATE.focused.health;
      els.focusAttn.style.color = HEALTH_COLOR[STATE.focused.health];
      renderRoundTable(STATE.focused, null);
      renderTelemetry(STATE.focused);
    }
  }
  function applyFleetUpdate(m) {
    if (m.fleet_health) renderFleetHealth(m.fleet_health);
    if (m.tokens) renderTokens(m.tokens);
    if (m.inference) renderInference(m.inference);
    STATE.sats = m.sats || STATE.sats;
    STATE.focused = m.focused || STATE.focused;
    STATE.sats.forEach(s => {
      const o = satEls[s.id];
      if (o) { o.dot.setAttribute("class", `sat h-${s.health}`); o.def = s; }
    });
    renderFleet();
    if (STATE.focused) {
      els.focusName.textContent = STATE.focused.name;
      els.focusAttn.textContent = ATTENTION_OF[STATE.focused.health] || STATE.focused.health;
      els.focusAttn.style.color = HEALTH_COLOR[STATE.focused.health];
      renderTelemetry(STATE.focused);
      const b = m.brief;
      if (b && b.subject_id === STATE.focused.id) {
        renderRoundTable(STATE.focused, b);
      } else {
        renderRoundTable(STATE.focused, null);
      }
    }
  }
  function applyInbox(m) {
    if (!m.item) return;
    const idx = STATE.inbox.findIndex(i => i.inbox_id === m.item.inbox_id);
    if (idx === -1) STATE.inbox.push(m.item);
    else STATE.inbox[idx] = m.item;
    renderInbox();
    if (STATE.selectedInbox && STATE.selectedInbox.inbox_id === m.item.inbox_id) {
      STATE.selectedInbox = m.item;
      renderBrief(m.item);
    }
  }

  function connect() {
    const es = new EventSource("/api/stream");
    es.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case "snapshot":     applySnapshot(m); break;
        case "fleet_update": applyFleetUpdate(m); break;
        case "focus_change": STATE.focused = m.focused;
                             els.rtStatus.textContent = "council deliberating…";
                             applyFleetUpdate({ focused: m.focused }); break;
        case "tokens":       renderTokens(m.tokens); break;
        case "inference":    renderInference(m.inference); break;
        case "inbox":        applyInbox(m); break;
      }
    };
    es.onerror = () => { es.close(); setTimeout(connect, 1500); };
  }

  // ---------------------------------------------------------------- NEO panels
  // Real Nemotron-generated tactical brief — refreshed every 60s by the
  // server-side neo_tactical_brief_loop. The dashboard polls every 10s.
  async function refreshNeoBrief() {
    try {
      const r = await fetch("/api/neo/tactical-brief").then(r => r.json());
      const textEl = document.getElementById("neo-brief-text");
      const provEl = document.getElementById("neo-brief-prov");
      const ageEl  = document.getElementById("neo-brief-age");
      if (!textEl) return;
      textEl.textContent = r.text || "(no brief)";
      provEl.textContent = `model: ${r.model_id || "?"} · ${r.latency_ms || 0} ms · ${r.eval_count || 0} tokens · src=${r.source || "?"}`;
      ageEl.textContent = `ttl ${r.ttl_remaining_s ?? 0}s`;
      ageEl.style.color = r.source === "llm" ? "#34d399" : (r.source === "llm-failed" ? "#f87171" : "#64748b");
    } catch (e) { /* server may not be up yet */ }
  }

  // Test status badge — pytest pass/fail count refreshed every 5 min by the server.
  async function refreshNeoTestStatus() {
    try {
      const r = await fetch("/api/neo/test-status").then(r => r.json());
      const badge = document.getElementById("neo-test-badge");
      if (!badge) return;
      if (r.ok) {
        badge.textContent = `TESTS ${r.passed} ✓`;
        badge.style.color = "#34d399";
      } else if (r.total > 0) {
        badge.textContent = `TESTS ${r.passed}✓ / ${r.failed + r.errors}✗`;
        badge.style.color = "#f87171";
      } else {
        badge.textContent = "TESTS —";
        badge.style.color = "#94a3b8";
      }
      badge.title = `${r.summary} (${r.duration_s}s)`;
    } catch (e) { /* ignore */ }
  }

  refreshNeoBrief(); setInterval(refreshNeoBrief, 10_000);
  refreshNeoTestStatus(); setInterval(refreshNeoTestStatus, 30_000);

  // ---------------------------------------------------------------- NEO workspaces
  // Tabs: World View / Operations / Fleet (Analysis) / Developer.
  const NEO_VIEWS = {
    worldview:  $("neo-worldview-view"),
    operations: $("neo-operations-view"),
    analysis:   $("neo-analysis-view"),
    developer:  $("neo-developer-view"),
  };
  function setNeoView(name) {
    Object.entries(NEO_VIEWS).forEach(([k, el]) => {
      if (el) el.style.display = (k === name) ? "" : "none";
    });
    document.querySelectorAll(".neo-tab").forEach(btn => {
      const active = btn.dataset.view === name;
      btn.style.color = active ? "#7dd3fc" : "#64748b";
      btn.style.borderBottom = active ? "2px solid #38bdf8" : "2px solid transparent";
      btn.classList.toggle("neo-tab-active", active);
    });
    if (name === "worldview")  refreshNeoWorldView();
    if (name === "operations") refreshNeoCharts();
    if (name === "developer")  refreshNeoDevView();
    if (name === "analysis")   refreshFleetRiskSummary();
  }
  document.querySelectorAll(".neo-tab").forEach(btn =>
    btn.addEventListener("click", () => setNeoView(btn.dataset.view))
  );
  // Default tab — start on World View (answers the three operator questions
  // directly: at-risk sats / space weather / where needs Starlink)
  setNeoView("worldview");

  // ---------------------------------------------------------------- WORLD VIEW renderer
  const BAND_COLORS = {
    GREEN: "#3df0c8", YELLOW: "#ffd166", RED: "#ff6470", BLACK: "#475569",
  };

  // ---------------------------------------------------------------- Composite risk → globe colors
  // The at-risk endpoint scores every sat by a composite risk formula. When
  // we have the full ranking, paint each globe dot with its band color so
  // operators see the danger map directly instead of just the LLM-label colors.
  const SAT_RISK_BAND = {};  // sat_id -> band string

  async function refreshSatRiskBands() {
    try {
      const r = await fetch("/api/neo/at-risk?n=999").then(r => r.json());
      // Wipe previous map; rebuild
      for (const k of Object.keys(SAT_RISK_BAND)) delete SAT_RISK_BAND[k];
      for (const s of (r.top || [])) {
        SAT_RISK_BAND[s.sat_id] = s.band;
      }
      // Apply to existing globe dots immediately
      applyRiskBandsToGlobe();
    } catch (e) { /* server may not be ready */ }
  }

  function applyRiskBandsToGlobe() {
    if (!satEls) return;
    for (const id in satEls) {
      const dot = satEls[id]?.dot;
      if (!dot) continue;
      const band = SAT_RISK_BAND[id];
      if (band && BAND_COLORS[band]) {
        dot.style.fill = BAND_COLORS[band];
        dot.style.stroke = BAND_COLORS[band];
        // Bigger radius for RED/BLACK so they stand out
        if (band === "RED" || band === "BLACK") {
          dot.setAttribute("r", "4.6");
        } else if (band === "YELLOW") {
          dot.setAttribute("r", "3.6");
        }
      } else {
        // No risk data yet — leave defaults
        dot.style.fill = "";
        dot.style.stroke = "";
      }
    }
  }

  // Refresh every 15s — composite risk shifts when SWPC/COTS state changes.
  refreshSatRiskBands(); setInterval(refreshSatRiskBands, 15_000);

  async function refreshNeoWorldView() {
    // 1) At-Risk Queue
    try {
      const r = await fetch("/api/neo/at-risk?n=20").then(r => r.json());
      const summary = r.summary || {bands: {}, total: 0};
      const sumEl = document.getElementById("neo-risk-summary");
      if (sumEl) sumEl.textContent = `${r.top?.length || 0} shown / ${summary.total || 0} sats`;
      const bandsEl = document.getElementById("neo-risk-bands");
      if (bandsEl) {
        bandsEl.innerHTML = "";
        for (const band of ["BLACK", "RED", "YELLOW", "GREEN"]) {
          const n = summary.bands?.[band] || 0;
          if (n === 0 && band !== "RED") continue;
          const pill = document.createElement("div");
          pill.style.cssText = `padding:3px 8px;border-radius:3px;background:${BAND_COLORS[band]}20;color:${BAND_COLORS[band]};border:1px solid ${BAND_COLORS[band]}55`;
          pill.innerHTML = `<b>${band}</b> ${n}`;
          bandsEl.appendChild(pill);
        }
      }
      const listEl = document.getElementById("neo-risk-list");
      if (listEl) {
        listEl.innerHTML = "";
        for (const sat of (r.top || [])) {
          const row = document.createElement("div");
          const col = BAND_COLORS[sat.band] || "#cbd5e1";
          const driverPills = (sat.drivers || []).filter(d => d.name !== "NOMINAL").slice(0, 4).map(d =>
            `<span style="display:inline-block;padding:1px 5px;margin:1px;border-radius:2px;background:${col}15;color:${col};font-size:9px">${d.name}</span>`
          ).join("");
          row.style.cssText = `padding:6px 8px;background:#020a14;border-left:3px solid ${col};border-radius:0 3px 3px 0;font-size:10px;cursor:pointer`;
          row.innerHTML =
            `<div style="display:flex;justify-content:space-between"><b style="color:${col}">${sat.band}</b><span>${sat.total_score.toFixed(1)}</span></div>
             <div style="color:#cbd5e1;margin:2px 0"><b>${sat.sat_name}</b> · ${sat.regime} · health=${sat.health_label}</div>
             <div style="color:#94a3b8;font-size:9px">${sat.summary}</div>
             <div>${driverPills}</div>`;
          row.addEventListener("click", () => {
            fetch("/api/focus", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({sat: sat.sat_id})});
          });
          listEl.appendChild(row);
        }
      }
    } catch (e) { /* ignore */ }

    // 2) Space Weather Forecast
    try {
      const r = await fetch("/api/neo/space-weather-forecast").then(r => r.json());
      const f = r.forecast || {};
      const issuedEl = document.getElementById("neo-wx-issued");
      if (issuedEl) issuedEl.textContent = f.issued_at ? `issued ${f.issued_at}` : "(no forecast yet)";
      const ratEl = document.getElementById("neo-wx-rationale");
      if (ratEl) ratEl.textContent = f.rationale || "(no rationale in this product)";
      const tblEl = document.getElementById("neo-wx-kp-table");
      if (tblEl) {
        const rows = f.geomagnetic_kp_table || [];
        if (rows.length === 0) {
          tblEl.innerHTML = `<div style="color:#475569;padding:4px 0">(NOAA Kp table parse skipped — see rationale above for the 3-day text summary)</div>`;
        } else {
          let html = `<div style="display:grid;grid-template-columns:80px 1fr 1fr 1fr;gap:4px;color:#64748b;border-bottom:1px solid #1e3a52;padding-bottom:2px">
            <div>UT slot</div><div>D+1</div><div>D+2</div><div>D+3</div></div>`;
          for (const row of rows) {
            const max = Math.max(row.day1, row.day2, row.day3);
            const cls = (v) => v >= 5 ? "#ff6470" : v >= 4 ? "#ffd166" : "#3df0c8";
            html += `<div style="display:grid;grid-template-columns:80px 1fr 1fr 1fr;gap:4px;padding:2px 0">
              <div style="color:#94a3b8">${row.slot}</div>
              <div style="color:${cls(row.day1)}">${row.day1.toFixed(2)}</div>
              <div style="color:${cls(row.day2)}">${row.day2.toFixed(2)}</div>
              <div style="color:${cls(row.day3)}">${row.day3.toFixed(2)}</div>
            </div>`;
          }
          tblEl.innerHTML = html;
        }
      }
      const alertsEl = document.getElementById("neo-wx-alerts");
      if (alertsEl) {
        const alerts = r.alerts || [];
        alertsEl.innerHTML = alerts.slice(0, 10).map(a =>
          `<div style="padding:4px 6px;background:#020a14;border-left:2px solid #fbbf24;margin:2px 0;border-radius:0 3px 3px 0">
             <div style="color:#fbbf24;font-weight:600">[${a.product_id || "?"}] ${(a.headline || "").slice(0, 96)}</div>
             <div style="color:#64748b;font-size:9px">${a.issue_datetime || ""}</div>
           </div>`
        ).join("") || `<div style="color:#475569;padding:4px 0">(no active alerts)</div>`;
      }
    } catch (e) { /* ignore */ }

    // 3) Where Needs Starlink — disaster map + list
    try {
      const r = await fetch("/api/neo/where-needs-starlink").then(r => r.json());
      const events = r.events || [];
      const countEl = document.getElementById("neo-disaster-count");
      if (countEl) countEl.textContent = `${events.length} events`;
      drawDisasterMap("neo-disaster-map", events);
      const listEl = document.getElementById("neo-disaster-list");
      if (listEl) {
        listEl.innerHTML = events.slice(0, 30).map(ev => {
          const sevCol = ev.severity_score >= 70 ? "#ff6470" : ev.severity_score >= 50 ? "#ffd166" : "#3df0c8";
          return `<div style="padding:4px 6px;background:#020a14;border-left:2px solid ${sevCol};border-radius:0 3px 3px 0">
            <div style="color:${sevCol};font-weight:600">${ev.source} · ${ev.headline}</div>
            <div style="color:#64748b;font-size:9px">(${ev.lat.toFixed(2)}, ${ev.lon.toFixed(2)}) · sev=${ev.severity_score.toFixed(0)} · ${ev.iso_time || ""}</div>
          </div>`;
        }).join("") || `<div style="color:#475569;padding:4px 0">(no active disasters in feed)</div>`;
      }
    } catch (e) { /* ignore */ }
  }

  // Mini equirectangular world map showing disaster markers
  function drawDisasterMap(svgId, events) {
    const svg = document.getElementById(svgId);
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const W = 360, H = 180;

    // Coarse continent outlines (rough rectangles) — better than nothing as a backdrop
    const continents = [
      [-170, 5, -55, 70],   // North America
      [-90, -55, -35, 12],  // South America
      [-15, 35, 50, 70],    // Europe
      [-20, -35, 50, 35],   // Africa
      [25, 5, 145, 70],     // Asia
      [110, -45, 155, -10], // Australia
    ];
    for (const [lon1, lat1, lon2, lat2] of continents) {
      const x1 = (lon1 + 180) * (W / 360);
      const y1 = (90 - lat2) * (H / 180);
      const x2 = (lon2 + 180) * (W / 360);
      const y2 = (90 - lat1) * (H / 180);
      const r = document.createElementNS(svgNS, "rect");
      r.setAttribute("x", x1); r.setAttribute("y", y1);
      r.setAttribute("width", Math.max(1, x2 - x1)); r.setAttribute("height", Math.max(1, y2 - y1));
      r.setAttribute("fill", "#0a2436"); r.setAttribute("stroke", "#1e3a52"); r.setAttribute("stroke-width", "0.3");
      svg.appendChild(r);
    }

    // Lat/lon grid lines (every 30°)
    for (let lon = -180; lon <= 180; lon += 60) {
      const x = (lon + 180) * (W / 360);
      const ln = document.createElementNS(svgNS, "line");
      ln.setAttribute("x1", x); ln.setAttribute("x2", x);
      ln.setAttribute("y1", 0); ln.setAttribute("y2", H);
      ln.setAttribute("stroke", "#102030"); ln.setAttribute("stroke-width", "0.3");
      svg.appendChild(ln);
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const y = (90 - lat) * (H / 180);
      const ln = document.createElementNS(svgNS, "line");
      ln.setAttribute("x1", 0); ln.setAttribute("x2", W);
      ln.setAttribute("y1", y); ln.setAttribute("y2", y);
      ln.setAttribute("stroke", "#102030"); ln.setAttribute("stroke-width", "0.3");
      svg.appendChild(ln);
    }

    // Equator line
    const eq = document.createElementNS(svgNS, "line");
    eq.setAttribute("x1", 0); eq.setAttribute("x2", W);
    eq.setAttribute("y1", H/2); eq.setAttribute("y2", H/2);
    eq.setAttribute("stroke", "#1e3a52"); eq.setAttribute("stroke-width", "0.6");
    svg.appendChild(eq);

    // Plot events
    for (const ev of events) {
      const x = (ev.lon + 180) * (W / 360);
      const y = (90 - ev.lat) * (H / 180);
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("cx", x); c.setAttribute("cy", y);
      c.setAttribute("r", Math.max(1.5, Math.min(6, ev.severity_score / 12)));
      const col = ev.severity_score >= 70 ? "#ff6470" :
                  ev.severity_score >= 50 ? "#ffd166" : "#3df0c8";
      c.setAttribute("fill", col); c.setAttribute("fill-opacity", "0.65");
      c.setAttribute("stroke", col); c.setAttribute("stroke-width", "0.6");
      const tt = document.createElementNS(svgNS, "title");
      tt.textContent = `${ev.headline} (sev=${ev.severity_score.toFixed(0)})`;
      c.appendChild(tt);
      svg.appendChild(c);
    }
  }
  setInterval(() => {
    if (document.getElementById("neo-worldview-view")?.style.display !== "none") refreshNeoWorldView();
  }, 30_000);

  // Fleet (Analysis) tab — replaces council with a fleet-risk summary.
  async function refreshFleetRiskSummary() {
    try {
      const r = await fetch("/api/neo/at-risk?n=3").then(r => r.json());
      const summary = r.summary || {bands: {}, total: 0};
      const bar = document.getElementById("fleet-risk-band-bar");
      if (bar) {
        bar.innerHTML = "";
        const total = summary.total || 1;
        for (const band of ["BLACK", "RED", "YELLOW", "GREEN"]) {
          const n = summary.bands?.[band] || 0;
          const col = BAND_COLORS[band] || "#cbd5e1";
          const pct = (100 * n / total).toFixed(0);
          const cell = document.createElement("div");
          cell.style.cssText = `flex:1;padding:8px;background:${col}15;border:1px solid ${col}55;border-radius:4px`;
          cell.innerHTML = `<div style="color:${col};font-size:10px;letter-spacing:0.12em;font-weight:600">${band}</div>
            <div style="color:${col};font-size:22px;font-weight:700">${n}</div>
            <div style="color:#64748b;font-size:10px">${pct}% of ${total}</div>`;
          bar.appendChild(cell);
        }
      }
      const top3 = document.getElementById("fleet-risk-top3");
      if (top3) {
        const rows = (r.top || []).slice(0, 3);
        top3.innerHTML = rows.length === 0 ? "" :
          `<div style="color:#7dd3fc;font-size:10px;letter-spacing:0.12em;margin-bottom:6px">TOP 3 AT-RISK</div>` +
          rows.map(s => {
            const col = BAND_COLORS[s.band] || "#cbd5e1";
            return `<div style="padding:4px 8px;background:#020a14;border-left:2px solid ${col};margin:2px 0;border-radius:0 3px 3px 0">
              <span style="color:${col};font-weight:600">${s.band}</span> · <b>${s.sat_name}</b> · score ${s.total_score.toFixed(1)} · ${s.summary}
            </div>`;
          }).join("");
      }
    } catch (e) { /* ignore */ }
  }
  setInterval(() => {
    if (document.getElementById("neo-analysis-view")?.style.display !== "none") refreshFleetRiskSummary();
  }, 30_000);

  // ---------------------------------------------------------------- $0 cloud badge
  async function refreshCloudBadge() {
    try {
      const r = await fetch("/api/state").then(r => r.json());
      const calls = (r.inference || {}).live_calls || 0;
      $("neo-cloud-calls").textContent = calls;
      $("neo-cloud-nim").textContent = "0"; // we never call NIM cloud yet
    } catch (e) { /* ignore */ }
  }
  refreshCloudBadge(); setInterval(refreshCloudBadge, 5_000);

  // ---------------------------------------------------------------- SVG sparkline renderer
  // Minimal, no external lib. Draws a polyline + optional area-fill + axis.
  function drawSparkline(svgId, samples, opts = {}) {
    const svg = document.getElementById(svgId);
    if (!svg) return;
    const vbox = svg.getAttribute("viewBox").split(/\s+/).map(Number);
    const W = vbox[2], H = vbox[3];
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (!samples || samples.length === 0) {
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", W/2); t.setAttribute("y", H/2);
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("fill", "#475569");
      t.setAttribute("font-size", "11");
      t.textContent = "(no samples yet — wait 60s)";
      svg.appendChild(t);
      return;
    }
    const stroke = opts.stroke || "#38bdf8";
    const fill = opts.fill || "rgba(56,189,248,0.16)";
    const log = opts.log === true;
    const minY = opts.minY;
    const maxY = opts.maxY;

    const xs = samples.map((_, i) => i);
    let ys = samples.map(s => Number(s.v) || 0);
    if (log) ys = ys.map(v => Math.log10(Math.max(v, 1e-12)));

    const minX = 0, maxX = Math.max(1, xs.length - 1);
    const ymin = (minY !== undefined) ? minY : Math.min(...ys);
    const ymax = (maxY !== undefined) ? maxY : Math.max(...ys);
    const yrange = (ymax - ymin) || 1;

    const padL = 4, padR = 4, padT = 4, padB = 12;
    const sx = (x) => padL + (x - minX) / (maxX - minX || 1) * (W - padL - padR);
    const sy = (y) => padT + (1 - (y - ymin) / yrange) * (H - padT - padB);

    // axis baseline
    const baseline = document.createElementNS(svgNS, "line");
    baseline.setAttribute("x1", padL); baseline.setAttribute("x2", W - padR);
    baseline.setAttribute("y1", H - padB); baseline.setAttribute("y2", H - padB);
    baseline.setAttribute("stroke", "#1e3a52"); baseline.setAttribute("stroke-width", "0.5");
    svg.appendChild(baseline);

    // area
    if (fill !== "none") {
      const area = document.createElementNS(svgNS, "path");
      let d = `M ${sx(0)} ${H - padB} `;
      ys.forEach((y, i) => { d += `L ${sx(i)} ${sy(y)} `; });
      d += `L ${sx(ys.length - 1)} ${H - padB} Z`;
      area.setAttribute("d", d); area.setAttribute("fill", fill);
      svg.appendChild(area);
    }

    // polyline
    const line = document.createElementNS(svgNS, "polyline");
    line.setAttribute("points", ys.map((y, i) => `${sx(i)},${sy(y)}`).join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", stroke);
    line.setAttribute("stroke-width", "1.4");
    line.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(line);

    // last-value marker
    const lastX = sx(ys.length - 1), lastY = sy(ys[ys.length - 1]);
    const dot = document.createElementNS(svgNS, "circle");
    dot.setAttribute("cx", lastX); dot.setAttribute("cy", lastY);
    dot.setAttribute("r", "2.5"); dot.setAttribute("fill", stroke);
    svg.appendChild(dot);

    // value label
    const t = document.createElementNS(svgNS, "text");
    t.setAttribute("x", lastX - 4); t.setAttribute("y", Math.max(10, lastY - 4));
    t.setAttribute("text-anchor", "end");
    t.setAttribute("fill", stroke);
    t.setAttribute("font-size", "10");
    t.setAttribute("font-family", "ui-monospace,monospace");
    const v = samples[samples.length - 1].v;
    t.textContent = log ? v.toExponential(2) : v.toFixed(2);
    svg.appendChild(t);
  }

  function drawStackedFleet(svgId, byColor) {
    const svg = document.getElementById(svgId);
    if (!svg) return;
    const vbox = svg.getAttribute("viewBox").split(/\s+/).map(Number);
    const W = vbox[2], H = vbox[3];
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const colors = ["fleet_green","fleet_yellow","fleet_red","fleet_black","fleet_unknown"];
    const palette = {
      fleet_green: "#3df0c8", fleet_yellow: "#ffd166", fleet_red: "#ff6470",
      fleet_black: "#475569", fleet_unknown: "#1e293b",
    };
    const N = Math.max(...colors.map(c => (byColor[c] || []).length));
    if (N === 0) {
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", W/2); t.setAttribute("y", H/2);
      t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "#475569");
      t.setAttribute("font-size", "11");
      t.textContent = "(no samples yet — wait 60s)";
      svg.appendChild(t);
      return;
    }
    const padL = 4, padR = 4, padT = 4, padB = 14;
    const xs = (i) => padL + (i / Math.max(1, N - 1)) * (W - padL - padR);
    // Compute per-tick totals to normalise
    const totals = [];
    for (let i = 0; i < N; i++) {
      let t = 0;
      for (const c of colors) t += ((byColor[c] || [])[i] || {v: 0}).v;
      totals.push(t || 1);
    }
    let yTop = new Array(N).fill(0);
    colors.forEach(color => {
      const series = byColor[color] || [];
      const path = document.createElementNS(svgNS, "path");
      let dTop = "";
      let dBot = "";
      for (let i = 0; i < N; i++) {
        const v = (series[i] || {v: 0}).v;
        const yPrev = yTop[i];
        const yCur  = yPrev + v;
        const yPrevPx = padT + (1 - yPrev / totals[i]) * (H - padT - padB);
        const yCurPx  = padT + (1 - yCur  / totals[i]) * (H - padT - padB);
        dTop += (i === 0 ? "M" : " L") + ` ${xs(i)} ${yCurPx}`;
        dBot = `L ${xs(i)} ${yPrevPx} ` + dBot;
        yTop[i] = yCur;
      }
      path.setAttribute("d", dTop + " " + dBot + " Z");
      path.setAttribute("fill", palette[color]);
      path.setAttribute("fill-opacity", "0.75");
      svg.appendChild(path);
    });
    // legend
    let lx = padL + 6;
    [["GREEN","#3df0c8"],["YELLOW","#ffd166"],["RED","#ff6470"],["BLACK","#475569"],["UNKNOWN","#1e293b"]].forEach(([lbl, col]) => {
      const r = document.createElementNS(svgNS, "rect");
      r.setAttribute("x", lx); r.setAttribute("y", H - 10);
      r.setAttribute("width", 8); r.setAttribute("height", 6);
      r.setAttribute("fill", col); svg.appendChild(r);
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", lx + 12); t.setAttribute("y", H - 4);
      t.setAttribute("fill", "#64748b"); t.setAttribute("font-size", "9");
      t.setAttribute("font-family", "ui-monospace,monospace");
      t.textContent = lbl;
      svg.appendChild(t);
      lx += lbl.length * 6 + 30;
    });
  }

  async function fetchMetric(name) {
    try {
      const r = await fetch(`/api/neo/timeseries?metric=${name}`).then(r => r.json());
      return r.samples || [];
    } catch (e) { return []; }
  }

  async function refreshNeoCharts() {
    const [kp, xray, sep, llmRate, vram, auditRate, cots] = await Promise.all([
      fetchMetric("swpc_kp"), fetchMetric("swpc_xray"), fetchMetric("swpc_sep"),
      fetchMetric("llm_calls_per_min"), fetchMetric("gpu_vram_pct"),
      fetchMetric("audit_actions_per_min"), fetchMetric("cots_anomaly_count"),
    ]);
    const [fg, fy, fr, fb, fu] = await Promise.all([
      fetchMetric("fleet_green"), fetchMetric("fleet_yellow"),
      fetchMetric("fleet_red"), fetchMetric("fleet_black"), fetchMetric("fleet_unknown"),
    ]);
    drawSparkline("neo-chart-kp", kp, { stroke: "#7dd3fc", fill: "rgba(125,211,252,0.18)", minY: 0, maxY: 9 });
    drawSparkline("neo-chart-xray", xray, { stroke: "#fbbf24", fill: "rgba(251,191,36,0.18)", log: true });
    drawSparkline("neo-chart-sep", sep, { stroke: "#f87171", fill: "rgba(248,113,113,0.18)", minY: 0 });
    drawSparkline("neo-chart-llm-rate", llmRate, { stroke: "#34d399", fill: "rgba(52,211,153,0.18)", minY: 0 });
    drawSparkline("neo-chart-vram", vram, { stroke: "#a78bfa", fill: "rgba(167,139,250,0.18)", minY: 0, maxY: 100 });
    drawSparkline("neo-chart-audit-rate", auditRate, { stroke: "#fb923c", fill: "rgba(251,146,60,0.18)", minY: 0 });
    drawSparkline("neo-chart-cots", cots, { stroke: "#f59e0b", fill: "rgba(245,158,11,0.18)", minY: 0 });
    drawStackedFleet("neo-chart-fleet", { fleet_green: fg, fleet_yellow: fy, fleet_red: fr, fleet_black: fb, fleet_unknown: fu });
    // Meta labels
    const last = (a) => a.length ? a[a.length - 1].v : null;
    function setText(id, v, unit = "") {
      const el = document.getElementById(id);
      if (el && v !== null) el.textContent = `${v.toFixed(2)} ${unit}`;
    }
    setText("neo-kp-meta",    last(kp), "Kp");
    if (last(xray) !== null) document.getElementById("neo-xray-meta").textContent = last(xray).toExponential(2) + " W/m²";
    setText("neo-sep-meta",   last(sep), "pfu");
    setText("neo-llm-meta",   last(llmRate), "calls/min");
    setText("neo-vram-meta",  last(vram), "%");
    setText("neo-audit-meta", last(auditRate), "/min");
    setText("neo-cots-meta",  last(cots), "anomalous");
    const fleet = (last(fg) || 0) + (last(fy) || 0) + (last(fr) || 0) + (last(fb) || 0) + (last(fu) || 0);
    const fleetEl = document.getElementById("neo-fleet-meta");
    if (fleetEl) fleetEl.textContent = `${fleet} sats`;
  }
  setInterval(refreshNeoCharts, 10_000);

  // ---------------------------------------------------------------- Developer tab refresh
  async function refreshNeoDevView() {
    try {
      const prov = await fetch("/api/neo/provenance").then(r => r.json());
      const provEl = $("neo-dev-provenance");
      if (provEl) provEl.textContent = JSON.stringify(prov, null, 2);
    } catch (e) { /* ignore */ }
    try {
      const tests = await fetch("/api/neo/test-status").then(r => r.json());
      const testEl = $("neo-dev-tests");
      if (testEl) testEl.textContent =
        `summary:      ${tests.summary}\n` +
        `passed:       ${tests.passed}\n` +
        `failed:       ${tests.failed}\n` +
        `errors:       ${tests.errors}\n` +
        `duration_s:   ${tests.duration_s}\n` +
        `last_run_ts:  ${new Date(tests.last_run_ts * 1000).toISOString()}\n`;
    } catch (e) { /* ignore */ }
    try {
      const rows = await fetch("/api/audit/last20").then(r => r.json());
      const auditEl = $("neo-dev-audit");
      if (auditEl) auditEl.textContent = rows.map(r =>
        `${r.ts || "?"}  ${r.severity || "INFO"}  ${(r.who || "").slice(0,28).padEnd(28)}  ${r.action || ""}  ${(r.msg || "").slice(0, 100)}`
      ).join("\n") || "(no audit rows yet)";
    } catch (e) { /* ignore */ }
    try {
      const audit = await fetch("/api/neo/storage-audit").then(r => r.json());
      const stEl = $("neo-dev-storage");
      if (stEl) {
        let s = `TOTAL: ${audit.total_human} across ${audit.sections.length} categories\n\n`;
        for (const sec of audit.sections) {
          s += `[${sec.size_human.padStart(10)}]  ${sec.category}\n`;
          s += `              path: ${sec.path}\n`;
          s += `              ${sec.rotation}\n`;
          if (sec.models && sec.models.length) {
            for (const m of sec.models) {
              s += `                  ${m.size.padStart(8)}  ${m.name}\n`;
            }
          }
          s += "\n";
        }
        s += "─── CLEANUP RECOMMENDATIONS ───\n";
        for (const rec of (audit.recommendations || [])) {
          s += `\n  [${rec.severity}] ${rec.action}  (save ${rec.estimated_saving_human})\n`;
          s += `  → ${rec.reason}\n`;
          if (rec.command_wsl) s += `  wsl$ ${rec.command_wsl}\n`;
          if (rec.command_bash) s += `  bash$ ${rec.command_bash}\n`;
        }
        stEl.textContent = s;
      }
    } catch (e) { /* ignore */ }
    try {
      const w = await fetch("/api/neo/wiki/stats").then(r => r.json());
      const wEl = $("neo-dev-wiki");
      if (wEl && !wEl.dataset.searched) {
        wEl.textContent =
          `index built:    ${new Date(w.built_at * 1000).toISOString()}\n` +
          `build duration: ${w.build_ms} ms\n` +
          `pages indexed:  ${w.n_docs}\n` +
          `unique terms:   ${w.unique_terms}\n` +
          `wiki root:      ${w.wiki_root}\n\n` +
          `Type a query above to retrieve. Examples:\n` +
          `  - "SEE latch-up current spike COTS"\n` +
          `  - "Polkadot JAM coretime"\n` +
          `  - "NemoClaw policy guardrail audit log"\n` +
          `  - "solar flare X-ray radiation LEO"\n`;
      }
    } catch (e) { /* ignore */ }
  }

  // Wiki RAG search box
  document.addEventListener("click", async (ev) => {
    if (ev.target?.id !== "neo-wiki-search-btn") return;
    const q = document.getElementById("neo-wiki-query")?.value?.trim();
    if (!q) return;
    const wEl = document.getElementById("neo-dev-wiki");
    if (!wEl) return;
    wEl.dataset.searched = "1";
    wEl.textContent = `retrieving "${q}"…`;
    try {
      const r = await fetch(`/api/neo/wiki/retrieve?q=${encodeURIComponent(q)}&k=5`).then(r => r.json());
      let s = `query: "${r.query}"  ·  ${r.hits?.length || 0} hits\n\n`;
      for (const h of (r.hits || [])) {
        s += `[score ${h.score.toFixed(2)}]  ${h.path}\n  title:   ${h.title}\n  snippet: ${h.snippet}\n\n`;
      }
      wEl.textContent = s || "(no hits)";
    } catch (e) { wEl.textContent = "search error: " + (e?.message || e); }
  });
  document.addEventListener("keypress", (ev) => {
    if (ev.target?.id === "neo-wiki-query" && ev.key === "Enter") {
      document.getElementById("neo-wiki-search-btn")?.click();
    }
  });
  setInterval(() => {
    if (document.getElementById("neo-developer-view")?.style.display !== "none") refreshNeoDevView();
  }, 5_000);

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  connect();
})();
