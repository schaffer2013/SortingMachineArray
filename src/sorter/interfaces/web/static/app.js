const json = async (url, options = {}) => {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || "Request failed");
  return body;
};
const pretty = value => JSON.stringify(value, null, 2);
const renderRuntimeBanner = status => {
  const banner = document.querySelector("#runtime-banner");
  if (!banner || !status) return;
  const live = status.runtime_target === "hardware_serial";
  banner.className = live ? "runtime-banner live" : "runtime-banner sim";
  banner.textContent = live
    ? `LIVE HARDWARE: ${status.serial_board?.port || "serial board"}`
    : "SIM BACKED: connect serial on System";
};
const refreshRuntimeBanner = async () => {
  try {
    renderRuntimeBanner(await json("/api/status"));
  } catch (error) {
  }
};
refreshRuntimeBanner();
setInterval(refreshRuntimeBanner, 2000);

window.SorterPages = {
  dashboard() {
    const summary = document.querySelector("#status-summary");
    const piles = document.querySelector("#pile-grid");
    const latest = document.querySelector("#latest-recognition");
    const pill = document.querySelector("#lifecycle-pill");
    document.querySelectorAll("[data-run]").forEach(button => button.onclick = async () => {
      await json(`/api/run/${button.dataset.run}`, {method: "POST"});
      refresh();
    });
    async function refresh() {
      const [status, snapshot] = await Promise.all([json("/api/status"), json("/api/snapshot")]);
      renderRuntimeBanner(status);
      pill.textContent = status.lifecycle;
      summary.innerHTML = [
        ["Phase", status.phase],
        ["Command", status.active_command || "—"],
        ["Moves", status.metrics.move_count],
        ["Scans", status.metrics.scan_count],
        ["Vacuum", status.vacuum_on ? "On" : "Off"],
        ["Distance", `${status.metrics.distance_mm.toFixed(1)} mm`],
      ].map(([k,v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
      piles.innerHTML = snapshot.piles.map(pile => `
        <article class="pile-card">
          <h3>Pile ${pile.number} · ${pile.role}</h3>
          <div class="stacked-copy muted">
            <span>Count: ${pile.known_count ? pile.count : "?"}</span>
            <span>Observation: ${pile.observation_state}</span>
            <span>Top: ${pile.top_card_name || "—"}</span>
            <span>Confidence: ${Number(pile.confidence || 0).toFixed(3)}</span>
          </div>
        </article>`).join("");
      const scan = status.last_recognition;
      latest.innerHTML = scan ? `
        <span>Name: ${scan.card_name || "—"}</span>
        <span>Confidence: ${Number(scan.confidence || 0).toFixed(3)}</span>
        <span>Backend: ${scan.backend || "—"}</span>
        <span>Review: ${scan.review_reason || "—"}</span>` : "No scans yet.";
    }
    refresh(); setInterval(refresh, 1200);
  },
  machine() {
    const statusRoot = document.querySelector("#machine-status");
    const profileSelect = document.querySelector("#light-profile");
    const profileForm = document.querySelector("#light-profile-form");
    const calibrationForm = document.querySelector("#calibration-form");
    document.querySelectorAll("[data-control]").forEach(button => button.onclick = async () => {
      const action = button.dataset.control;
      const payload = (action === "move_xy" || action === "move_camera_xy") ? {
        x_mm: document.querySelector("#move-x").value,
        y_mm: document.querySelector("#move-y").value,
      } : action === "move_z" ? {
        z_mm: document.querySelector("#move-z").value,
      } : action === "lights" ? {
        status: document.querySelector("#light-status").value,
      } : action === "light_profile" ? {
        name: profileSelect.value,
      } : {};
      await json(`/api/control/${action}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      refresh();
    });
    profileForm.onsubmit = async event => {
      event.preventDefault();
      const form = new FormData(profileForm);
      await json("/api/light-profiles", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          name: form.get("name"),
          red: Number(form.get("red")),
          green: Number(form.get("green")),
          blue: Number(form.get("blue")),
        }),
      });
      profileForm.reset();
      await loadProfiles();
    };
    calibrationForm.onsubmit = async event => {
      event.preventDefault();
      const form = new FormData(calibrationForm);
      await json("/api/calibration", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          camera_offset_x_mm: Number(form.get("camera_offset_x_mm")),
          camera_offset_y_mm: Number(form.get("camera_offset_y_mm")),
          camera_offset_z_mm: Number(form.get("camera_offset_z_mm")),
          min_xy_travel_z_mm: Number(form.get("min_xy_travel_z_mm")),
          z_home_mm: Number(form.get("z_home_mm")),
          c_home_mm: Number(form.get("c_home_mm")),
          safe_z_mm: Number(form.get("safe_z_mm")),
          pick_z_mm: Number(form.get("pick_z_mm")),
          place_z_mm: Number(form.get("place_z_mm")),
          probe_enabled: calibrationForm.elements.probe_enabled.checked,
          probe_retract_z_mm: Number(form.get("probe_retract_z_mm")),
          probe_place_clearance_mm: Number(form.get("probe_place_clearance_mm")),
          probe_max_contact_z_mm: form.get("probe_max_contact_z_mm") === "" ? null : Number(form.get("probe_max_contact_z_mm")),
        }),
      });
      refresh();
    };
    async function loadProfiles() {
      const data = await json("/api/light-profiles");
      profileSelect.innerHTML = data.profiles
        .map(profile => `<option value="${profile.name}">${profile.name} (${profile.red}, ${profile.green}, ${profile.blue})</option>`)
        .join("");
    }
    async function refresh() {
      const status = await json("/api/status");
      renderRuntimeBanner(status);
      const cards = [
        ["Lifecycle", status.lifecycle],
        ["Phase", status.phase],
        ["Active command", status.active_command || "—"],
        ["Initialized", status.machine_initialized ? "Yes" : "No"],
        ["X", `${status.pose.x_mm.toFixed(2)} mm`],
        ["Y", `${status.pose.y_mm.toFixed(2)} mm`],
        ["Z", `${status.pose.z_mm.toFixed(2)} mm`],
        ["Vacuum", status.vacuum_on ? "On" : "Off"],
        ["Lights", status.lights_status],
        ["Light profile", status.lights_profile || "—"],
        ["RGB", status.lights_rgb?.length ? status.lights_rgb.join(", ") : "—"],
        ["Camera offset", `${status.calibration.camera_offset_x_mm.toFixed(2)}, ${status.calibration.camera_offset_y_mm.toFixed(2)}, ${status.calibration.camera_offset_z_mm.toFixed(2)} mm`],
        ["Min XY Z", `${status.calibration.min_xy_travel_z_mm.toFixed(2)} mm`],
        ["Homed Z/C", `${status.calibration.z_home_mm.toFixed(2)}, ${status.calibration.c_home_mm.toFixed(2)} mm`],
        ["BLTouch", status.calibration.probe_enabled ? "Enabled" : "Disabled"],
        ["Probe retract", `${status.calibration.probe_retract_z_mm.toFixed(2)} mm`],
      ];
      ["camera_offset_x_mm", "camera_offset_y_mm", "camera_offset_z_mm", "min_xy_travel_z_mm", "z_home_mm", "c_home_mm", "safe_z_mm", "pick_z_mm", "place_z_mm", "probe_retract_z_mm", "probe_place_clearance_mm", "probe_max_contact_z_mm"].forEach(name => {
        const input = calibrationForm.elements[name];
        if (document.activeElement !== input) input.value = status.calibration[name] ?? "";
      });
      calibrationForm.elements.probe_enabled.checked = Boolean(status.calibration.probe_enabled);
      statusRoot.innerHTML = cards.map(([k,v]) => `<article class="status-card"><div class="muted">${k}</div><strong>${v}</strong></article>`).join("");
    }
    loadProfiles(); refresh(); setInterval(refresh, 1200);
  },
  movement() {
    const statusRoot = document.querySelector("#movement-status");
    const statePill = document.querySelector("#movement-state");
    const message = document.querySelector("#movement-message");
    const controlPayload = action => {
      if (action === "move_xy" || action === "move_camera_xy") {
        return {
          x_mm: Number(document.querySelector("#movement-x").value),
          y_mm: Number(document.querySelector("#movement-y").value),
        };
      }
      if (action === "move_z") return {z_mm: Number(document.querySelector("#movement-z").value)};
      if (action === "move_c") return {c_mm: Number(document.querySelector("#movement-c").value)};
      return {};
    };
    async function sendControl(action, payload = controlPayload(action)) {
      try {
        const result = await json(`/api/control/${action}`, {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(payload),
        });
        message.textContent = result.message || "";
      } catch (error) {
        message.textContent = error.message;
      }
      refresh();
    }
    document.querySelectorAll("[data-control]").forEach(button => {
      button.onclick = () => sendControl(button.dataset.control);
    });
    document.querySelectorAll("[data-jog-axis]").forEach(button => {
      button.onclick = () => {
        const axis = button.dataset.jogAxis;
        const sign = Number(button.dataset.jogSign);
        if (axis === "x" || axis === "y") {
          const step = Number(document.querySelector("#xy-step").value) * sign;
          sendControl("jog_xy", axis === "x" ? {dx_mm: step, dy_mm: 0} : {dx_mm: 0, dy_mm: step});
        } else if (axis === "z") {
          const step = Number(document.querySelector("#z-step").value) * sign;
          sendControl("jog_z", {dz_mm: step});
        } else if (axis === "c") {
          const step = Number(document.querySelector("#c-step").value) * sign;
          sendControl("jog_c", {dc_mm: step});
        }
      };
    });
    document.querySelectorAll("[data-paired-zc]").forEach(button => {
      button.onclick = () => {
        const step = Number(document.querySelector("#zc-step").value) * Number(button.dataset.pairedZc);
        sendControl("jog_zc_interface", {dz_mm: step});
      };
    });
    async function refresh() {
      const status = await json("/api/status");
      renderRuntimeBanner(status);
      statePill.textContent = status.lifecycle;
      const c = Number(status.pose.c_mm || 0);
      const z = Number(status.pose.z_mm || 0);
      statusRoot.innerHTML = [
        ["Initialized", status.machine_initialized ? "Yes" : "No"],
        ["Runtime", status.runtime_target === "hardware_serial" ? "LIVE HARDWARE" : "SIM BACKED"],
        ["X", `${status.pose.x_mm.toFixed(2)} mm`],
        ["Y", `${status.pose.y_mm.toFixed(2)} mm`],
        ["Z", `${z.toFixed(2)} mm`],
        ["C", `${c.toFixed(2)} mm`],
        ["End effector C", `${c.toFixed(2)} mm`],
        ["Vacuum", status.vacuum_on ? "On" : "Off"],
        ["Min XY Z", `${status.calibration.min_xy_travel_z_mm.toFixed(2)} mm`],
        ["Command", status.active_command || "--"],
      ].map(([k,v]) => `<article class="status-card"><div class="muted">${k}</div><strong>${v}</strong></article>`).join("");
    }
    refresh(); setInterval(refresh, 1200);
  },
  recognition() {
    const query = document.querySelector("#card-query");
    const validation = document.querySelector("#card-validation");
    const form = document.querySelector("#recognition-form");
    const result = document.querySelector("#recognition-result");
    query.oninput = async () => {
      const data = await json(`/api/card/validate?q=${encodeURIComponent(query.value)}`);
      validation.innerHTML = data.valid
        ? `<strong>Valid card:</strong> ${data.match.name}`
        : data.suggestions.length
          ? `No exact match. Suggestions: ${data.suggestions.join(", ")}`
          : "No exact match.";
    };
    form.onsubmit = async event => {
      event.preventDefault();
      const data = new FormData(form);
      ["prefer_visual_small_pool","use_tracked_pool","track_result"].forEach(name => {
        data.set(name, form.elements[name].checked ? "true" : "false");
      });
      result.textContent = "Recognizing…";
      const response = await fetch("/api/recognition/run", {method:"POST", body:data});
      const body = await response.json();
      result.textContent = body.ok ? pretty(body.result) : body.message;
    };
  },
  runs() {
    const root = document.querySelector("#runs-table");
    (async () => {
      const data = await json("/api/runs");
      root.innerHTML = `<table><thead><tr><th>Run</th><th>Status</th><th>Mode</th><th>Scenario</th><th>Started</th><th>Moves</th></tr></thead><tbody>${
        data.runs.map(run => `<tr>
          <td>${run.run_id}</td>
          <td>${run.status}</td>
          <td>${run.mode}</td>
          <td>${run.scenario_name || "—"}</td>
          <td>${run.started_at}</td>
          <td>${run.metrics?.move_count ?? "—"}</td>
        </tr>`).join("")
      }</tbody></table>`;
    })();
  },
  system() {
    const details = document.querySelector("#system-details");
    const pill = document.querySelector("#update-pill");
    const message = document.querySelector("#system-message");
    const raw = document.querySelector("#system-raw");
    const checkButton = document.querySelector("#check-update");
    const updateButton = document.querySelector("#apply-update");
    const serialPill = document.querySelector("#serial-pill");
    const serialPort = document.querySelector("#serial-port");
    const serialBaud = document.querySelector("#serial-baud");
    const serialConnect = document.querySelector("#serial-connect");
    const serialDisconnect = document.querySelector("#serial-disconnect");
    const serialRefresh = document.querySelector("#serial-refresh");
    const serialMessage = document.querySelector("#serial-message");
    const serialForm = document.querySelector("#serial-command-form");
    const serialCommand = document.querySelector("#serial-command");
    const serialResponse = document.querySelector("#serial-response");
    const endstopRefresh = document.querySelector("#endstop-refresh");
    const endstopState = document.querySelector("#endstop-state");
    const bltouchPill = document.querySelector("#bltouch-pill");
    const bltouchMessage = document.querySelector("#bltouch-message");
    const bltouchResponse = document.querySelector("#bltouch-response");
    const bltouchProbe = document.querySelector("#bltouch-probe");
    const bltouchState = document.querySelector("#bltouch-state");
    const render = data => {
      pill.textContent = data.update_available ? "Update available" : "Current";
      pill.className = data.update_available ? "pill warn-pill" : "pill good-pill";
      updateButton.disabled = !data.can_update;
      details.innerHTML = [
        ["Version", data.version],
        ["Branch", data.current_branch || "detached"],
        ["Current SHA", data.current_sha || "--"],
        ["Main SHA", data.remote_sha || "--"],
        ["Behind main", data.commits_behind],
        ["Ahead of main", data.commits_ahead],
        ["Local changes", data.dirty ? "Yes" : "No"],
      ].map(([k,v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
      message.textContent = data.restart_required ? "Update applied. Restart required." : (data.message || "");
      raw.textContent = pretty(data);
    };
    async function refresh(refreshRemote = false) {
      message.textContent = refreshRemote ? "Checking origin/main..." : "Loading system state...";
      render(await json(`/api/system${refreshRemote ? "?refresh=true" : ""}`));
    }
    checkButton.onclick = () => refresh(true);
    updateButton.onclick = async () => {
      updateButton.disabled = true;
      message.textContent = "Updating from origin/main...";
      try {
        render(await json("/api/system/update", {method: "POST"}));
      } catch (error) {
        message.textContent = error.message;
        render(await json("/api/system"));
      }
    };
    function renderSerial(data) {
      const status = data.status || data;
      serialPill.textContent = status.connected ? `Connected ${status.port}` : "Disconnected";
      serialPill.className = status.connected ? "pill good-pill" : "pill warn-pill";
      serialConnect.disabled = Boolean(status.connected);
      serialDisconnect.disabled = !status.connected;
      if (data.ports) {
        const selected = status.port || serialPort.value;
        serialPort.innerHTML = data.ports.length
          ? data.ports.map(port => `<option value="${port.device}">${port.device} - ${port.description || "Serial port"}</option>`).join("")
          : `<option value="">No ports found</option>`;
        if (selected) serialPort.value = selected;
      }
      serialBaud.value = status.baud_rate || serialBaud.value || 115200;
      serialMessage.textContent = data.message || data.auto?.message || status.last_error || "";
      serialResponse.textContent = status.last_response?.length ? status.last_response.join("\n") : serialResponse.textContent;
      renderEndstops(status.last_endstops || {});
    }
    function renderEndstops(endstops) {
      const names = Object.keys(endstops).sort();
      endstopState.innerHTML = names.length
        ? names.map(name => {
          const state = endstops[name];
          const cls = state === "triggered" ? "warn-pill" : "good-pill";
          return `<article class="status-card"><div class="muted">${name}</div><strong class="pill ${cls}">${state}</strong></article>`;
        }).join("")
        : `<article class="status-card"><div class="muted">M119</div><strong>No endstop data</strong></article>`;
    }
    async function refreshSerial(auto = false) {
      serialMessage.textContent = auto ? "Looking for controller..." : "Refreshing ports...";
      renderSerial(await json(`/api/serial/ports${auto ? "?auto=true" : ""}`));
    }
    async function refreshEndstops() {
      try {
        const data = await json("/api/serial/endstops");
        renderSerial(data);
        renderEndstops(data.endstops || {});
        if (data.endstops?.z_probe) {
          bltouchPill.textContent = `z_probe ${data.endstops.z_probe}`;
          bltouchPill.className = data.endstops.z_probe === "triggered" ? "pill warn-pill" : "pill good-pill";
        }
      } catch (error) {
        serialMessage.textContent = error.message;
      }
    }
    async function sendBltouch(action) {
      bltouchMessage.textContent = `Sending ${action.replace("_", " ")}...`;
      try {
        const result = await json(`/api/serial/bltouch/${action}`, {method:"POST"});
        bltouchMessage.textContent = result.message || "";
        bltouchResponse.textContent = result.response.join("\n");
        renderSerial(result);
        if (action !== "probe") refreshEndstops();
      } catch (error) {
        bltouchMessage.textContent = error.message;
      }
    }
    serialRefresh.onclick = () => refreshSerial(false);
    serialConnect.onclick = async () => {
      try {
        renderSerial(await json("/api/serial/connect", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({port: serialPort.value, baud_rate: Number(serialBaud.value || 115200)}),
        }));
        refreshEndstops();
      } catch (error) {
        serialMessage.textContent = error.message;
        refreshSerial(false);
      }
    };
    serialDisconnect.onclick = async () => {
      renderSerial(await json("/api/serial/disconnect", {method:"POST"}));
    };
    serialForm.onsubmit = async event => {
      event.preventDefault();
      try {
        const result = await json("/api/serial/send", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({command: serialCommand.value}),
        });
        serialResponse.textContent = result.response.join("\n");
        renderSerial(result);
      } catch (error) {
        serialMessage.textContent = error.message;
      }
    };
    endstopRefresh.onclick = refreshEndstops;
    document.querySelectorAll("[data-bltouch]").forEach(button => {
      button.onclick = () => sendBltouch(button.dataset.bltouch);
    });
    bltouchProbe.onclick = () => {
      if (confirm("Run single probe G30 at the current XY position?")) sendBltouch("probe");
    };
    bltouchState.onclick = refreshEndstops;
    refresh(true);
    refreshSerial(true).then(refreshEndstops);
    setInterval(async () => {
      try {
        const status = await json("/api/status");
        renderRuntimeBanner(status);
        if (status.serial_board?.connected) refreshEndstops();
      } catch (error) {
      }
    }, 2000);
  },
  about() {
    const root = document.querySelector("#capability-grid");
    (async () => {
      const data = await json("/api/capabilities");
      root.innerHTML = data.capabilities.map(item => `
        <article class="capability-card">
          <p class="eyebrow status-${item.status}">${item.status}</p>
          <h3>${item.name}</h3>
          <p class="muted">${item.detail}</p>
        </article>`).join("");
    })();
  },
};
