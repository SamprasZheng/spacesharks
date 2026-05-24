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
    fhGreen: $("fh-green"), fhYellow: $("fh-yellow"), fhRed: $("fh-red"), fhBlack: $("fh-black"),
    focusName: $("focus-name"), focusAttn: $("focus-attn"),
    layoutToggle: $("layout-toggle"),

    councilButtons: $("council-buttons"), councilDesc: $("council-desc"),

    fleetCount: $("fleet-count"), fleetList: $("fleet-list"), fleetFilters: $("fleet-filters"),
    catalogSize: $("catalog-size"),

    rtSvg: $("roundtable"), rtStatus: $("rt-status"), rtTally: $("rt-tally"),

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
    els.fhGreen.textContent  = f.GREEN  || 0;
    els.fhYellow.textContent = f.YELLOW || 0;
    els.fhRed.textContent    = f.RED    || 0;
    els.fhBlack.textContent  = f.BLACK  || 0;
  }
  function renderInference(inf) {
    if (!inf) return;
    STATE.inference = inf;
    const live = inf.mode === "LIVE-OLLAMA";
    els.inferBadge.classList.toggle("live", live);
    els.inferMode.textContent = inf.mode;
    const lineup = inf.lineup || [];
    const alive = lineup.filter(m => m.alive && m.loaded);
    if (live) {
      const dirMs = inf.director_last_ms ? `· dir ${inf.director_last_ms}ms ` : "";
      els.inferSub.textContent =
        `${alive.length}/${lineup.length} seats · ${inf.live_calls} calls ${dirMs}· VRAM ${inf.host_gpu ? Math.round(100 * inf.host_gpu.mem_used_mib / inf.host_gpu.mem_total_mib) + "%" : "?"}`;
    } else {
      els.inferSub.textContent = `${inf.available_models?.length || 0} models reachable — click to go LIVE`;
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
    els.inferSub.textContent = "probing Ollama…";
    try {
      const r = await fetch("/api/probe-ollama", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(r => r.json());
      if (!r.ok) els.inferSub.textContent = r.reason || "probe failed";
    } catch (err) { els.inferSub.textContent = "probe error: " + err; }
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
  function renderFleet() {
    const list = STATE.sats.filter(matchesFilter);
    const order = { BLACK: 0, RED: 1, YELLOW: 2, GREEN: 3, UNKNOWN: 4 };
    list.sort((a, b) => (order[a.health] - order[b.health]) || a.name.localeCompare(b.name));
    els.fleetCount.textContent = `${list.length} / ${STATE.sats.length}`;
    els.fleetList.innerHTML = list.map(s => `
      <li data-id="${s.id}" class="${STATE.focused && STATE.focused.id === s.id ? "focused" : ""}">
        <span class="fl-dot h-${s.health}"></span>
        <div>
          <div class="fl-name">${escapeHtml(s.name)}</div>
          <div class="fl-meta">${s.regime} · ${escapeHtml(s.shell || s.operator)}</div>
        </div>
        <div class="fl-tag">${ATTENTION_OF[s.health] || s.health}</div>
      </li>`).join("");
    els.fleetList.querySelectorAll("li").forEach(li =>
      li.addEventListener("click", () => focusSat(li.dataset.id))
    );
  }

  function focusSat(id) {
    fetch("/api/focus", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sat: id }),
    });
  }

  // ------------------------------------------------------------------ round-table
  const RT_CX = 240, RT_CY = 195, RT_RADIUS = 130;
  const DIR_POS = { x: RT_CX, y: 38 };
  function seatPositions(n) {
    return Array.from({ length: n }, (_, i) => {
      const a = -Math.PI / 2 + i * (2 * Math.PI / n);
      return { x: RT_CX + Math.cos(a) * RT_RADIUS, y: RT_CY + Math.sin(a) * RT_RADIUS };
    });
  }

  function renderRoundTable(focused, brief) {
    if (!focused) { els.rtSvg.innerHTML = ""; return; }
    const votes = (brief && brief.votes) ? brief.votes :
                  (focused.assessment ? focused.assessment.votes : []);
    const director = brief ? brief.director : (focused.assessment ? focused.assessment.arbiter : null);
    const activeSeats = (STATE.inference && STATE.inference.active_seats) || ["ORBIT","TRIAGE","EVIDENCE"];
    const n = activeSeats.length;
    const positions = seatPositions(n);

    // central sat-card
    const attn = ATTENTION_OF[focused.health] || focused.health;
    const center = `
      <g class="rt-center">
        <rect x="${RT_CX - 75}" y="${RT_CY - 36}" width="150" height="72" rx="4"/>
        <text class="ct-name"   x="${RT_CX}" y="${RT_CY - 16}" text-anchor="middle">${escapeHtml(focused.name)}</text>
        <text class="ct-meta"   x="${RT_CX}" y="${RT_CY - 2}"  text-anchor="middle">${focused.regime}${focused.shell ? " · " + escapeHtml(focused.shell) : ""}</text>
        <text class="ct-health" x="${RT_CX}" y="${RT_CY + 22}" text-anchor="middle"
              style="fill:${HEALTH_COLOR[focused.health] || "#fff"}">${attn}</text>
      </g>`;

    // edges
    const edges = positions.map((p) => {
      return `<line class="rt-edge active" x1="${p.x}" y1="${p.y}" x2="${RT_CX}" y2="${RT_CY - 4}"/>`;
    }).join("");

    // seats — map seat name → vote
    const voteBySeat = {};
    votes.forEach(v => { if (v.seat) voteBySeat[v.seat] = v; });
    const seats = positions.map((p, i) => {
      const seatName = activeSeats[i];
      const seatTitle = (STATE.council_seats.find(s => s.seat === seatName) || {}).title || seatName;
      const v = voteBySeat[seatName];
      const klass = v ? `vote-${v.label}` : "thinking";
      const id    = v ? (v.model || "—") : "deliberating…";
      const tag   = v ? (v.vendor || v.family || "") : "";
      const vote  = v ? (v.label || "?")[0] : "·";
      const ms    = (v && v.ms) ? `${v.ms} ms` : "";
      const labelAbove = p.y < RT_CY;
      const roleY = labelAbove ? p.y - 42 : p.y + 32;
      const idY   = labelAbove ? p.y - 30 : p.y + 44;
      const tagY  = labelAbove ? p.y - 20 : p.y + 54;
      const msY   = labelAbove ? p.y - 11 : p.y + 63;
      return `<g class="rt-seat ${klass}">
        <circle cx="${p.x}" cy="${p.y}" r="18"/>
        <text class="seat-vote" x="${p.x}" y="${p.y + 6}" text-anchor="middle"
              style="fill:${v ? HEALTH_COLOR[v.label] : "var(--info)"}">${vote}</text>
        <text class="seat-role" x="${p.x}" y="${roleY}" text-anchor="middle">${escapeHtml(seatTitle.toUpperCase())}</text>
        <text class="seat-id"   x="${p.x}" y="${idY}"   text-anchor="middle">${escapeHtml(id)}</text>
        <text class="seat-tag"  x="${p.x}" y="${tagY}"  text-anchor="middle">${escapeHtml(tag)}</text>
        <text class="seat-ms"   x="${p.x}" y="${msY}"   text-anchor="middle">${ms}</text>
      </g>`;
    }).join("");

    // Mission Director (always shown if assessment ran)
    let directorChip = "";
    if (director) {
      const dis = director.disagreement ? "ESCALATED" : "CONFIRMED";
      directorChip = `
        <g class="rt-director">
          <line class="rt-director-line" x1="${RT_CX}" y1="${DIR_POS.y + 22}" x2="${RT_CX}" y2="${RT_CY - 38}"/>
          <rect x="${DIR_POS.x - 100}" y="${DIR_POS.y - 18}" width="200" height="44" rx="3"/>
          <text class="ab-label" x="${DIR_POS.x}" y="${DIR_POS.y - 4}"  text-anchor="middle">MISSION DIRECTOR · ${dis}</text>
          <text class="ab-vote"  x="${DIR_POS.x - 60}" y="${DIR_POS.y + 16}" text-anchor="middle"
                style="fill:${HEALTH_COLOR[director.label]}">${ATTENTION_OF[director.label] || director.label}</text>
          <text class="ab-id"    x="${DIR_POS.x + 40}" y="${DIR_POS.y + 16}" text-anchor="middle">${escapeHtml(director.model || "nemotron")} · ${director.ms || "?"}ms</text>
        </g>`;
    }

    els.rtSvg.innerHTML = directorChip + edges + seats + center;

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
  const REGIME_RX  = { LEO: 195, SSO: 215, MEO: 290, GEO: 370 };
  const REGIME_RY  = { LEO: 60,  SSO: 95,  MEO: 135, GEO: 195 };
  const REGIME_SPD = { LEO: 0.14, SSO: 0.10, MEO: 0.04, GEO: 0.014 };

  // Background visual catalog (5k unassessed objects, static dots)
  function buildCatalog(catalog) {
    const parts = [];
    catalog.forEach((s, i) => {
      const phase = ((parseInt(s.id, 10) || i) % 360) / 360;
      const a = phase * Math.PI * 2;
      const x = (CENTER.x + Math.cos(a) * (REGIME_RX[s.regime] || 200)).toFixed(1);
      const y = (CENTER.y + Math.sin(a) * (REGIME_RY[s.regime] || 60) * 0.55).toFixed(1);
      parts.push(`<circle class="sat-bg" cx="${x}" cy="${y}" r="0.8"/>`);
    });
    els.catalogLayer.innerHTML = parts.join("");
    if (els.earthCount) els.earthCount.textContent = catalog.length.toLocaleString();
    if (els.catalogSize) els.catalogSize.textContent = catalog.length.toLocaleString();
  }

  // Active triage sats (animated, health-coloured)
  const satEls = {};
  function buildSats(satList) {
    els.satLayer.innerHTML = "";
    Object.keys(satEls).forEach(k => delete satEls[k]);
    const groups = {};
    satList.forEach(s => { (groups[s.regime] = groups[s.regime] || []).push(s); });
    for (const regime in groups) {
      const arr = groups[regime];
      arr.forEach((s, i) => {
        const phase = i / arr.length;
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("r", regime === "GEO" ? 3.6 : regime === "MEO" ? 3.2 : 2.6);
        c.setAttribute("class", `sat h-${s.health}`);
        c.dataset.id = s.id;
        c.addEventListener("click", () => focusSat(s.id));
        els.satLayer.appendChild(c);
        satEls[s.id] = { dot: c, def: s, phase };
      });
    }
  }
  function satPos(o, t) {
    const speed = REGIME_SPD[o.def.regime] || 0.1;
    const ang = (o.phase + t * speed) * Math.PI * 2;
    return {
      x: CENTER.x + Math.cos(ang) * REGIME_RX[o.def.regime],
      y: CENTER.y + Math.sin(ang) * REGIME_RY[o.def.regime] * 0.55,
    };
  }
  function animateGlobe() {
    const t = performance.now() / 1000;
    for (const id in satEls) {
      const o = satEls[id]; const p = satPos(o, t);
      o.dot.setAttribute("cx", p.x); o.dot.setAttribute("cy", p.y);
      const back = Math.sin((o.phase + t * REGIME_SPD[o.def.regime]) * Math.PI * 2) > 0;
      o.dot.setAttribute("fill-opacity", back ? "0.55" : "1");
    }
    if (STATE.focused) {
      const o = satEls[STATE.focused.id];
      if (o) {
        const p = satPos(o, t);
        els.focusOverlay.innerHTML =
          `<ellipse class="focus-track" cx="${CENTER.x}" cy="${CENTER.y}" ` +
          `rx="${REGIME_RX[STATE.focused.regime]}" ry="${(REGIME_RY[STATE.focused.regime] * 0.55).toFixed(1)}"/>` +
          `<circle class="sat focused h-${STATE.focused.health}" cx="${p.x}" cy="${p.y}" r="6"/>`;
      }
    }
    requestAnimationFrame(animateGlobe);
  }
  requestAnimationFrame(animateGlobe);
  buildStars(); buildGraticule(); buildContinents();

  // pull catalog once
  fetch("/api/catalog").then(r => r.json()).then(d => {
    if (d.catalog) buildCatalog(d.catalog);
  }).catch(() => {});

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

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  connect();
})();
