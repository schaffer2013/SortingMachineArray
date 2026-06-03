const json = async (url, options = {}) => {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || "Request failed");
  return body;
};
const pretty = value => JSON.stringify(value, null, 2);

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
          safe_z_mm: Number(form.get("safe_z_mm")),
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
      const cards = [
        ["Lifecycle", status.lifecycle],
        ["Phase", status.phase],
        ["Active command", status.active_command || "—"],
        ["X", `${status.pose.x_mm.toFixed(2)} mm`],
        ["Y", `${status.pose.y_mm.toFixed(2)} mm`],
        ["Z", `${status.pose.z_mm.toFixed(2)} mm`],
        ["Vacuum", status.vacuum_on ? "On" : "Off"],
        ["Lights", status.lights_status],
        ["Light profile", status.lights_profile || "—"],
        ["RGB", status.lights_rgb?.length ? status.lights_rgb.join(", ") : "—"],
        ["Camera offset", `${status.calibration.camera_offset_x_mm.toFixed(2)}, ${status.calibration.camera_offset_y_mm.toFixed(2)}, ${status.calibration.camera_offset_z_mm.toFixed(2)} mm`],
        ["Min XY Z", `${status.calibration.min_xy_travel_z_mm.toFixed(2)} mm`],
      ];
      ["camera_offset_x_mm", "camera_offset_y_mm", "camera_offset_z_mm", "min_xy_travel_z_mm", "safe_z_mm"].forEach(name => {
        const input = calibrationForm.elements[name];
        if (document.activeElement !== input) input.value = status.calibration[name];
      });
      statusRoot.innerHTML = cards.map(([k,v]) => `<article class="status-card"><div class="muted">${k}</div><strong>${v}</strong></article>`).join("");
    }
    loadProfiles(); refresh(); setInterval(refresh, 1200);
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
