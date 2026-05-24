// Spaceshark Mission Commander — front-end.
// Pentagonal round-table for the 5 AI advisors + structured mission-brief.

(() => {
  "use strict";
  const $   = (id) => document.getElementById(id);
  const svgNS = "http://www.w3.org/2000/svg";
  const HEALTH_COLOR = { GREEN: "#3df0c8", YELLOW: "#ffd166", RED: "#ff6470", BLACK: "#2a2a2a" };

  const els = {
    clock: $("clock"),
    inferBadge: $("infer-badge"), inferMode: $("infer-mode"), inferSub: $("infer-sub"),
    gpuName: $("gpu-name"), gpuUtil: $("gpu-util"), gpuMem: $("gpu-mem"),
    tokenBar: $("token-bar"), tokenSpent: $("token-spent"),
    tokenQuota: $("token-quota"), tokenPct: $("token-pct"), tokenRate: $("token-rate"),
    fhGreen: $("fh-green"), fhYellow: $("fh-yellow"), fhRed: $("fh-red"), fhBlack: $("fh-black"),
    focusName: $("focus-name"), focusHealth: $("focus-health"),

    fleetCount: $("fleet-count"), fleetList: $("fleet-list"), fleetFilters: $("fleet-filters"),

    rtSvg: $("roundtable"), rtStatus: $("rt-status"), rtTally: $("rt-tally"),

    brief: $("brief"), briefTs: $("brief-ts"),
    btnApprove: $("btn-approve"), btnReview: $("btn-review"),

    stars: $("stars"), continents: $("continents"), graticule: $("graticule"),
    satLayer: $("sat-layer"), focusOverlay: $("focus-overlay"),

    telSat: $("tel-sat"),
    telAlt: $("tel-alt"), telVel: $("tel-vel"), telSig: $("tel-sig"),
    telAltVal: $("tel-alt-val"), telVelVal: $("tel-vel-val"), telSigVal: $("tel-sig-val"),
    lifecycle: $("lifecycle"),

    lineupSub: $("lineup-sub"), lineupTbl: $("lineup-tbl"),
  };

  const STATE = {
    sats: [],
    focused: null,
    brief: null,
    filter: "ALL",
  };

  // ------------------------------------------------------------------ clock
  function tickClock() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    els.clock.textContent =
      `${d.toLocaleDateString("en-GB", { weekday: "short" }).toUpperCase()} ` +
      `${pad(d.getDate())} ${d.toLocaleDateString("en-GB", { month: "short" }).toUpperCase()} ` +
      `${d.getFullYear()} | ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
  }
  setInterval(tickClock, 1000); tickClock();

  // ------------------------------------------------------------------ top bar
  function renderTokens(t) {
    const pct = Math.min(100, t.pct || 0);
    els.tokenBar.style.width = pct + "%";
    els.tokenSpent.textContent = (t.spent || 0).toLocaleString();
    els.tokenQuota.textContent = (t.quota || 0).toLocaleString();
    els.tokenPct.textContent   = (t.pct || 0).toFixed(2) + "%";
    els.tokenRate.textContent  = (t.rate_tokens_per_min || 0).toLocaleString();
    els.tokenPct.style.color = pct > 80 ? "var(--bad)" : pct > 50 ? "var(--warn)" : "var(--accent)";
  }
  function renderFleetHealth(f) {
    els.fhGreen.textContent  = f.GREEN  || 0;
    els.fhYellow.textContent = f.YELLOW || 0;
    els.fhRed.textContent    = f.RED    || 0;
    els.fhBlack.textContent  = f.BLACK  || 0;
  }

  function renderInference(inf) {
    if (!inf) return;
    const live = inf.mode === "LIVE-OLLAMA";
    els.inferBadge.classList.toggle("live", live);
    els.inferMode.textContent = inf.mode;
    const alive = (inf.lineup || []).filter(m => m.alive && m.loaded);
    if (live) {
      els.inferSub.textContent =
        `${alive.length}/${(inf.lineup || []).length} advisors alive · ${inf.live_calls} calls`;
    } else {
      els.inferSub.textContent = `${inf.available_models?.length || 0} ollama models reachable — click to go LIVE`;
    }
    if (inf.host_gpu) {
      els.gpuName.textContent = inf.host_gpu.name;
      els.gpuUtil.textContent = inf.host_gpu.util_pct + "%";
      els.gpuMem.textContent  = `${inf.host_gpu.mem_used_mib}/${inf.host_gpu.mem_total_mib} MiB`;
    }
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
    const all = (inf.primary || []).concat(inf.backup || []);
    const alive = all.filter(m => m.alive && m.loaded).length;
    els.lineupSub.textContent = `${alive}/${all.length} alive`;
    const fmt = (m) => {
      let state, klass;
      if (!m.loaded)            { state = "not pulled"; klass = "miss"; }
      else if (!m.alive)        { state = "DEAD";       klass = "dead"; }
      else if (m.replaced_by)   { state = "→ "+m.replaced_by; klass = "swapped"; }
      else                      { state = m.last_label || "ALIVE"; klass = "alive"; }
      const ms = m.last_call_ms ? ` ${m.last_call_ms}ms` : "";
      return `<tr class="ln-role-${m.role} ${m.alive ? "" : "dead"}">
        <td><span class="ln-dot" style="background:${m.loaded ? (m.alive ? "var(--accent)" : "var(--bad)") : "var(--ink-faint)"}"></span>
            <span class="ln-id">${escapeHtml(m.id)}</span></td>
        <td class="ln-vendor">${escapeHtml(m.vendor)}${ms}</td>
        <td class="ln-state ${klass}">${escapeHtml(state)}</td>
      </tr>`;
    };
    const rows = [];
    rows.push(`<tr class="lineup-section"><td colspan="3">PRIMARY ${(inf.primary || []).filter(m => m.alive && m.loaded).length}/${(inf.primary || []).length}</td></tr>`);
    (inf.primary || []).forEach(m => rows.push(fmt(m)));
    rows.push(`<tr class="lineup-section"><td colspan="3">BACKUP ${(inf.backup || []).filter(m => m.alive && m.loaded).length}/${(inf.backup || []).length}</td></tr>`);
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
    // Sort: warn states first within filter, then by name
    const order = { BLACK: 0, RED: 1, YELLOW: 2, GREEN: 3 };
    list.sort((a, b) => (order[a.health] - order[b.health]) || a.name.localeCompare(b.name));
    els.fleetCount.textContent = `${list.length} / ${STATE.sats.length}`;
    els.fleetList.innerHTML = list.map(s => `
      <li data-id="${s.id}" class="${STATE.focused && STATE.focused.id === s.id ? "focused" : ""}">
        <span class="fl-dot h-${s.health}"></span>
        <div>
          <div class="fl-name">${escapeHtml(s.name)}</div>
          <div class="fl-meta">${s.regime} · ${escapeHtml(s.shell || s.operator)}</div>
        </div>
        <div class="fl-tag">${s.health}</div>
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

  // ------------------------------------------------------------------ round-table SVG
  // 5 seats arranged at pentagon vertices around a central sat card.
  const RT_CX = 240, RT_CY = 175, RT_RADIUS = 130;
  const SEAT_POS = [0, 1, 2, 3, 4].map(i => {
    const a = -Math.PI / 2 + i * (2 * Math.PI / 5);
    return { x: RT_CX + Math.cos(a) * RT_RADIUS, y: RT_CY + Math.sin(a) * RT_RADIUS };
  });
  const ARBITER_POS = { x: RT_CX, y: 28 };

  function renderRoundTable(focused, brief) {
    if (!focused) { els.rtSvg.innerHTML = ""; return; }
    const votes = (brief && brief.votes) ? brief.votes.slice(0, 5) :
                  (focused.assessment ? focused.assessment.votes.slice(0, 5) : []);
    const arbiter = brief ? brief.arbiter : (focused.assessment ? focused.assessment.arbiter : null);

    const center = `
      <g class="rt-center">
        <rect x="${RT_CX - 70}" y="${RT_CY - 36}" width="140" height="72" rx="4"/>
        <text class="ct-name"   x="${RT_CX}" y="${RT_CY - 14}" text-anchor="middle">${escapeHtml(focused.name)}</text>
        <text class="ct-meta"   x="${RT_CX}" y="${RT_CY + 1}"  text-anchor="middle">${focused.regime}${focused.shell ? " · " + escapeHtml(focused.shell) : ""}</text>
        <text class="ct-health" x="${RT_CX}" y="${RT_CY + 22}" text-anchor="middle"
              style="fill:${HEALTH_COLOR[focused.health] || "#fff"}">${focused.health}</text>
      </g>`;

    // edges from seats to center
    const edges = SEAT_POS.map((p, i) => {
      const cls = (votes[i] && votes[i].label) ? "active" : "";
      return `<line class="rt-edge ${cls}" x1="${p.x}" y1="${p.y}" x2="${RT_CX}" y2="${RT_CY - 4}"/>`;
    }).join("");

    const seats = SEAT_POS.map((p, i) => {
      const v = votes[i];
      const klass = v ? `vote-${v.label}` : "thinking";
      const id    = v ? (v.model || "—") : "deliberating…";
      const tag   = v ? (v.vendor || v.family || "") : "";
      const vote  = v ? (v.label || "?")[0] : "·";
      const ms    = (v && v.ms) ? `${v.ms} ms` : "";
      const lblX = p.x; const lblY = p.y;
      const labelAbove = p.y < RT_CY;
      const idY  = labelAbove ? lblY - 32 : lblY + 38;
      const tagY = labelAbove ? lblY - 22 : lblY + 48;
      const msY  = labelAbove ? lblY - 12 : lblY + 58;
      return `<g class="rt-seat ${klass}">
        <circle cx="${p.x}" cy="${p.y}" r="18"/>
        <text class="seat-vote" x="${p.x}" y="${p.y + 6}" text-anchor="middle"
              style="fill:${v ? HEALTH_COLOR[v.label] : "var(--info)"}">${vote}</text>
        <text class="seat-id"  x="${lblX}" y="${idY}"  text-anchor="middle">${escapeHtml(id)}</text>
        <text class="seat-tag" x="${lblX}" y="${tagY}" text-anchor="middle">${escapeHtml(tag)}</text>
        <text class="seat-ms"  x="${lblX}" y="${msY}"  text-anchor="middle">${ms}</text>
      </g>`;
    }).join("");

    // arbiter chip (top), drawn only when escalation happened
    let arbiterChip = "";
    if (arbiter) {
      arbiterChip = `
        <g class="rt-arbiter">
          <line class="rt-arbiter-line" x1="${RT_CX}" y1="${ARBITER_POS.y + 22}" x2="${RT_CX}" y2="${RT_CY - 38}"/>
          <rect x="${ARBITER_POS.x - 90}" y="${ARBITER_POS.y - 18}" width="180" height="40" rx="3"/>
          <text class="ab-label" x="${ARBITER_POS.x}" y="${ARBITER_POS.y - 4}"  text-anchor="middle">T2 ARBITER</text>
          <text class="ab-vote"  x="${ARBITER_POS.x - 50}" y="${ARBITER_POS.y + 14}" text-anchor="middle"
                style="fill:${HEALTH_COLOR[arbiter.label]}">${arbiter.label || "?"}</text>
          <text class="ab-id"    x="${ARBITER_POS.x + 30}" y="${ARBITER_POS.y + 14}" text-anchor="middle">${escapeHtml(arbiter.model || "nemotron")} · ${arbiter.ms || "?"}ms</text>
        </g>`;
    }

    els.rtSvg.innerHTML = arbiterChip + edges + seats + center;

    // status text + tally
    const labels = votes.map(v => v.label).filter(Boolean);
    const ms = labels.length ? `${labels.length}/5 advisors voted` :
                "advisors deliberating…";
    els.rtStatus.textContent = arbiter ?
      `${ms} · ARBITER escalated → ${arbiter.label}` : ms;

    renderTally(votes, arbiter);
  }

  function renderTally(votes, arbiter) {
    const counts = { GREEN: 0, YELLOW: 0, RED: 0, BLACK: 0 };
    votes.forEach(v => { if (v.label) counts[v.label] = (counts[v.label] || 0) + 1; });
    const total = Math.max(1, Object.values(counts).reduce((a, b) => a + b, 0));
    const bar = ["GREEN", "YELLOW", "RED", "BLACK"]
      .map(k => `<i class="b-${k}" style="width:${100 * counts[k] / total}%"></i>`).join("");
    const cells = ["GREEN", "YELLOW", "RED", "BLACK"]
      .map(k => `<span style="color:${HEALTH_COLOR[k]}">${k.slice(0,1)}<b>${counts[k]}</b></span>`).join("");
    els.rtTally.innerHTML = `
      <div class="rt-bar">${bar}</div>
      <div class="rt-counts">${cells}${arbiter ? `<span style="color:var(--warn);margin-left:8px">ARB ${arbiter.label}</span>` : ""}</div>`;
  }

  // ------------------------------------------------------------------ mission brief
  function renderBrief(brief) {
    if (!brief) { els.brief.innerHTML = "<i style='color:var(--ink-faint)'>awaiting first round-table…</i>"; return; }
    STATE.brief = brief;
    els.briefTs.textContent = brief.provenance?.ts?.replace("T", " ").replace("Z", "Z") || "—";
    const labelCls = `h-${brief.health}`;
    const actionCls = ({ NOMINAL: "green", MONITOR: "", "SAFE-MODE": "red", RETIRE: "black" })[brief.action] || "";
    const voteRows = brief.votes.map(v => `
      <div class="brief-vote-row">
        <div>${escapeHtml(v.model || "?")} <span class="bv-vendor">${escapeHtml(v.vendor || "")}</span></div>
        <div class="bv-label ${v.label}">${v.label}</div>
        <div class="bv-ms">${v.ms || "—"}ms</div>
      </div>`).join("");
    const factors = brief.drivers || {};
    const factorRow = (label, value, hint) => {
      const pct = Math.min(120, value * 100);
      return `<div class="bf-row">
        <span>${label}</span>
        <div class="bf-bar"><i style="width:${pct}%"></i></div>
        <b>${value.toFixed(2)}</b>
        <div style="grid-column:2/-1;color:var(--ink-faint);font-size:9.5px">${hint}</div>
      </div>`;
    };
    const arbiter = brief.arbiter;

    els.brief.innerHTML = `
      <div class="brief-section subject">
        <div class="brief-label">SUBJECT</div>
        <div class="brief-body">
          <b>${escapeHtml(brief.subject)}</b> — ${brief.regime}${brief.shell ? " / " + escapeHtml(brief.shell) : ""}
          · op ${escapeHtml(brief.operator)}
        </div>
      </div>
      <div class="brief-section">
        <div class="brief-label">SYNOPSIS</div>
        <div class="brief-body">${escapeHtml(brief.synopsis || "")}</div>
        <div class="brief-body">HEALTH <b class="${labelCls}">${brief.health}</b>${brief.transition ? ` <span style="color:var(--ink-faint)">(${escapeHtml(brief.transition)})</span>` : ""}</div>
      </div>
      <div class="brief-section">
        <div class="brief-label">ADVISOR VOTES (${brief.votes.length})</div>
        <div>${voteRows}</div>
      </div>
      ${arbiter ? `
      <div class="brief-section arbiter">
        <div class="brief-label">T2 ARBITER · ESCALATED</div>
        <div class="brief-body"><b>${escapeHtml(arbiter.model || "")}</b> → <b style="color:${HEALTH_COLOR[arbiter.label]}">${arbiter.label}</b> in ${arbiter.ms || "?"} ms</div>
        ${arbiter.rationale ? `<div class="brief-body" style="color:var(--ink-dim);font-style:italic;font-size:10.5px">${escapeHtml(arbiter.rationale.slice(0, 300))}</div>` : ""}
      </div>` : ""}
      <div class="brief-section">
        <div class="brief-label">DRIVERS</div>
        <div class="brief-factors">
          ${factorRow("AGE",     factors.age || 0,     "vs design life")}
          ${factorRow("TID",     factors.tid || 0,     "accumulated dose")}
          ${factorRow("SEE 30d", factors.see || 0,     "single-event upsets")}
          ${factorRow("WEATHER", factors.weather || 0, `Kp ${brief.weather?.kp || "?"} · X-ray ${brief.weather?.xray_class || "?"}`)}
        </div>
      </div>
      <div class="brief-section action ${actionCls}">
        <div class="brief-label">RECOMMENDED ACTION</div>
        <div class="brief-body"><b>${brief.action}</b></div>
      </div>
      <div class="brief-section">
        <div class="brief-label">PROVENANCE</div>
        <div class="brief-kv">
          <div class="k">event_id</div>     <div class="v">${escapeHtml(brief.provenance?.event_id || "")}</div>
          <div class="k">evidence_hash</div><div class="v">${escapeHtml((brief.provenance?.evidence_hash || "").slice(0, 16))}…</div>
          <div class="k">parser</div>       <div class="v">${escapeHtml(brief.provenance?.parser_version || "")}</div>
          <div class="k">review</div>       <div class="v">${escapeHtml(brief.review_status || "")}</div>
        </div>
      </div>`;
  }
  els.btnApprove.addEventListener("click", () =>
    fetch("/api/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }));
  els.btnReview.addEventListener("click", () => {
    if (STATE.brief) console.log("brief:", STATE.brief);  // operator can grab it from devtools for now
  });

  // ------------------------------------------------------------------ earth (compact)
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
      const o = satEls[id];
      const p = satPos(o, t);
      o.dot.setAttribute("cx", p.x);
      o.dot.setAttribute("cy", p.y);
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

  // ------------------------------------------------------------------ telemetry + lifecycle
  const LC_ORDER = ["Pre-Launch", "In-Orbit Operations", "Event Management",
                    "Deorbiting / Disposal", "Decommissioned"];
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
    const idx = LC_ORDER.indexOf(f.lifecycle_stage);
    [...els.lifecycle.children].forEach((c, i) => {
      c.classList.toggle("active", i === idx);
      c.classList.toggle("passed", i < idx);
    });
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
    if (s.fleet_health) renderFleetHealth(s.fleet_health);
    if (s.tokens) renderTokens(s.tokens);
    if (s.inference) renderInference(s.inference);
    buildSats(STATE.sats);
    renderFleet();
    if (STATE.focused) {
      els.focusName.textContent = STATE.focused.name;
      els.focusHealth.textContent = STATE.focused.health;
      els.focusHealth.style.color = HEALTH_COLOR[STATE.focused.health];
      renderRoundTable(STATE.focused, STATE.brief);
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
      els.focusHealth.textContent = STATE.focused.health;
      els.focusHealth.style.color = HEALTH_COLOR[STATE.focused.health];
      renderTelemetry(STATE.focused);
      // Only update the round-table when the brief is for the *currently focused* sat
      const b = m.brief;
      if (b && b.subject_id === STATE.focused.id) {
        STATE.brief = b;
        renderRoundTable(STATE.focused, b);
        renderBrief(b);
      } else {
        renderRoundTable(STATE.focused, STATE.brief);
      }
    }
  }

  function connect() {
    const es = new EventSource("/api/stream");
    es.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case "snapshot":     applySnapshot(m); break;
        case "fleet_update": applyFleetUpdate(m); break;
        case "focus_change": STATE.focused = m.focused; STATE.brief = null;
                             els.rtStatus.textContent = "advisors deliberating…";
                             applyFleetUpdate({ focused: m.focused }); break;
        case "tokens":       renderTokens(m.tokens); break;
        case "inference":    renderInference(m.inference); break;
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
