// Spacesharks Mission Desk — dashboard front-end.
// Renders the health-monitor MVP. No build step, no deps.

(() => {
  "use strict";
  const $   = (id) => document.getElementById(id);
  const svgNS = "http://www.w3.org/2000/svg";
  const HEALTH_COLOR = { GREEN: "#3df0c8", YELLOW: "#ffd166", RED: "#ff6470", BLACK: "#222" };

  // ------------------------------------------------------------------
  // Element handles
  // ------------------------------------------------------------------
  const els = {
    clock: $("clock"),
    inferBadge: $("infer-badge"), inferMode: $("infer-mode"), inferSub: $("infer-sub"),
    agentSub: $("agent-sub"),
    gpuName: $("gpu-name"), gpuUtil: $("gpu-util"), gpuMem: $("gpu-mem"),
    tokenBar: $("token-bar"), tokenSpent: $("token-spent"),
    tokenQuota: $("token-quota"), tokenPct: $("token-pct"), tokenRate: $("token-rate"),
    fhGreen: $("fh-green"), fhYellow: $("fh-yellow"), fhRed: $("fh-red"), fhBlack: $("fh-black"),
    focusName: $("focus-name"), focusHealth: $("focus-health"),
    trustSvg: $("trust-svg"), trustPct: $("trust-pct"),
    trustTarget: $("trust-target"), trustFinal: $("trust-final"),
    wxGrid: $("wx-grid"),
    lineupTbl: $("lineup-tbl"),
    earth: $("earth"), stars: $("stars"),
    continents: $("continents"), graticule: $("graticule"),
    satLayer: $("sat-layer"), focusOverlay: $("focus-overlay"),
    hudAlt: $("hud-alt"), hudVel: $("hud-vel"),
    hudIncl: $("hud-incl"), hudOp: $("hud-op"),
    copilot: $("copilot-stream"), recBody: $("rec-body"),
    btnApprove: $("btn-approve"), btnReview: $("btn-review"),
    lcSat: $("lc-sat"), lifecycle: $("lifecycle"), lcStats: $("lc-stats"),
    telSat: $("tel-sat"),
    telAlt: $("tel-alt"), telVel: $("tel-vel"), telSig: $("tel-sig"),
    telAltVal: $("tel-alt-val"), telVelVal: $("tel-vel-val"), telSigVal: $("tel-sig-val"),
    dosSat: $("dos-sat"), dossier: $("dossier"), healthFactors: $("health-factors"),
    drawer: $("drawer"), drawerToggle: $("drawer-toggle"),
    logBody: $("log-body"), logCount: $("log-count"),
    alertsBody: $("alerts-body"), alertCount: $("alert-count"),
    fleetBody: $("fleet-body"),
  };
  const LOG_CAP = 6;

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  const STATE = {
    sats: [],         // public_sat list
    fleet: {},        // health counts
    weather: {},
    focused: null,
    tokens: { spent: 0, quota: 1, pct: 0, calls: 0, rate_tokens_per_min: 0, by_model: {} },
    assessors: [],
    logCount: 0,
  };

  // ------------------------------------------------------------------
  // Top bar
  // ------------------------------------------------------------------
  function tickClock() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    els.clock.textContent =
      `${d.toLocaleDateString("en-GB", { weekday: "short" }).toUpperCase()} ` +
      `${pad(d.getDate())} ${d.toLocaleDateString("en-GB", { month: "short" }).toUpperCase()} ` +
      `${d.getFullYear()} | ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
  }
  setInterval(tickClock, 1000);
  tickClock();

  function renderTokens(t) {
    STATE.tokens = t;
    const pct = Math.min(100, t.pct || 0);
    els.tokenBar.style.width = pct + "%";
    els.tokenSpent.textContent = (t.spent || 0).toLocaleString();
    els.tokenQuota.textContent = (t.quota || 0).toLocaleString();
    els.tokenPct.textContent   = (t.pct || 0).toFixed(2) + "%";
    els.tokenRate.textContent  = (t.rate_tokens_per_min || 0).toLocaleString();
    // shift colour towards red as quota fills:
    if (pct > 80)      els.tokenPct.style.color = "var(--bad)";
    else if (pct > 50) els.tokenPct.style.color = "var(--warn)";
    else               els.tokenPct.style.color = "var(--accent)";
  }
  function renderFleetHealth(f) {
    STATE.fleet = f;
    els.fhGreen.textContent  = f.GREEN  || 0;
    els.fhYellow.textContent = f.YELLOW || 0;
    els.fhRed.textContent    = f.RED    || 0;
    els.fhBlack.textContent  = f.BLACK  || 0;
  }

  // ------------------------------------------------------------------
  // Earth — graticule, continents, stars
  // ------------------------------------------------------------------
  const CENTER = { x: 400, y: 260 };
  const R = 170;

  function buildStars() {
    const out = [];
    for (let i = 0; i < 220; i++) {
      const x = Math.random() * 800;
      const y = Math.random() * 520;
      const dx = x - CENTER.x, dy = y - CENTER.y;
      if (dx * dx + dy * dy < (R + 30) * (R + 30)) continue;  // no stars over the globe
      const r = Math.random() < 0.85 ? 0.5 : (Math.random() < 0.6 ? 0.9 : 1.4);
      const a = (0.25 + Math.random() * 0.65).toFixed(2);
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="white" fill-opacity="${a}"/>`);
    }
    els.stars.innerHTML = out.join("");
  }

  function buildGraticule() {
    const lines = [];
    // latitudes (5 ellipses)
    for (let i = 1; i <= 4; i++) {
      const ry = R * Math.cos((i * Math.PI) / 10);
      lines.push(`<ellipse cx="${CENTER.x}" cy="${CENTER.y - R * Math.sin((i * Math.PI) / 10) * 0}" ` +
                 `rx="${R}" ry="${ry}"/>`);
    }
    // equator
    lines.push(`<line x1="${CENTER.x - R}" y1="${CENTER.y}" x2="${CENTER.x + R}" y2="${CENTER.y}"/>`);
    // longitudes (vertical ellipses by rotating)
    for (let i = 0; i < 8; i++) {
      const rx = R * Math.abs(Math.cos((i * Math.PI) / 8));
      lines.push(`<ellipse cx="${CENTER.x}" cy="${CENTER.y}" rx="${rx}" ry="${R}"/>`);
    }
    els.graticule.innerHTML = lines.join("");
  }

  // Very-stylized continent silhouettes (decorative, not cartographic).
  function buildContinents() {
    const cx = CENTER.x, cy = CENTER.y;
    const paths = [
      // Africa-ish
      `M${cx-12},${cy-30} q22,-6 30,18 t-8,52 q-14,18 -32,8 t-10,-50 q-2,-24 20,-28z`,
      // Eurasia-ish (top)
      `M${cx-72},${cy-90} q40,-12 90,4 t60,-10 q22,12 8,32 t-90,16 q-50,-2 -68,-22 z`,
      // Americas-ish (left)
      `M${cx-148},${cy-60} q-12,30 4,60 t8,80 q-18,4 -22,-30 t-16,-60 q-2,-46 26,-50z`,
      // SE Asia / Australia (lower right)
      `M${cx+60},${cy+30} q24,-2 38,18 t-10,28 q-22,8 -36,-6 t-30,-22 q4,-22 38,-18z`,
      // Greenland blob
      `M${cx-90},${cy-110} q14,-8 22,6 t-8,18 q-16,2 -14,-24z`,
    ];
    els.continents.innerHTML = paths.map(d => `<path d="${d}"/>`).join("");
  }

  // ------------------------------------------------------------------
  // Sats on the globe — orbital rings with eye-level perspective
  // ------------------------------------------------------------------
  const REGIME_RX  = { LEO: 195, SSO: 215, MEO: 290, GEO: 370 };
  const REGIME_RY  = { LEO: 60,  SSO: 95,  MEO: 135, GEO: 195 };
  const REGIME_SPD = { LEO: 0.14,SSO: 0.10,MEO: 0.04,GEO: 0.014 };

  const satEls = {};   // id -> { dot, def, phase, label }

  function buildSats(satList) {
    els.satLayer.innerHTML = "";
    Object.keys(satEls).forEach(k => delete satEls[k]);
    // group by regime to space initial phases
    const groups = {};
    satList.forEach(s => { (groups[s.regime] = groups[s.regime] || []).push(s); });
    for (const regime in groups) {
      const arr = groups[regime];
      arr.forEach((s, i) => {
        const phase = i / arr.length;
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("r", regime === "GEO" ? 4.2 : regime === "MEO" ? 3.6 : 3.2);
        c.setAttribute("class", `sat h-${s.health}`);
        c.dataset.id = s.id;
        c.dataset.name = s.name;
        c.addEventListener("click", () => focusSat(s.id));
        els.satLayer.appendChild(c);
        satEls[s.id] = { dot: c, def: s, phase };
      });
    }
  }

  function satPos(satObj, t) {
    const def = satObj.def;
    const speed = REGIME_SPD[def.regime] || 0.1;
    const ang = (satObj.phase + t * speed) * Math.PI * 2;
    return {
      x: CENTER.x + Math.cos(ang) * REGIME_RX[def.regime],
      y: CENTER.y + Math.sin(ang) * REGIME_RY[def.regime] * 0.55,
      // 0.55 squeeze gives the "Earth as ball, orbits go in front/behind" feel
    };
  }

  function animateGlobe() {
    const t = performance.now() / 1000;
    for (const id in satEls) {
      const o = satEls[id];
      const p = satPos(o, t);
      o.dot.setAttribute("cx", p.x);
      o.dot.setAttribute("cy", p.y);
      // back half slightly dimmed for depth
      const isBack = Math.sin((o.phase + t * REGIME_SPD[o.def.regime]) * Math.PI * 2) > 0;
      o.dot.setAttribute("fill-opacity", isBack ? "0.55" : "1");
    }
    drawFocusOverlay(t);
    requestAnimationFrame(animateGlobe);
  }

  function drawFocusOverlay(t) {
    const f = STATE.focused;
    if (!f) { els.focusOverlay.innerHTML = ""; return; }
    const o = satEls[f.id];
    if (!o) return;
    const p = satPos(o, t);
    // draw a faint track ring + callout
    els.focusOverlay.innerHTML =
      `<ellipse class="focus-track" cx="${CENTER.x}" cy="${CENTER.y}" ` +
      `rx="${REGIME_RX[f.regime]}" ry="${(REGIME_RY[f.regime] * 0.55).toFixed(1)}"/>` +
      `<circle class="sat focused h-${f.health}" cx="${p.x}" cy="${p.y}" r="6" fill-opacity="0.9"/>` +
      `<rect class="focus-callout" x="${p.x + 12}" y="${p.y - 22}" width="120" height="44" rx="2"/>` +
      `<text class="focus-callout-text" x="${p.x + 18}" y="${p.y - 8}">${escapeHtml(f.name)}</text>` +
      `<text class="focus-callout-text k" x="${p.x + 18}" y="${p.y + 6}">${f.regime} · ${f.altitude_km} km</text>` +
      `<text class="focus-callout-text k" x="${p.x + 18}" y="${p.y + 18}">HEALTH ${f.health}</text>`;
    // HUD
    els.hudAlt.textContent  = `Alt:  ${f.altitude_km} km`;
    els.hudVel.textContent  = `Incl: ${f.inclination_deg}°`;
    els.hudIncl.textContent = `Op:   ${f.operator}`;
    els.hudOp.textContent   = `Stage:${f.lifecycle_stage}`;
  }

  // ------------------------------------------------------------------
  // Trust stack — branching tree
  // ------------------------------------------------------------------
  function renderTrust(focused) {
    if (!focused || !focused.assessment) return;
    const a = focused.assessment;
    els.trustPct.textContent = a.consensus_pct + "%";
    els.trustTarget.textContent = focused.name;
    els.trustFinal.textContent = `CONSENSUS: ${a.consensus_label}  ·  ${a.consensus_pct}%`;
    els.trustFinal.style.color = HEALTH_COLOR[a.consensus_label];
    els.trustFinal.style.borderColor = HEALTH_COLOR[a.consensus_label];
    // build branching tree
    const W = 280, H = 220;
    const leftX = 25, rightX = 245;
    const reqY = H / 2;
    const votes = a.votes.slice(0, 6);
    const n = votes.length;
    const lines = [];
    // request node
    lines.push(`<g class="trust-node"><circle cx="${leftX}" cy="${reqY}" r="14"/>` +
               `<text x="${leftX}" y="${reqY + 3}" text-anchor="middle">REQ</text></g>`);
    votes.forEach((v, i) => {
      const y = 22 + i * ((H - 44) / Math.max(1, n - 1));
      const liveTag = v.live ? "★" : "";
      const labelChar = (v.label || "?")[0];
      const tagText = (v.vendor || v.family || "").slice(0, 12);
      const idText  = (v.model || "").slice(0, 22);
      lines.push(`<path class="trust-edge ${v.label === "GREEN" ? "" : "dim"}" ` +
                 `d="M${leftX + 14},${reqY} C${(leftX + rightX) / 2},${reqY} ${(leftX + rightX) / 2},${y} ${rightX - 24},${y}"/>`);
      lines.push(`<g class="trust-node vote-${v.label} ${v.live ? "live" : ""}">` +
                 `<circle cx="${rightX - 12}" cy="${y}" r="9"/>` +
                 `<text x="${rightX - 12}" y="${y + 2}" text-anchor="middle">${labelChar}</text>` +
                 `<text class="id"  x="${rightX - 26}" y="${y - 2}" text-anchor="end">${idText} ${liveTag}</text>` +
                 `<text class="tag" x="${rightX - 26}" y="${y + 8}" text-anchor="end">${tagText}${v.ms ? " · " + v.ms + "ms" : ""}</text>` +
                 `</g>`);
    });
    els.trustSvg.innerHTML = lines.join("");
  }

  function renderWeather(wx) {
    STATE.weather = wx;
    els.wxGrid.innerHTML = `
      <span>Kp index</span><b>${wx.kp}</b>
      <span>X-ray</span><b>${wx.xray_class}</b>
      <span>SEP &gt;10MeV</span><b>${wx.sep_pfu} pfu</b>
      <span>AE</span><b>${wx.ae} nT</b>
      <span>storm</span><b>${wx.storm_regime || "—"}</b>`;
  }

  // ------------------------------------------------------------------
  // Copilot stream
  // ------------------------------------------------------------------
  function pushCopilot(e) {
    const div = document.createElement("div");
    div.className = `cop-entry ${e.who}`;
    const who = e.who === "user" ? (e.who_label || "Sampras") : "AI AGENT";
    let meta = "";
    if (e.recommendation) meta += `<div class="cop-meta">RECOMMEND <b>${e.recommendation}</b></div>`;
    if (e.action)         meta += `<div class="cop-meta">ACTION <b>${e.action}</b></div>`;
    div.innerHTML =
      `<div class="cop-head"><span class="who ${e.who}">${who}</span><span>${e.ts} UTC</span></div>` +
      `<div class="cop-msg">${escapeHtml(e.msg)}</div>${meta}`;
    els.copilot.appendChild(div);
    els.copilot.scrollTop = els.copilot.scrollHeight;
    while (els.copilot.children.length > 50) els.copilot.removeChild(els.copilot.firstChild);
    if (e.recommendation) {
      els.recBody.textContent = `${e.msg}  →  ${e.recommendation}`;
    }
  }

  // ------------------------------------------------------------------
  // Lifecycle chevrons
  // ------------------------------------------------------------------
  const LC_ORDER = ["Pre-Launch", "In-Orbit Operations", "Event Management",
                    "Deorbiting / Disposal", "Decommissioned"];
  function renderLifecycle(f) {
    if (!f) return;
    els.lcSat.textContent = `${f.name} [ID: ${f.id}]`;
    const idx = LC_ORDER.indexOf(f.lifecycle_stage);
    [...els.lifecycle.children].forEach((c, i) => {
      c.classList.toggle("active", i === idx);
      c.classList.toggle("passed", i < idx);
    });
    els.lcStats.innerHTML = `
      <div><span>OPERATOR</span><b>${escapeHtml(f.operator)}</b></div>
      <div><span>LAUNCHED</span><b>${f.launched}</b></div>
      <div><span>AGE / LIFE</span><b>${f.age_years}y / ${f.design_life_years}y (${f.design_life_pct}%)</b></div>
      <div><span>MISSION</span><b>${f.mission_type.toUpperCase()}</b></div>`;
  }

  // ------------------------------------------------------------------
  // Telemetry sparklines
  // ------------------------------------------------------------------
  function renderTelemetry(f) {
    if (!f || !f.telemetry) return;
    els.telSat.textContent = `${f.name} LIVE`;
    drawSpark(els.telAlt, f.telemetry.alt);
    drawSpark(els.telVel, f.telemetry.vel);
    drawSpark(els.telSig, f.telemetry.sig);
    const last = (arr) => arr.length ? arr[arr.length - 1] : "--";
    els.telAltVal.textContent = last(f.telemetry.alt);
    els.telVelVal.textContent = last(f.telemetry.vel);
    els.telSigVal.textContent = last(f.telemetry.sig);
  }
  function drawSpark(el, data) {
    if (!data || !data.length) return;
    const W = 300, H = 60;
    const min = Math.min(...data), max = Math.max(...data);
    const span = Math.max(0.001, max - min);
    const pts = data.map((v, i) =>
      `${(i / (data.length - 1) * W).toFixed(1)},${(H - 5 - ((v - min) / span) * (H - 10)).toFixed(1)}`
    ).join(" ");
    el.setAttribute("points", pts);
  }

  // ------------------------------------------------------------------
  // Dossier + health factors
  // ------------------------------------------------------------------
  function renderDossier(f) {
    if (!f) return;
    els.dosSat.textContent = `${f.name} · ${f.regime}`;
    els.dossier.innerHTML = `
      <div class="k">Operator</div><div class="v">${escapeHtml(f.operator)}</div>
      <div class="k">Launched</div><div class="v dim">${f.launched}</div>
      <div class="k">Mass</div><div class="v dim">${(f.altitude_km).toLocaleString()} km alt</div>
      <div class="k">Inclination</div><div class="v dim">${f.inclination_deg}°</div>
      <div class="k">Mission</div><div class="v">${escapeHtml(f.mission_type)}</div>
      <div class="k">Stage</div><div class="v" style="color:${HEALTH_COLOR[f.health]}">${escapeHtml(f.lifecycle_stage)}</div>
      <div class="k">Health</div><div class="v" style="color:${HEALTH_COLOR[f.health]}"><b>${f.health}</b> (score ${f.score})</div>
      <div class="k">Last assessed</div><div class="v dim">${f.last_assessed || "—"}</div>`;
    if (f.assessment && f.assessment.factors) {
      const factor = f.assessment.factors;
      els.healthFactors.innerHTML = `
        ${factorBar("AGE",     factor.age,     `${f.age_years}y / ${f.design_life_years}y`)}
        ${factorBar("TID",     factor.tid,     `${f.tid_accumulated_krad} / ${f.tid_budget_krad} krad`)}
        ${factorBar("SEE 30d", factor.see,     `${f.see_events_30d} events`)}
        ${factorBar("WEATHER", factor.weather, `Kp ${STATE.weather.kp || "--"}`)}`;
    }
  }
  function factorBar(label, value, hint) {
    const pct = Math.min(120, value * 100);
    return `<div class="hf-row">
      <span>${label}</span>
      <div class="hf-bar"><i style="width:${pct}%"></i></div>
      <b>${value.toFixed(2)}</b>
      <span style="grid-column:2/-1;color:var(--ink-faint);font-size:10px">${hint}</span>
    </div>`;
  }

  // ------------------------------------------------------------------
  // Drawer (collapsible secondary panels)
  // ------------------------------------------------------------------
  els.drawerToggle.addEventListener("click", () =>
    els.drawer.classList.toggle("collapsed"));

  // ------------------------------------------------------------------
  // Fleet table (in drawer)
  // ------------------------------------------------------------------
  function renderFleetTable() {
    els.fleetBody.innerHTML = STATE.sats.map(s => `
      <tr data-id="${s.id}">
        <td class="h"><span class="pill pill-${s.health}"></span> ${s.health}</td>
        <td>${escapeHtml(s.name)}</td>
        <td>${s.regime}</td>
        <td>${s.age_years}y / ${s.design_life_years}y</td>
        <td>${s.tid_pct}%</td>
        <td>${s.score}</td>
      </tr>`).join("");
    els.fleetBody.querySelectorAll("tr").forEach(tr => {
      tr.addEventListener("click", () => focusSat(tr.dataset.id));
    });
  }

  // ------------------------------------------------------------------
  // Log + alerts
  // ------------------------------------------------------------------
  function pushLog(satId, health, transition) {
    STATE.logCount++;
    const li = document.createElement("li");
    li.className = `health-${health}`;
    const ts = new Date().toISOString().slice(11, 19);
    const sat = STATE.sats.find(s => s.id === satId);
    li.innerHTML = `<span class="ts">${ts}</span>` +
                   `<span><b>${health}</b> ${escapeHtml(sat ? sat.name : satId)} ${transition ? "· " + escapeHtml(transition) : ""}</span>`;
    els.logBody.prepend(li);
    while (els.logBody.children.length > LOG_CAP) els.logBody.removeChild(els.logBody.lastChild);
    els.logCount.textContent = STATE.logCount + " entries";
  }
  let alertN = 0;
  function pushAlert(a) {
    alertN++;
    const li = document.createElement("li");
    li.className = `sev-${a.severity}`;
    li.innerHTML = `<span class="a-ts">[${a.ts}]</span><span class="a-sev">${a.severity}</span>${escapeHtml(a.message)}`;
    els.alertsBody.prepend(li);
    while (els.alertsBody.children.length > 40) els.alertsBody.removeChild(els.alertsBody.lastChild);
    els.alertCount.textContent = alertN + " total";
  }

  // ------------------------------------------------------------------
  // Focus a sat (server-driven)
  // ------------------------------------------------------------------
  function focusSat(satId) {
    fetch("/api/focus", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sat: satId }),
    });
  }
  els.btnApprove.addEventListener("click", () =>
    fetch("/api/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }));
  els.btnReview.addEventListener("click", () =>
    els.drawer.classList.remove("collapsed"));

  // ------------------------------------------------------------------
  // Apply a full snapshot
  // ------------------------------------------------------------------
  function applySnapshot(s) {
    STATE.sats = s.sats || [];
    STATE.focused = s.focused;
    if (s.fleet_health) renderFleetHealth(s.fleet_health);
    if (s.weather) renderWeather(s.weather);
    if (s.tokens) renderTokens(s.tokens);
    if (s.inference) renderInference(s.inference);
    buildSats(STATE.sats);
    renderFleetTable();
    if (STATE.focused) {
      els.focusName.textContent = STATE.focused.name;
      els.focusHealth.textContent = STATE.focused.health;
      els.focusHealth.style.color = HEALTH_COLOR[STATE.focused.health];
      renderTrust(STATE.focused);
      renderLifecycle(STATE.focused);
      renderTelemetry(STATE.focused);
      renderDossier(STATE.focused);
    }
    if (s.copilot)  s.copilot.forEach(pushCopilot);
    if (s.alerts)   s.alerts.forEach(pushAlert);
  }

  function applyFleetUpdate(m) {
    if (m.fleet_health) renderFleetHealth(m.fleet_health);
    if (m.weather) renderWeather(m.weather);
    if (m.tokens) renderTokens(m.tokens);
    if (m.inference) renderInference(m.inference);
    STATE.sats = m.sats || STATE.sats;
    STATE.focused = m.focused || STATE.focused;
    // update sat health classes without rebuilding
    STATE.sats.forEach(s => {
      const o = satEls[s.id];
      if (o) {
        o.dot.setAttribute("class", `sat h-${s.health}`);
        o.def = s;
      }
    });
    renderFleetTable();
    if (STATE.focused) {
      els.focusName.textContent = STATE.focused.name;
      els.focusHealth.textContent = STATE.focused.health;
      els.focusHealth.style.color = HEALTH_COLOR[STATE.focused.health];
      renderTrust(STATE.focused);
      renderLifecycle(STATE.focused);
      renderTelemetry(STATE.focused);
      renderDossier(STATE.focused);
    }
    if (m.last_assessed) {
      pushLog(m.last_assessed.sat_id, m.last_assessed.health, m.last_assessed.assessment.transition);
    }
  }

  // ------------------------------------------------------------------
  // SSE connect
  // ------------------------------------------------------------------
  function connect() {
    const es = new EventSource("/api/stream");
    es.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case "snapshot":     applySnapshot(m); break;
        case "fleet_update": applyFleetUpdate(m); break;
        case "focus_change": STATE.focused = m.focused; applyFleetUpdate({ focused: m.focused }); break;
        case "copilot":      pushCopilot(m.entry); break;
        case "alert":        pushAlert(m.alert); break;
        case "tokens":       renderTokens(m.tokens); break;
        case "inference":    renderInference(m.inference); break;
      }
    };
    es.onerror = () => {
      es.close();
      setTimeout(connect, 1500);
    };
  }

  // ------------------------------------------------------------------
  // Inference badge + GPU readout
  // ------------------------------------------------------------------
  function renderInference(inf) {
    if (!inf) return;
    const live = inf.mode === "LIVE-OLLAMA";
    els.inferBadge.classList.toggle("live", live);
    els.inferMode.textContent = inf.mode;
    const lineup = inf.lineup || [];
    const alive = lineup.filter(m => m.alive && m.loaded);
    if (live) {
      const ms = inf.last_lineup_call_ms;
      els.inferSub.textContent =
        `${alive.length}/${lineup.length} models alive · lineup tick ${ms ? ms + " ms" : "—"} · ${inf.live_calls} calls`;
      els.agentSub.textContent = `[ ${alive.length} model${alive.length === 1 ? "" : "s"} LIVE ]`;
    } else {
      els.inferSub.textContent = `${inf.available_models?.length || 0} ollama models reachable — click to go LIVE`;
      els.agentSub.textContent = "[ SIM-MODE — click badge to go LIVE ]";
    }
    if (inf.host_gpu) {
      els.gpuName.textContent = inf.host_gpu.name;
      els.gpuUtil.textContent = inf.host_gpu.util_pct + "%";
      els.gpuMem.textContent  = `${inf.host_gpu.mem_used_mib}/${inf.host_gpu.mem_total_mib} MiB`;
    } else {
      els.gpuName.textContent = "n/a";
      els.gpuUtil.textContent = "—";
      els.gpuMem.textContent  = "—";
    }
    renderLineup(inf);
  }

  function renderLineup(inf) {
    if (!els.lineupTbl) return;
    const rows = [];
    const fmt = (m) => {
      let state, klass;
      if (!m.loaded)      { state = "not pulled"; klass = "miss"; }
      else if (!m.alive)  { state = "DEAD";       klass = "dead"; }
      else if (m.replaced_by) { state = "→ " + m.replaced_by; klass = "swapped"; }
      else                { state = m.last_label || "ALIVE"; klass = "alive"; }
      const swap = m.replaced_by ? ` <span class="ln-vendor">(swapped → ${m.replaced_by})</span>` : "";
      const ms = m.last_call_ms ? ` ${m.last_call_ms}ms` : "";
      return `<tr class="ln-role-${m.role} ${m.alive ? "" : "dead"}">
        <td><span class="ln-dot" style="background:${m.loaded ? (m.alive ? "var(--accent)" : "var(--bad)") : "var(--ink-faint)"}"></span>
            <span class="ln-id">${escapeHtml(m.id)}</span>${swap}</td>
        <td class="ln-vendor">${escapeHtml(m.vendor)}${ms}</td>
        <td class="ln-state ${klass}">${escapeHtml(state)}</td>
      </tr>`;
    };
    rows.push(`<tr class="lineup-section"><td colspan="3">PRIMARY ${(inf.primary || []).filter(m => m.alive && m.loaded).length}/${(inf.primary || []).length}</td></tr>`);
    (inf.primary || []).forEach(m => rows.push(fmt(m)));
    rows.push(`<tr class="lineup-section"><td colspan="3">BACKUP ${(inf.backup || []).filter(m => m.alive && m.loaded).length}/${(inf.backup || []).length}</td></tr>`);
    (inf.backup || []).forEach(m => rows.push(fmt(m)));
    els.lineupTbl.querySelector("tbody").innerHTML = rows.join("");
  }
  els.inferBadge.addEventListener("click", async () => {
    els.inferSub.textContent = "probing Ollama…";
    try {
      const r = await fetch("/api/probe-ollama", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
        .then(r => r.json());
      if (!r.ok) {
        els.inferSub.textContent = `${r.reason || "probe failed"}${r.available ? " — try: " + r.available.slice(0,3).join(", ") : ""}`;
        return;
      }
      // success — server will push an `inference` SSE event, but update immediately too
      els.inferBadge.classList.add("live");
      els.inferMode.textContent = "LIVE-OLLAMA";
      els.inferSub.textContent = `${r.model} · ${r.ms} ms · "${(r.response || "").slice(0, 40)}"`;
    } catch (err) {
      els.inferSub.textContent = "probe error: " + err;
    }
  });

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------
  buildStars();
  buildGraticule();
  buildContinents();
  requestAnimationFrame(animateGlobe);
  connect();
})();
