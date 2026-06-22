const json = async (url, options = {}) => {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || "Request failed");
  return body;
};
const pretty = value => JSON.stringify(value, null, 2);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "\"": "&quot;",
  "'": "&#39;",
}[character]));
const getTheme = () => localStorage.getItem("sorter-theme") || "light";
const setTheme = theme => {
  const normalized = theme === "light" ? "light" : "dark";
  localStorage.setItem("sorter-theme", normalized);
  document.documentElement.dataset.theme = normalized;
  return normalized;
};
setTheme(getTheme());
const renderRuntimeBanner = status => {
  const banner = document.querySelector("#runtime-banner");
  if (!banner || !status) return;
  const faulted = Boolean(status.serial_board?.controller_fault);
  const serialLive = isVerifiedSerialController(status);
  const directHardware = status.runtime_target === "hardware_direct";
  const simulation = status.runtime_target === "simulation";
  banner.className = (serialLive || directHardware) && !faulted ? "runtime-banner live" : "runtime-banner sim";
  banner.textContent = faulted
    ? "CONTROLLER FAULT: reset or power-cycle controller"
    : serialLive
    ? `LIVE HARDWARE: ${status.serial_board?.port}`
    : directHardware
      ? "HARDWARE RUNTIME: direct Pi adapters"
    : simulation
      ? "SIMULATION"
      : "HARDWARE NOT CONNECTED";
};
const refreshRuntimeBanner = async () => {
  try {
    let status = await json("/api/status");
    if (status.runtime_mode === "hardware" && status.serial_board?.session_open && !status.serial_board?.busy) {
      try {
        await json("/api/serial/heartbeat", {method:"POST"});
        status = await json("/api/status");
      } catch (error) {
        status = await json("/api/status");
      }
    }
    renderRuntimeBanner(status);
  } catch (error) {
  }
};
refreshRuntimeBanner();
setInterval(refreshRuntimeBanner, 2000);
const isHardwareMode = status => status.runtime_mode === "hardware";
const isSimulationMode = status => status.runtime_mode === "simulation";
const isHardwareLive = status => status.runtime_target === "hardware_serial" || status.runtime_target === "hardware_direct";
const isVerifiedSerialController = status => status.runtime_target === "hardware_serial" && Boolean(status.serial_board?.connected);
const controllerStateText = status => {
  if (status.serial_board?.controller_fault) return status.serial_board?.last_error || "Faulted; reset controller";
  return status.serial_board?.connection_state || "--";
};
const setButtonsDisabled = (root, selector, disabled) => {
  root.querySelectorAll(selector).forEach(button => button.disabled = disabled);
};
const clampChannel = value => Math.max(0, Math.min(255, Number(value) || 0));
const rgbToHex = ([red, green, blue]) =>
  `#${[red, green, blue].map(value => clampChannel(value).toString(16).padStart(2, "0")).join("")}`;
const hexToRgb = hex => {
  const clean = String(hex || "#000000").replace("#", "").padEnd(6, "0").slice(0, 6);
  return [0, 2, 4].map(offset => parseInt(clean.slice(offset, offset + 2), 16) || 0);
};
const GCODE_COMMAND_TITLES = {
  G0: "Linear Move",
  G1: "Linear Move",
  G2: "Arc or Circle Move",
  G3: "Arc or Circle Move",
  G4: "Dwell",
  G10: "Retract",
  G11: "Recover",
  G20: "Inch Units",
  G21: "Millimeter Units",
  G28: "Auto Home",
  G29: "Bed Leveling",
  G30: "Single Z-Probe",
  G90: "Absolute Positioning",
  G91: "Relative Positioning",
  G92: "Set Position",
  M17: "Enable Steppers",
  M18: "Disable steppers",
  M84: "Disable steppers",
  M92: "Set Axis Steps-per-unit",
  M111: "Debug Level",
  M112: "Full Shutdown",
  M114: "Get Current Position",
  M115: "Firmware Info",
  M118: "Serial print",
  M119: "Endstop States",
  M120: "Enable Endstops",
  M121: "Disable Endstops",
  M122: "TMC Debugging",
  M150: "Set RGB(W) Color",
  M211: "Software Endstops",
  M280: "Servo Position",
  M400: "Finish Moves",
  M401: "Deploy Probe",
  M402: "Stow Probe",
  M410: "Quickstop",
  M500: "Save Settings",
  M501: "Restore Settings",
  M502: "Factory Reset",
  M503: "Report Settings",
  M906: "Stepper Motor Current",
  M914: "TMC Bump Sensitivity",
  M999: "STOP Restart",
};
const commandTitle = command => {
  const code = String(command || "").trim().split(/\s+/)[0]?.toUpperCase();
  return GCODE_COMMAND_TITLES[code] || "";
};
const SERIAL_LOG_PAGE_SIZE = 25;
const serialLogPages = {command: 0, poll: 0};
const renderSerialLog = (root, entries, emptyText, logKey) => {
  const newestFirst = [...entries].reverse();
  const totalPages = Math.max(1, Math.ceil(newestFirst.length / SERIAL_LOG_PAGE_SIZE));
  serialLogPages[logKey] = Math.min(serialLogPages[logKey] || 0, totalPages - 1);
  const pageIndex = serialLogPages[logKey];
  const pageEntries = newestFirst.slice(
    pageIndex * SERIAL_LOG_PAGE_SIZE,
    (pageIndex + 1) * SERIAL_LOG_PAGE_SIZE,
  );
  const rows = pageEntries.map(entry => {
        const response = entry.response?.length ? entry.response.join("\n") : "(no immediate response)";
        const error = entry.error ? `\nERROR: ${entry.error}` : "";
        const title = commandTitle(entry.command);
        return `
          <details class="serial-log-entry">
            <summary>
              <span>${escapeHtml(entry.sent_at)}</span>
              <strong class="${entry.ok ? "status-ready" : "status-partial"}">${entry.ok ? "OK" : "ERR"}</strong>
              <code>${escapeHtml(entry.command)}</code>
              <span class="serial-command-title">${escapeHtml(title)}</span>
            </summary>
            <pre>${escapeHtml(`${response}${error}`)}</pre>
          </details>
        `;
      }).join("");
  root.innerHTML = entries.length
    ? `
        <div class="serial-log-pager">
          <button class="secondary" type="button" data-serial-log="${logKey}" data-page-delta="-1" ${pageIndex === 0 ? "disabled" : ""}>Previous</button>
          <span class="muted">Page ${pageIndex + 1} of ${totalPages}</span>
          <button class="secondary" type="button" data-serial-log="${logKey}" data-page-delta="1" ${pageIndex >= totalPages - 1 ? "disabled" : ""}>Next</button>
        </div>
        <div class="serial-log-page">${rows}</div>
      `
    : `<p class="muted">${escapeHtml(emptyText)}</p>`;
  root.querySelectorAll("[data-page-delta]").forEach(button => {
    button.onclick = () => {
      serialLogPages[logKey] = Math.max(0, Math.min(totalPages - 1, pageIndex + Number(button.dataset.pageDelta)));
      renderSerialLog(root, entries, emptyText, logKey);
    };
  });
};

window.SorterPages = {
  camera() {
    const feed = document.querySelector("#camera-live-feed");
    const refreshButton = document.querySelector("#camera-refresh");
    const statusRoot = document.querySelector("#camera-move-status");
    const statePill = document.querySelector("#camera-move-state");
    const message = document.querySelector("#camera-move-message");
    const controlPayload = action => {
      if (action === "move_xy" || action === "move_camera_xy") {
        return {
          x_mm: Number(document.querySelector("#camera-move-x").value),
          y_mm: Number(document.querySelector("#camera-move-y").value),
        };
      }
      if (action === "move_z") return {z_mm: Number(document.querySelector("#camera-move-z").value)};
      if (action === "move_c") return {c_mm: Number(document.querySelector("#camera-move-c").value)};
      return {};
    };
    async function sendControl(action, payload = controlPayload(action), sourceButton = null) {
      if (sourceButton) sourceButton.disabled = true;
      message.textContent = `Sending ${action.replaceAll("_", " ")}...`;
      try {
        const result = await json(`/api/control/${action}`, {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(payload),
        });
        message.textContent = result.message || "";
      } catch (error) {
        message.textContent = error.message;
      } finally {
        if (sourceButton) sourceButton.disabled = false;
        refresh();
      }
    }
    refreshButton.onclick = () => {
      feed.src = `/camera/stream?t=${Date.now()}`;
    };
    document.querySelectorAll("[data-camera-control]").forEach(button => {
      button.onclick = () => sendControl(button.dataset.cameraControl, controlPayload(button.dataset.cameraControl), button);
    });
    document.querySelectorAll("[data-camera-jog-axis]").forEach(button => {
      button.onclick = () => {
        const axis = button.dataset.cameraJogAxis;
        const sign = Number(button.dataset.cameraJogSign);
        if (axis === "x" || axis === "y") {
          const step = Number(document.querySelector("#camera-xy-step").value) * sign;
          sendControl("jog_xy", axis === "x" ? {dx_mm: step, dy_mm: 0} : {dx_mm: 0, dy_mm: step}, button);
        } else if (axis === "z") {
          const step = Number(document.querySelector("#camera-z-step").value) * sign;
          sendControl("jog_z", {dz_mm: step}, button);
        } else if (axis === "c") {
          const step = Number(document.querySelector("#camera-c-step").value) * sign;
          sendControl("jog_c", {dc_mm: step}, button);
        }
      };
    });
    async function refresh() {
      const status = await json("/api/status");
      renderRuntimeBanner(status);
      const hardwareMode = isHardwareMode(status);
      const hardwareLive = isHardwareLive(status);
      const controllerFault = Boolean(status.serial_board?.controller_fault);
      statePill.textContent = controllerFault
        ? "CONTROLLER FAULT"
        : hardwareLive
          ? "LIVE HARDWARE"
          : isSimulationMode(status) ? "SIMULATION" : "HARDWARE NOT CONNECTED";
      statePill.className = hardwareLive && !controllerFault ? "pill good-pill" : "pill warn-pill";
      setButtonsDisabled(document, "[data-camera-control], [data-camera-jog-axis]", hardwareMode && (!hardwareLive || controllerFault));
      statusRoot.innerHTML = [
        ["X", `${Number(status.pose.x_mm || 0).toFixed(2)} mm`],
        ["Y", `${Number(status.pose.y_mm || 0).toFixed(2)} mm`],
        ["Z", `${Number(status.pose.z_mm || 0).toFixed(2)} mm`],
        ["C", `${Number(status.pose.c_mm || 0).toFixed(2)} mm`],
        ["Controller", controllerStateText(status)],
        ["Command", status.active_command || "--"],
      ].map(([k,v]) => `<article class="status-card"><div class="muted">${k}</div><strong>${v}</strong></article>`).join("");
    }
    refresh(); setInterval(refresh, 1200);
  },
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
    const runtimePill = document.querySelector("#machine-runtime-pill");
    const profileSelect = document.querySelector("#light-profile");
    const profileForm = document.querySelector("#light-profile-form");
    const calibrationForm = document.querySelector("#calibration-form");
    const pixelGrid = document.querySelector("#pixel-grid");
    const pixelEditorPill = document.querySelector("#pixel-editor-pill");
    const pixelIndex = document.querySelector("#pixel-index");
    const pixelColor = document.querySelector("#pixel-color");
    const pixelCopyPreview = document.querySelector("#pixel-copy-preview");
    const pixelRed = document.querySelector("#pixel-red");
    const pixelGreen = document.querySelector("#pixel-green");
    const pixelBlue = document.querySelector("#pixel-blue");
    const pixelCopy = document.querySelector("#pixel-copy");
    const pixelPaste = document.querySelector("#pixel-paste");
    const pixelFill = document.querySelector("#pixel-fill");
    const pixelClear = document.querySelector("#pixel-clear");
    const pixelApply = document.querySelector("#pixel-apply");
    const pixelProfile = document.querySelector("#pixel-profile");
    const pixelProfileName = document.querySelector("#pixel-profile-name");
    const pixelLoadProfile = document.querySelector("#pixel-load-profile");
    const pixelDeleteProfile = document.querySelector("#pixel-delete-profile");
    const pixelSaveProfile = document.querySelector("#pixel-save-profile");
    const pixelMessage = document.querySelector("#pixel-message");
    const pixels = Array.from({length: 16}, () => [0, 0, 32]);
    let neopixelProfiles = [];
    let selectedPixel = 0;
    let selectedPixels = new Set([0]);
    let copiedPixel = [0, 0, 32];
    document.querySelectorAll("[data-control]").forEach(button => button.onclick = async () => {
      const action = button.dataset.control;
      if (action === "light_profile") {
        try {
          await applySelectedLightProfile();
        } catch (error) {
          pixelMessage.textContent = error.message;
          statusRoot.innerHTML = `<article class="status-card"><div class="muted">Control error</div><strong>${error.message}</strong></article>`;
        }
        refresh();
        return;
      }
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
      try {
        await json(`/api/control/${action}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      } catch (error) {
        statusRoot.innerHTML = `<article class="status-card"><div class="muted">Control error</div><strong>${error.message}</strong></article>`;
      }
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
      const data = await json("/api/neopixel/profile-options");
      neopixelProfiles = data.profiles || [];
      const options = neopixelProfiles.length
        ? neopixelProfiles.map(profile => `<option value="${profile.kind}:${profile.name}">${profileLabel(profile)}</option>`).join("")
        : `<option value="">No profiles saved</option>`;
      profileSelect.innerHTML = options;
      pixelProfile.innerHTML = options;
    }
    function profileLabel(profile) {
      if (profile.kind === "solid") {
        return `${profile.name} - solid (${profile.red}, ${profile.green}, ${profile.blue})`;
      }
      return `${profile.name} - 16 pixels`;
    }
    function selectedProfile(select) {
      const [kind, ...nameParts] = String(select.value || "").split(":");
      const name = nameParts.join(":");
      return neopixelProfiles.find(item => item.kind === kind && item.name === name);
    }
    async function applySelectedLightProfile() {
      const profile = selectedProfile(profileSelect);
      if (!profile) return;
      if (profile.kind === "pixel") {
        await json("/api/neopixel/display", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({pixels: profile.pixels}),
        });
        pixelMessage.textContent = `Applied ${profile.name}`;
        return;
      }
      await json("/api/control/light_profile", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({name: profile.name}),
      });
    }
    function renderPixels() {
      pixelGrid.innerHTML = pixels.map((pixel, index) => `
        <button
          type="button"
          class="pixel-button${selectedPixels.has(index) ? " selected" : ""}${index === selectedPixel ? " primary" : ""}"
          data-pixel-index="${index}"
          style="background:${rgbToHex(pixel)}; --angle:${index * 22.5}deg"
          title="LED ${index}">
          ${index}
        </button>`).join("");
      pixelGrid.querySelectorAll("[data-pixel-index]").forEach(button => {
        button.onclick = event => selectPixel(Number(button.dataset.pixelIndex), event);
      });
      pixelEditorPill.textContent = selectedPixels.size === 1 ? `LED ${selectedPixel}` : `${selectedPixels.size} LEDs`;
      pixelCopy.disabled = selectedPixels.size !== 1;
    }
    function syncPixelInputs() {
      const pixel = pixels[selectedPixel];
      pixelIndex.value = selectedPixel;
      pixelColor.value = rgbToHex(pixel);
      pixelRed.value = pixel[0];
      pixelGreen.value = pixel[1];
      pixelBlue.value = pixel[2];
      pixelCopyPreview.value = rgbToHex(copiedPixel);
    }
    function selectPixel(index, event = null) {
      selectedPixel = Math.max(0, Math.min(15, Number(index) || 0));
      if (event?.ctrlKey || event?.metaKey || event?.shiftKey) {
        if (selectedPixels.has(selectedPixel) && selectedPixels.size > 1) {
          selectedPixels.delete(selectedPixel);
        } else {
          selectedPixels.add(selectedPixel);
        }
      } else {
        selectedPixels = new Set([selectedPixel]);
      }
      syncPixelInputs();
      renderPixels();
    }
    function setSelectedPixel(rgb) {
      const color = rgb.map(clampChannel);
      selectedPixels.forEach(index => pixels[index] = [...color]);
      syncPixelInputs();
      renderPixels();
    }
    pixelIndex.oninput = () => selectPixel(pixelIndex.value);
    pixelColor.oninput = () => setSelectedPixel(hexToRgb(pixelColor.value));
    [pixelRed, pixelGreen, pixelBlue].forEach(input => {
      input.oninput = () => setSelectedPixel([pixelRed.value, pixelGreen.value, pixelBlue.value]);
    });
    pixelCopy.onclick = () => {
      if (selectedPixels.size !== 1) {
        pixelMessage.textContent = "Select exactly one LED to copy";
        return;
      }
      copiedPixel = [...pixels[selectedPixel]];
      syncPixelInputs();
      pixelMessage.textContent = `Copied LED ${selectedPixel}`;
    };
    pixelPaste.onclick = () => {
      selectedPixels.forEach(index => pixels[index] = [...copiedPixel]);
      syncPixelInputs();
      renderPixels();
      pixelMessage.textContent = selectedPixels.size === 1
        ? `Pasted to LED ${selectedPixel}`
        : `Pasted to ${selectedPixels.size} LEDs`;
    };
    pixelFill.onclick = () => {
      const color = [...pixels[selectedPixel]];
      pixels.forEach((_, index) => pixels[index] = [...color]);
      renderPixels();
      syncPixelInputs();
      pixelMessage.textContent = "Filled all LEDs from selected color";
    };
    pixelClear.onclick = () => {
      pixels.forEach((_, index) => pixels[index] = [0, 0, 0]);
      renderPixels();
      syncPixelInputs();
      pixelMessage.textContent = "Cleared all LEDs";
    };
    pixelApply.onclick = async () => {
      try {
        const result = await json("/api/neopixel/display", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({pixels}),
        });
        pixelMessage.textContent = result.message || "Applied";
      } catch (error) {
        pixelMessage.textContent = error.message;
      }
    };
    pixelLoadProfile.onclick = () => {
      const profile = selectedProfile(pixelProfile);
      if (!profile) {
        pixelMessage.textContent = "Choose a saved profile";
        return;
      }
      profile.pixels.forEach((pixel, index) => pixels[index] = pixel.map(clampChannel));
      selectedPixel = 0;
      selectedPixels = new Set([0]);
      renderPixels();
      syncPixelInputs();
      pixelMessage.textContent = `Loaded ${profile.name}`;
    };
    pixelDeleteProfile.onclick = async () => {
      const profile = selectedProfile(pixelProfile);
      if (!profile) {
        pixelMessage.textContent = "Choose a saved profile";
        return;
      }
      if (!confirm(`Delete ${profile.name}?`)) return;
      try {
        await json("/api/neopixel/profiles", {
          method:"DELETE",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({kind: profile.kind, name: profile.name}),
        });
        pixelMessage.textContent = `Deleted ${profile.name}`;
        await loadProfiles();
      } catch (error) {
        pixelMessage.textContent = error.message;
      }
    };
    pixelSaveProfile.onclick = async () => {
      try {
        const result = await json("/api/neopixel/profiles", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({name: pixelProfileName.value, pixels}),
        });
        pixelMessage.textContent = `Saved ${result.profile.name}`;
        pixelProfileName.value = "";
        await loadProfiles();
        pixelProfile.value = `pixel:${result.profile.name}`;
        profileSelect.value = `pixel:${result.profile.name}`;
      } catch (error) {
        pixelMessage.textContent = error.message;
      }
    };
    async function refresh() {
      const status = await json("/api/status");
      renderRuntimeBanner(status);
      const hardwareMode = isHardwareMode(status);
      const hardwareLive = isHardwareLive(status);
      runtimePill.textContent = hardwareLive ? "LIVE HARDWARE" : isSimulationMode(status) ? "SIMULATION" : "HARDWARE NOT CONNECTED";
      runtimePill.className = hardwareLive ? "pill good-pill" : "pill warn-pill";
      document.querySelectorAll("[data-control='lights'], [data-control='light_profile']").forEach(button => {
        button.disabled = hardwareMode && !hardwareLive;
      });
      document.querySelectorAll("[data-control='vacuum_on'], [data-control='vacuum_off']").forEach(button => {
        button.disabled = hardwareMode;
      });
      pixelApply.disabled = hardwareMode && !hardwareLive;
      const cards = [
        ["Lifecycle", status.lifecycle],
        ["Runtime", status.runtime_message],
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
    renderPixels(); syncPixelInputs(); loadProfiles(); refresh(); setInterval(refresh, 1200);
  },
  movement() {
    const statusRoot = document.querySelector("#movement-status");
    const statePill = document.querySelector("#movement-state");
    const message = document.querySelector("#movement-message");
    const endstopRefresh = document.querySelector("#endstop-refresh");
    const endstopState = document.querySelector("#endstop-state");
    const bltouchPill = document.querySelector("#bltouch-pill");
    const bltouchMessage = document.querySelector("#bltouch-message");
    const bltouchResponse = document.querySelector("#bltouch-response");
    const bltouchProbe = document.querySelector("#bltouch-probe");
    const bltouchState = document.querySelector("#bltouch-state");
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
    async function sendControl(action, payload = controlPayload(action), sourceButton = null) {
      if (sourceButton) sourceButton.disabled = true;
      message.textContent = `Sending ${action.replaceAll("_", " ")}...`;
      try {
        const result = await json(`/api/control/${action}`, {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(payload),
        });
        message.textContent = result.message || "";
      } catch (error) {
        message.textContent = error.message;
      } finally {
        if (sourceButton) sourceButton.disabled = false;
        refresh();
      }
    }
    document.querySelectorAll("[data-control]").forEach(button => {
      button.onclick = () => sendControl(button.dataset.control, controlPayload(button.dataset.control), button);
    });
    document.querySelectorAll("[data-jog-axis]").forEach(button => {
      button.onclick = () => {
        const axis = button.dataset.jogAxis;
        const sign = Number(button.dataset.jogSign);
        if (axis === "x" || axis === "y") {
          const step = Number(document.querySelector("#xy-step").value) * sign;
          sendControl("jog_xy", axis === "x" ? {dx_mm: step, dy_mm: 0} : {dx_mm: 0, dy_mm: step}, button);
        } else if (axis === "z") {
          const step = Number(document.querySelector("#z-step").value) * sign;
          sendControl("jog_z", {dz_mm: step}, button);
        } else if (axis === "c") {
          const step = Number(document.querySelector("#c-step").value) * sign;
          sendControl("jog_c", {dc_mm: step}, button);
        }
      };
    });
    document.querySelectorAll("[data-paired-zc]").forEach(button => {
      button.onclick = () => {
        const step = Number(document.querySelector("#zc-step").value) * Number(button.dataset.pairedZc);
        sendControl("jog_zc_interface", {dz_mm: step}, button);
      };
    });
    function renderEndstops(endstops) {
      const names = Object.keys(endstops).sort();
      endstopState.innerHTML = names.length
        ? names.map(name => {
          const state = endstops[name];
          const cls = state === "triggered" ? "warn-pill" : "good-pill";
          return `<article class="status-card"><div class="muted">${name}</div><strong class="pill ${cls}">${state}</strong></article>`;
        }).join("")
        : `<article class="status-card"><div class="muted">M119</div><strong>No live endstop data</strong></article>`;
    }
    async function refreshEndstops(auto = false) {
      try {
        const status = await json("/api/status");
        if (!isHardwareLive(status)) {
          renderEndstops(status.serial_board?.last_endstops || {});
          bltouchPill.textContent = isSimulationMode(status) ? "Simulation" : "Unavailable";
          bltouchPill.className = "pill warn-pill";
          return;
        }
        const data = await json(`/api/serial/endstops${auto ? "?poll=true" : ""}`);
        renderEndstops(data.endstops || {});
        if (data.endstops?.z_probe) {
          bltouchPill.textContent = `z_probe ${data.endstops.z_probe}`;
          bltouchPill.className = data.endstops.z_probe === "triggered" ? "pill warn-pill" : "pill good-pill";
        }
      } catch (error) {
        if (!auto) bltouchMessage.textContent = error.message;
      }
    }
    async function sendBltouch(action) {
      bltouchMessage.textContent = `Sending ${action.replace("_", " ")}...`;
      try {
        const result = await json(`/api/serial/bltouch/${action}`, {method:"POST"});
        bltouchMessage.textContent = result.message || "";
        bltouchResponse.textContent = result.response.join("\n");
        if (action !== "probe") refreshEndstops();
      } catch (error) {
        bltouchMessage.textContent = error.message;
      }
    }
    endstopRefresh.onclick = () => refreshEndstops(false);
    document.querySelectorAll("[data-bltouch]").forEach(button => {
      button.onclick = () => sendBltouch(button.dataset.bltouch);
    });
    bltouchProbe.onclick = () => {
      if (confirm("Run single probe G30 at the current XY position?")) sendBltouch("probe");
    };
    bltouchState.onclick = () => refreshEndstops(false);
    async function refresh() {
      const status = await json("/api/status");
      renderRuntimeBanner(status);
      const hardwareMode = isHardwareMode(status);
      const hardwareLive = isHardwareLive(status);
      const controllerFault = Boolean(status.serial_board?.controller_fault);
      statePill.textContent = controllerFault
        ? "CONTROLLER FAULT"
        : hardwareLive
          ? "LIVE HARDWARE"
          : isSimulationMode(status) ? "SIMULATION" : "HARDWARE NOT CONNECTED";
      statePill.className = hardwareLive && !controllerFault ? "pill good-pill" : "pill warn-pill";
      setButtonsDisabled(document, "[data-control], [data-jog-axis], [data-paired-zc]", hardwareMode && (!hardwareLive || controllerFault));
      const hardwareOnlyDisabled = !hardwareLive || controllerFault;
      endstopRefresh.disabled = hardwareOnlyDisabled;
      bltouchProbe.disabled = hardwareOnlyDisabled;
      bltouchState.disabled = hardwareOnlyDisabled;
      document.querySelectorAll("[data-bltouch]").forEach(button => button.disabled = hardwareOnlyDisabled);
      const c = Number(status.pose.c_mm || 0);
      const z = Number(status.pose.z_mm || 0);
      statusRoot.innerHTML = [
        ["Initialized", status.machine_initialized ? "Yes" : "No"],
        ["Runtime", status.runtime_message],
        ["Controller", controllerStateText(status)],
        ["X", `${status.pose.x_mm.toFixed(2)} mm`],
        ["Y", `${status.pose.y_mm.toFixed(2)} mm`],
        ["Z", `${z.toFixed(2)} mm`],
        ["C", `${c.toFixed(2)} mm`],
        ["End effector C", `${c.toFixed(2)} mm`],
        ["Vacuum", status.vacuum_on ? "On" : "Off"],
        ["Min XY Z", `${status.calibration.min_xy_travel_z_mm.toFixed(2)} mm`],
        ["Command", status.active_command || "--"],
      ].map(([k,v]) => `<article class="status-card"><div class="muted">${k}</div><strong>${v}</strong></article>`).join("");
      renderEndstops(status.serial_board?.last_endstops || {});
    }
    refresh(); setInterval(refresh, 1200); setInterval(() => refreshEndstops(true), 2500);
  },
  recognition() {
    const query = document.querySelector("#card-query");
    const validation = document.querySelector("#card-validation");
    const form = document.querySelector("#recognition-form");
    const result = document.querySelector("#recognition-result");
    const cameraFeed = document.querySelector("#recognition-camera-feed");
    const cameraRefresh = document.querySelector("#recognition-camera-refresh");
    let recognitionSource = "upload";
    cameraRefresh.onclick = () => {
      cameraFeed.src = `/camera/stream?t=${Date.now()}`;
    };
    document.querySelectorAll("[data-recognition-source]").forEach(button => {
      button.onclick = () => {
        recognitionSource = button.dataset.recognitionSource;
      };
    });
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
      data.set("source", recognitionSource);
      ["prefer_visual_small_pool","use_tracked_pool","track_result"].forEach(name => {
        data.set(name, form.elements[name].checked ? "true" : "false");
      });
      result.textContent = recognitionSource === "camera" ? "Capturing live frame..." : "Recognizing...";
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
    const runtimeMode = document.querySelector("#runtime-mode");
    const runtimeApply = document.querySelector("#runtime-apply");
    const runtimeMessage = document.querySelector("#runtime-message");
    const themeMode = document.querySelector("#theme-mode");
    const themeApply = document.querySelector("#theme-apply");
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
    const serialCommandLog = document.querySelector("#serial-command-log");
    const serialPollLog = document.querySelector("#serial-poll-log");
    let serialOperationActive = false;
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
    async function refreshRuntime() {
      const data = await json("/api/runtime");
      runtimeMode.value = data.runtime_mode;
      themeMode.value = getTheme();
      renderRuntimeBanner(data.status);
      runtimeMessage.textContent = data.status.runtime_message;
    }
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
    runtimeApply.onclick = async () => {
      try {
        const result = await json("/api/runtime", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({mode: runtimeMode.value}),
        });
        runtimeMessage.textContent = result.status.runtime_message;
        renderRuntimeBanner(result.status);
      } catch (error) {
        runtimeMessage.textContent = error.message;
      }
    };
    themeApply.onclick = () => {
      const selected = setTheme(themeMode.value);
      runtimeMessage.textContent = `${selected[0].toUpperCase()}${selected.slice(1)} theme selected`;
    };
    function renderSerial(data) {
      const status = data.status || data;
      const state = status.connection_state || "disconnected";
      serialPill.textContent = status.controller_fault
        ? "Controller fault"
        : status.connected
        ? `Verified ${status.port}`
        : status.session_open
          ? `${state} ${status.port || ""}`
          : state === "connecting"
            ? `Connecting ${status.port || ""}`
            : "Disconnected";
      serialPill.className = status.connected && !status.controller_fault ? "pill good-pill" : "pill warn-pill";
      const busy = Boolean(status.busy) || serialOperationActive;
      serialConnect.disabled = Boolean(status.session_open) || busy;
      serialDisconnect.disabled = !status.session_open || busy;
      serialRefresh.disabled = busy;
      serialPort.disabled = busy || Boolean(status.session_open);
      serialBaud.disabled = busy || Boolean(status.session_open);
      serialForm.querySelector("button").disabled = !status.session_open || busy;
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
      renderSerialLog(serialCommandLog, status.serial_command_log || [], "No requested serial commands sent in this session.", "command");
      renderSerialLog(serialPollLog, status.serial_poll_log || [], "No serial status polls sent in this session.", "poll");
    }
    async function withSerialOperation(messageText, operation) {
      if (serialOperationActive) return;
      serialOperationActive = true;
      let errorMessage = "";
      serialMessage.textContent = messageText;
      serialConnect.disabled = true;
      serialDisconnect.disabled = true;
      serialRefresh.disabled = true;
      serialPort.disabled = true;
      serialBaud.disabled = true;
      serialForm.querySelector("button").disabled = true;
      try {
        const result = await operation();
        renderSerial(result);
        refreshRuntime();
      } catch (error) {
        errorMessage = error.message;
      } finally {
        serialOperationActive = false;
        await refreshSerial(false);
        if (errorMessage) serialMessage.textContent = errorMessage;
      }
    }
    async function refreshSerial(auto = false) {
      if (serialOperationActive) return;
      serialMessage.textContent = auto ? "Looking for controller..." : "Refreshing ports...";
      renderSerial(await json(`/api/serial/ports${auto ? "?auto=true" : ""}`));
    }
    serialRefresh.onclick = () => refreshSerial(false);
    serialConnect.onclick = () => {
      withSerialOperation("Connecting to controller...", () => json("/api/serial/connect", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({port: serialPort.value, baud_rate: Number(serialBaud.value || 115200)}),
        }));
    };
    serialDisconnect.onclick = () => {
      withSerialOperation("Disconnecting controller...", () => json("/api/serial/disconnect", {method:"POST"}));
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
    refresh(true);
    refreshRuntime();
    refreshSerial(false);
    setInterval(async () => {
      try {
        if (!serialOperationActive) {
          const status = await json("/api/status");
          renderSerial(status.serial_board || {});
        }
      } catch (error) {
      }
    }, 2500);
    setInterval(async () => {
      try {
        const status = await json("/api/status");
        renderRuntimeBanner(status);
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
