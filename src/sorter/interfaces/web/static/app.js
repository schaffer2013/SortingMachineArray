const json = async (url, options = {}) => {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || "Request failed");
  return body;
};
const pretty = value => JSON.stringify(value, null, 2);
const logDebugEvent = (event, details = {}) => {
  const payload = JSON.stringify({event, details});
  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], {type: "application/json"});
      if (navigator.sendBeacon("/api/debug/event", blob)) return;
    }
    fetch("/api/debug/event", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: payload,
      keepalive: true,
    }).catch(() => {});
  } catch (error) {
  }
};
document.addEventListener("click", event => {
  const button = event.target.closest("button");
  if (!button) return;
  logDebugEvent("ui.button.click", {
    path: window.location.pathname,
    id: button.id || null,
    text: button.textContent.trim(),
    disabled: Boolean(button.disabled),
    dataset: {...button.dataset},
  });
}, {capture: true});
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  "\"": "&quot;",
  "'": "&#39;",
}[character]));
const isObject = value => value !== null && typeof value === "object" && !Array.isArray(value);
const nonEmptyObject = value => isObject(value) && Object.keys(value).length > 0;
const firstPresent = values => values.find(value => value !== undefined && value !== null && value !== "");
const formatConfidence = value => {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  const percent = number <= 1 ? number * 100 : number;
  return `${percent.toFixed(1)}%`;
};
const formatSeconds = value => {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return number < 1 ? `${Math.round(number * 1000)} ms` : `${number.toFixed(2)} s`;
};
const timingValue = (timings, keys) => {
  for (const key of keys) {
    if (timings[key] !== undefined && timings[key] !== null) return timings[key];
  }
  return null;
};
const recognitionTimings = result => {
  const raw = result?.debug?.raw || {};
  return firstPresent([
    nonEmptyObject(raw.timings) ? raw.timings : null,
    nonEmptyObject(raw.moss_machine?.timings) ? raw.moss_machine.timings : null,
    nonEmptyObject(raw.moss?.debug?.timings) ? raw.moss.debug.timings : null,
    nonEmptyObject(raw.moss?.timings) ? raw.moss.timings : null,
    nonEmptyObject(result?.debug?.timings) ? result.debug.timings : null,
  ]) || {};
};
const recognitionSetConfidence = (result, candidate) => {
  const setCode = candidate?.set_code;
  const comparisons = result?.debug?.raw?.set_symbol?.comparisons;
  if (Array.isArray(comparisons) && setCode) {
    const comparison = comparisons.find(item => item?.set_code === setCode);
    if (comparison?.similarity !== undefined) return comparison.similarity;
  }
  return candidate?.score;
};
const renderRecognitionSummary = (root, result) => {
  if (!root || !result) return;
  const candidate = Array.isArray(result.alternatives) ? result.alternatives[0] : null;
  const timings = recognitionTimings(result);
  const totalTime = timingValue(timings, ["total", "wall_total", "scanner_runtime"]);
  const timingDetails = [
    ["Title OCR", timingValue(timings, ["title_ocr"])],
    ["Secondary OCR", timingValue(timings, ["secondary_ocr"])],
    ["Set symbol", timingValue(timings, ["set_symbol_compare"])],
    ["Moss scan", timingValue(timings, ["scanner_runtime"])],
  ].filter(([, value]) => value !== null && value !== undefined);
  const timingDetail = timingDetails.length
    ? timingDetails.slice(0, 3).map(([label, value]) => `${label} ${formatSeconds(value)}`).join(" · ")
    : "No stage timings reported";
  root.hidden = false;
  root.innerHTML = [
    ["Name", result.card_name || result.debug?.raw?.best_name || candidate?.name || "--", `Confidence ${formatConfidence(result.confidence)}`],
    ["Set", candidate?.set_code || "--", `Confidence ${formatConfidence(recognitionSetConfidence(result, candidate))}`],
    ["Timing", formatSeconds(totalTime), timingDetail],
  ].map(([label, value, detail]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}<span class="summary-detail">${escapeHtml(detail)}</span></dd></div>`).join("");
};
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
const serialLogOpenEntries = {command: new Set(), poll: new Set()};
const serialLogEntryKey = entry => `${entry.sent_at || ""}|${entry.command || ""}|${entry.ok ? "ok" : "err"}`;
const renderSerialLog = (root, entries, emptyText, logKey) => {
  root.querySelectorAll("details.serial-log-entry").forEach(detail => {
    const key = detail.dataset.entryKey;
    if (!key) return;
    if (detail.open) serialLogOpenEntries[logKey].add(key);
    else serialLogOpenEntries[logKey].delete(key);
  });
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
        const key = serialLogEntryKey(entry);
        const isOpen = serialLogOpenEntries[logKey].has(key);
        return `
          <details class="serial-log-entry" data-entry-key="${escapeHtml(key)}" ${isOpen ? "open" : ""}>
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

const createSkewCropTool = ({feed, cropStage, cropOverlay, cropToggle, cropReset, cropPreview, cropMeta, storageKey, autoRefreshMs = 0}) => {
  const noop = {
    refreshFrame: async () => false,
    captureBlob: async () => null,
    resetCrop: () => {},
  };
  if (!feed || !cropStage || !cropOverlay || !cropPreview) return noop;
  const cropImage = new Image();
  const sourceCanvas = document.createElement("canvas");
  const sourceContext = sourceCanvas.getContext("2d", {willReadFrequently: true});
  const previewContext = cropPreview.getContext("2d");
  const polygon = cropOverlay.querySelector(".crop-polygon");
  const svg = cropOverlay.querySelector(".crop-quadrilateral");
  const lines = {
    verticalFirst: cropOverlay.querySelector('[data-crop-rule="vertical-first"]'),
    verticalSecond: cropOverlay.querySelector('[data-crop-rule="vertical-second"]'),
    horizontalFirst: cropOverlay.querySelector('[data-crop-rule="horizontal-first"]'),
    horizontalSecond: cropOverlay.querySelector('[data-crop-rule="horizontal-second"]'),
  };
  const corners = ["nw", "ne", "se", "sw"];
  const autoRefreshIntervalMs = Math.max(0, Number(autoRefreshMs) || 0);
  let enabled = true;
  let loading = false;
  let framePromise = null;
  let pointer = null;
  let frame = {width: 0, height: 0};
  const defaultCrop = {
    nw: {x: 0.28, y: 0.08},
    ne: {x: 0.72, y: 0.08},
    se: {x: 0.72, y: 0.90},
    sw: {x: 0.28, y: 0.90},
  };
  const clamp01 = value => Math.max(0, Math.min(1, Number(value) || 0));
  const normalizeCrop = value => Object.fromEntries(corners.map(corner => [corner, {
    x: clamp01(value[corner]?.x),
    y: clamp01(value[corner]?.y),
  }]));
  const cloneCrop = value => Object.fromEntries(corners.map(corner => [corner, {...value[corner]}]));
  const loadSavedCrop = () => {
    if (!storageKey) return null;
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
      return saved && corners.every(corner => isObject(saved[corner])) ? normalizeCrop(saved) : null;
    } catch (error) {
      return null;
    }
  };
  const saveCrop = () => {
    if (!storageKey) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(normalizeCrop(crop)));
    } catch (error) {
    }
  };
  let crop = loadSavedCrop() || cloneCrop(defaultCrop);
  const bounds = () => {
    const stageRect = cropStage.getBoundingClientRect();
    const feedRect = feed.getBoundingClientRect();
    const imageWidth = frame.width || feed.naturalWidth || feedRect.width;
    const imageHeight = frame.height || feed.naturalHeight || feedRect.height;
    if (!imageWidth || !imageHeight || !feedRect.width || !feedRect.height) return null;
    const imageAspect = imageWidth / imageHeight;
    const feedAspect = feedRect.width / feedRect.height;
    let width = feedRect.width;
    let height = feedRect.height;
    let left = feedRect.left - stageRect.left;
    let top = feedRect.top - stageRect.top;
    if (feedAspect > imageAspect) {
      width = height * imageAspect;
      left += (feedRect.width - width) / 2;
    } else {
      height = width / imageAspect;
      top += (feedRect.height - height) / 2;
    }
    return {left, top, width, height, imageWidth, imageHeight};
  };
  const lerp = (start, end, amount) => ({
    x: start.x + (end.x - start.x) * amount,
    y: start.y + (end.y - start.y) * amount,
  });
  const setLine = (line, start, end) => {
    if (!line) return;
    line.setAttribute("x1", start.x);
    line.setAttribute("y1", start.y);
    line.setAttribute("x2", end.x);
    line.setAttribute("y2", end.y);
  };
  const shiftedCrop = (source, dx, dy) => {
    const xs = corners.map(corner => source[corner].x);
    const ys = corners.map(corner => source[corner].y);
    const shiftX = Math.max(-Math.min(...xs), Math.min(1 - Math.max(...xs), dx));
    const shiftY = Math.max(-Math.min(...ys), Math.min(1 - Math.max(...ys), dy));
    return Object.fromEntries(corners.map(corner => [corner, {
      x: source[corner].x + shiftX,
      y: source[corner].y + shiftY,
    }]));
  };
  const pointFromEvent = event => {
    const currentBounds = bounds();
    if (!currentBounds) return null;
    const stageRect = cropStage.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - stageRect.left - currentBounds.left) / currentBounds.width)),
      y: Math.max(0, Math.min(1, (event.clientY - stageRect.top - currentBounds.top) / currentBounds.height)),
    };
  };
  const renderOverlay = () => {
    const currentBounds = bounds();
    if (!enabled || !currentBounds) {
      cropOverlay.hidden = true;
      return;
    }
    cropOverlay.hidden = false;
    crop = normalizeCrop(crop);
    cropOverlay.style.left = `${currentBounds.left}px`;
    cropOverlay.style.top = `${currentBounds.top}px`;
    cropOverlay.style.width = `${currentBounds.width}px`;
    cropOverlay.style.height = `${currentBounds.height}px`;
    svg?.setAttribute("viewBox", `0 0 ${currentBounds.width} ${currentBounds.height}`);
    const points = Object.fromEntries(corners.map(corner => [corner, {
      x: crop[corner].x * currentBounds.width,
      y: crop[corner].y * currentBounds.height,
    }]));
    polygon?.setAttribute("points", corners.map(corner => `${points[corner].x},${points[corner].y}`).join(" "));
    setLine(lines.verticalFirst, lerp(points.nw, points.ne, 1 / 3), lerp(points.sw, points.se, 1 / 3));
    setLine(lines.verticalSecond, lerp(points.nw, points.ne, 2 / 3), lerp(points.sw, points.se, 2 / 3));
    setLine(lines.horizontalFirst, lerp(points.nw, points.sw, 1 / 3), lerp(points.ne, points.se, 1 / 3));
    setLine(lines.horizontalSecond, lerp(points.nw, points.sw, 2 / 3), lerp(points.ne, points.se, 2 / 3));
    cropOverlay.querySelectorAll("[data-crop-handle]").forEach(handle => {
      const point = points[handle.dataset.cropHandle];
      handle.style.left = `${point.x}px`;
      handle.style.top = `${point.y}px`;
    });
  };
  const projectiveMapForUnitSquare = points => {
    const [topLeft, topRight, bottomRight, bottomLeft] = points;
    const dx1 = topRight.x - bottomRight.x;
    const dy1 = topRight.y - bottomRight.y;
    const dx2 = bottomLeft.x - bottomRight.x;
    const dy2 = bottomLeft.y - bottomRight.y;
    const dx3 = topLeft.x - topRight.x + bottomRight.x - bottomLeft.x;
    const dy3 = topLeft.y - topRight.y + bottomRight.y - bottomLeft.y;
    let g = 0;
    let h = 0;
    if (Math.abs(dx3) > 0.000001 || Math.abs(dy3) > 0.000001) {
      const determinant = dx1 * dy2 - dx2 * dy1;
      if (Math.abs(determinant) < 0.000001) return null;
      g = (dx3 * dy2 - dx2 * dy3) / determinant;
      h = (dx1 * dy3 - dx3 * dy1) / determinant;
    }
    return {
      a: topRight.x - topLeft.x + g * topRight.x,
      b: bottomLeft.x - topLeft.x + h * bottomLeft.x,
      c: topLeft.x,
      d: topRight.y - topLeft.y + g * topRight.y,
      e: bottomLeft.y - topLeft.y + h * bottomLeft.y,
      f: topLeft.y,
      g,
      h,
    };
  };
  const transformPoint = (matrix, x, y) => {
    const denominator = matrix.g * x + matrix.h * y + 1;
    return {
      x: (matrix.a * x + matrix.b * y + matrix.c) / denominator,
      y: (matrix.d * x + matrix.e * y + matrix.f) / denominator,
    };
  };
  const drawPreview = () => {
    if (!sourceContext || !previewContext || !frame.width || !frame.height) return false;
    sourceCanvas.width = frame.width;
    sourceCanvas.height = frame.height;
    sourceContext.drawImage(cropImage, 0, 0, frame.width, frame.height);
    const source = sourceContext.getImageData(0, 0, frame.width, frame.height);
    const output = previewContext.createImageData(cropPreview.width, cropPreview.height);
    const sourcePoints = corners.map(corner => ({
      x: crop[corner].x * (frame.width - 1),
      y: crop[corner].y * (frame.height - 1),
    }));
    const matrix = projectiveMapForUnitSquare(sourcePoints);
    if (!matrix) return false;
    for (let y = 0; y < cropPreview.height; y += 1) {
      const normalizedY = cropPreview.height > 1 ? y / (cropPreview.height - 1) : 0;
      for (let x = 0; x < cropPreview.width; x += 1) {
        const normalizedX = cropPreview.width > 1 ? x / (cropPreview.width - 1) : 0;
        const sourcePoint = transformPoint(matrix, normalizedX, normalizedY);
        const sourceX = Math.max(0, Math.min(frame.width - 1, Math.round(sourcePoint.x)));
        const sourceY = Math.max(0, Math.min(frame.height - 1, Math.round(sourcePoint.y)));
        const sourceIndex = (sourceY * frame.width + sourceX) * 4;
        const outputIndex = (y * cropPreview.width + x) * 4;
        output.data[outputIndex] = source.data[sourceIndex];
        output.data[outputIndex + 1] = source.data[sourceIndex + 1];
        output.data[outputIndex + 2] = source.data[sourceIndex + 2];
        output.data[outputIndex + 3] = source.data[sourceIndex + 3];
      }
    }
    previewContext.putImageData(output, 0, 0);
    return true;
  };
  const updatePreview = () => {
    previewContext?.clearRect(0, 0, cropPreview.width, cropPreview.height);
    if (!enabled) {
      if (cropMeta) cropMeta.textContent = "Overlay hidden";
      return;
    }
    if (!cropImage.complete || !frame.width || !frame.height) {
      if (cropMeta) cropMeta.textContent = "Loading camera frame";
      return;
    }
    const rendered = drawPreview();
    if (cropMeta) cropMeta.textContent = rendered ? `4-point crop -> ${cropPreview.width} x ${cropPreview.height}` : "Move corners apart to preview crop";
  };
  const resetCrop = () => {
    crop = cloneCrop(defaultCrop);
    saveCrop();
    renderOverlay();
    updatePreview();
  };
  const refreshFrame = async () => {
    if (!enabled) return false;
    if (loading && framePromise) return framePromise;
    loading = true;
    framePromise = new Promise(resolve => {
      cropImage.onload = () => {
        loading = false;
        frame = {width: cropImage.naturalWidth, height: cropImage.naturalHeight};
        renderOverlay();
        updatePreview();
        resolve(true);
      };
      cropImage.onerror = () => {
        loading = false;
        if (cropMeta) cropMeta.textContent = "Camera frame unavailable";
        resolve(false);
      };
      cropImage.src = `/api/camera/frame.jpg?t=${Date.now()}`;
    });
    return framePromise;
  };
  const captureBlob = async () => {
    if (!enabled) return null;
    if (!frame.width || !frame.height) {
      const loaded = await refreshFrame();
      if (!loaded) return null;
    }
    if (!drawPreview()) return null;
    return new Promise(resolve => cropPreview.toBlob(resolve, "image/png"));
  };
  cropToggle?.addEventListener("click", () => {
    enabled = !enabled;
    cropToggle.textContent = enabled ? "Hide" : "Show";
    cropToggle.setAttribute("aria-pressed", String(enabled));
    renderOverlay();
    updatePreview();
    if (enabled) refreshFrame();
  });
  cropReset?.addEventListener("click", resetCrop);
  cropOverlay.addEventListener("pointerdown", event => {
    if (!enabled) return;
    const point = pointFromEvent(event);
    if (!point) return;
    pointer = {
      id: event.pointerId,
      mode: event.target.dataset.cropHandle ? "corner" : "drag",
      handle: event.target.dataset.cropHandle || null,
      startPoint: point,
      startCrop: cloneCrop(crop),
    };
    cropOverlay.setPointerCapture(event.pointerId);
  });
  cropOverlay.addEventListener("pointermove", event => {
    if (!pointer || pointer.id !== event.pointerId) return;
    const point = pointFromEvent(event);
    if (!point) return;
    crop = pointer.mode === "drag"
      ? shiftedCrop(pointer.startCrop, point.x - pointer.startPoint.x, point.y - pointer.startPoint.y)
      : normalizeCrop({...pointer.startCrop, [pointer.handle]: {x: point.x, y: point.y}});
    renderOverlay();
    updatePreview();
  });
  cropOverlay.addEventListener("pointerup", event => {
    if (pointer?.id === event.pointerId) {
      pointer = null;
      saveCrop();
    }
  });
  cropOverlay.addEventListener("pointercancel", event => {
    if (pointer?.id === event.pointerId) {
      pointer = null;
      saveCrop();
    }
  });
  window.addEventListener("resize", () => {
    renderOverlay();
    updatePreview();
  });
  renderOverlay();
  updatePreview();
  refreshFrame();
  if (autoRefreshIntervalMs > 0) {
    setInterval(() => {
      if (enabled && !pointer && !document.hidden) refreshFrame();
    }, autoRefreshIntervalMs);
  }
  return {refreshFrame, captureBlob, resetCrop};
};

window.SorterPages = {
  camera() {
    const feed = document.querySelector("#camera-live-feed");
    const refreshButton = document.querySelector("#camera-refresh");
    const cropStage = document.querySelector("#camera-crop-stage");
    const cropOverlay = document.querySelector("#camera-crop-overlay");
    const cardDetectOverlay = document.querySelector("#camera-card-detection-overlay");
    const cardDetectButton = document.querySelector("#camera-card-detect");
    const cardDetectSummary = document.querySelector("#camera-card-detect-summary");
    const cardDetectResult = document.querySelector("#camera-card-detect-result");
    const cardTruthToggle = document.querySelector("#camera-card-truth-toggle");
    const cardTruthOverlay = document.querySelector("#camera-card-truth-overlay");
    const cardWarpPreviewStage = document.querySelector(".card-warp-preview-stage");
    const cropToggle = document.querySelector("#camera-crop-toggle");
    const cropPreview = document.querySelector("#camera-crop-preview");
    const cropMeta = document.querySelector("#camera-crop-meta");
    const statusRoot = document.querySelector("#camera-move-status");
    const statePill = document.querySelector("#camera-move-state");
    const message = document.querySelector("#camera-move-message");
    const cardAspect = 63 / 88;
    const cropImage = new Image();
    let cropEnabled = false;
    let cropFrameLoading = false;
    let cropPointer = null;
    let lastCardBackDetection = null;
    let cropFrame = {width: 0, height: 0};
    let crop = {x: 0.28, y: 0.08, width: 0.44, height: 0.82};
    const cropContext = cropPreview?.getContext("2d");
    const controlPayload = action => {
      if (action === "move_xy" || action === "move_camera_xy") {
        return {
          x_mm: Number(document.querySelector("#camera-move-x").value),
          y_mm: Number(document.querySelector("#camera-move-y").value),
          z_mm: Number(document.querySelector("#camera-move-z").value),
          coordinate_space: action === "move_camera_xy" ? "camera" : "vacuum",
        };
      }
      if (action === "move_z") return {z_mm: Number(document.querySelector("#camera-move-z").value), coordinate_space: "camera"};
      if (action === "move_c") return {c_mm: Number(document.querySelector("#camera-move-c").value)};
      return {};
    };
      const visibleImageBounds = () => {
        if (!cropStage || !feed) return null;
        const stageRect = cropStage.getBoundingClientRect();
        const feedRect = feed.getBoundingClientRect();
        const imageWidth = cropFrame.width || feed.naturalWidth || feedRect.width;
        const imageHeight = cropFrame.height || feed.naturalHeight || feedRect.height;
        if (!imageWidth || !imageHeight || !feedRect.width || !feedRect.height) return null;
        const imageAspect = imageWidth / imageHeight;
        const feedAspect = feedRect.width / feedRect.height;
        let width = feedRect.width;
        let height = feedRect.height;
        let left = feedRect.left - stageRect.left;
        let top = feedRect.top - stageRect.top;
        if (feedAspect > imageAspect) {
          width = height * imageAspect;
          left += (feedRect.width - width) / 2;
        } else {
          height = width / imageAspect;
          top += (feedRect.height - height) / 2;
        }
        return {left, top, width, height, imageWidth, imageHeight};
      };
      const renderCardDetectionOverlay = detection => {
        if (!cardDetectOverlay) return;
        const bounds = visibleImageBounds();
        const corners = detection?.corners_px;
        const box = detection?.estimated_card_bbox_px || detection?.component_bbox_px;
        if (!bounds || !detection?.found || ((!corners || corners.length !== 4) && (!box || box.length !== 4))) {
          cardDetectOverlay.hidden = true;
          return;
        }
        cardDetectOverlay.hidden = false;
        cardDetectOverlay.style.left = `${bounds.left}px`;
        cardDetectOverlay.style.top = `${bounds.top}px`;
        cardDetectOverlay.style.width = `${bounds.width}px`;
        cardDetectOverlay.style.height = `${bounds.height}px`;
        const polygonPoints = corners && corners.length === 4
          ? corners.map(([x, y]) => `${(Number(x) / bounds.imageWidth) * bounds.width},${(Number(y) / bounds.imageHeight) * bounds.height}`).join(" ")
          : (() => {
              const [left, top, right, bottom] = box.map(Number);
              return [
                `${(left / bounds.imageWidth) * bounds.width},${(top / bounds.imageHeight) * bounds.height}`,
                `${(right / bounds.imageWidth) * bounds.width},${(top / bounds.imageHeight) * bounds.height}`,
                `${(right / bounds.imageWidth) * bounds.width},${(bottom / bounds.imageHeight) * bounds.height}`,
                `${(left / bounds.imageWidth) * bounds.width},${(bottom / bounds.imageHeight) * bounds.height}`,
              ].join(" ");
            })();
        cardDetectOverlay.innerHTML = `<svg aria-hidden="true"><polygon points="${escapeHtml(polygonPoints)}"></polygon></svg>`;
      };
      const runCardBackDetection = async () => {
        if (cardDetectButton) cardDetectButton.disabled = true;
        if (cardDetectSummary) cardDetectSummary.textContent = "Detecting card back...";
        try {
          const response = await json("/api/card-back/detect", {
            method: "POST",
          });
          lastCardBackDetection = response;
          renderCardDetectionOverlay(response);
          if (cardDetectSummary) {
            cardDetectSummary.textContent = response.found
              ? `Found card back: confidence ${Number(response.confidence || 0).toFixed(3)}, rotation ${Number(response.rotation_degrees || 0).toFixed(2)} deg`
              : response.message || "No card back found";
          }
          if (cardDetectResult) cardDetectResult.textContent = JSON.stringify(response, null, 2);
          if (response.warped_image_data_url && cropContext && cropPreview) {
            const warpedImage = new Image();
            warpedImage.onload = () => {
              cropContext.clearRect(0, 0, cropPreview.width, cropPreview.height);
              cropContext.drawImage(warpedImage, 0, 0, cropPreview.width, cropPreview.height);
              if (cropMeta) cropMeta.textContent = `${response.warped_image_size?.[0] || cropPreview.width} x ${response.warped_image_size?.[1] || cropPreview.height} px warped card back`;
            };
            warpedImage.src = response.warped_image_data_url;
          }
        } catch (error) {
          if (cardDetectOverlay) cardDetectOverlay.hidden = true;
          lastCardBackDetection = null;
          if (cardDetectSummary) cardDetectSummary.textContent = error.message;
          if (cardDetectResult) cardDetectResult.textContent = JSON.stringify({error: error.message}, null, 2);
        } finally {
          if (cardDetectButton) cardDetectButton.disabled = false;
        }
      };
      const updateTruthOverlay = () => {
        const enabled = Boolean(cardTruthToggle?.checked);
        if (cardTruthOverlay) cardTruthOverlay.hidden = !enabled;
        cardWarpPreviewStage?.classList.toggle("truth-overlay-enabled", enabled);
      };
      const normalizeCrop = nextCrop => {
        const bounds = visibleImageBounds();
        const imageAspect = bounds ? bounds.imageWidth / bounds.imageHeight : 4 / 3;
        let height = Number(nextCrop.height) || 0.6;
        let width = height * cardAspect / imageAspect;
        if (nextCrop.width) {
          width = Number(nextCrop.width);
          height = width * imageAspect / cardAspect;
        }
        const minWidth = 0.08;
        const minHeight = minWidth * imageAspect / cardAspect;
        if (width < minWidth) {
          width = minWidth;
          height = minHeight;
        }
        if (width > 0.96) {
          width = 0.96;
          height = width * imageAspect / cardAspect;
        }
        if (height > 0.96) {
          height = 0.96;
          width = height * cardAspect / imageAspect;
        }
        const x = Math.max(0, Math.min(1 - width, Number(nextCrop.x) || 0));
        const y = Math.max(0, Math.min(1 - height, Number(nextCrop.y) || 0));
        return {x, y, width, height};
      };
      const initializeCrop = () => {
        const bounds = visibleImageBounds();
        const imageAspect = bounds ? bounds.imageWidth / bounds.imageHeight : 4 / 3;
        const height = 0.82;
        const width = Math.min(0.82, height * cardAspect / imageAspect);
        crop = normalizeCrop({x: (1 - width) / 2, y: (1 - height) / 2, width});
      };
      const renderCropOverlay = () => {
        if (!cropOverlay) return;
        const bounds = visibleImageBounds();
        if (!cropEnabled || !bounds) {
          cropOverlay.hidden = true;
          return;
        }
        cropOverlay.hidden = false;
        crop = normalizeCrop(crop);
        cropOverlay.style.left = `${bounds.left + crop.x * bounds.width}px`;
        cropOverlay.style.top = `${bounds.top + crop.y * bounds.height}px`;
        cropOverlay.style.width = `${crop.width * bounds.width}px`;
        cropOverlay.style.height = `${crop.height * bounds.height}px`;
      };
      const pointerToCropPoint = event => {
        const bounds = visibleImageBounds();
        if (!bounds) return null;
        const stageRect = cropStage.getBoundingClientRect();
        const x = Math.max(0, Math.min(1, (event.clientX - stageRect.left - bounds.left) / bounds.width));
        const y = Math.max(0, Math.min(1, (event.clientY - stageRect.top - bounds.top) / bounds.height));
        return {x, y, bounds};
      };
      const updateCropPreview = () => {
        if (!cropContext || !cropPreview) return;
        cropContext.clearRect(0, 0, cropPreview.width, cropPreview.height);
        if (!cropEnabled) {
          cropMeta.textContent = "Overlay hidden";
          return;
        }
        if (!cropImage.complete || !cropFrame.width || !cropFrame.height) {
          cropMeta.textContent = "Loading camera frame";
          return;
        }
        const sourceX = Math.round(crop.x * cropFrame.width);
        const sourceY = Math.round(crop.y * cropFrame.height);
        const sourceWidth = Math.round(crop.width * cropFrame.width);
        const sourceHeight = Math.round(crop.height * cropFrame.height);
        cropContext.drawImage(cropImage, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, cropPreview.width, cropPreview.height);
        cropMeta.textContent = `${sourceWidth} x ${sourceHeight} px -> ${cropPreview.width} x ${cropPreview.height}`;
      };
      const refreshCropFrame = () => {
        if (!cropEnabled || cropFrameLoading) return;
        cropFrameLoading = true;
        cropImage.src = `/api/camera/frame.jpg?t=${Date.now()}`;
      };
      cropImage.onload = () => {
        cropFrameLoading = false;
        cropFrame = {width: cropImage.naturalWidth, height: cropImage.naturalHeight};
        if (!crop.width || !crop.height) initializeCrop();
        renderCropOverlay();
        updateCropPreview();
      };
      cropImage.onerror = () => {
        cropFrameLoading = false;
        if (cropEnabled) cropMeta.textContent = "Camera frame unavailable";
      };
      cropToggle.onclick = () => {
        cropEnabled = !cropEnabled;
        cropToggle.textContent = cropEnabled ? "Hide" : "Show";
        cropToggle.setAttribute("aria-pressed", String(cropEnabled));
        if (cropEnabled) {
          initializeCrop();
          refreshCropFrame();
        }
        renderCropOverlay();
        updateCropPreview();
      };
      cropOverlay?.addEventListener("pointerdown", event => {
        if (!cropEnabled) return;
        const point = pointerToCropPoint(event);
        if (!point) return;
        cropPointer = {
          id: event.pointerId,
          mode: event.target.dataset.cropHandle ? "resize" : "drag",
          handle: event.target.dataset.cropHandle || null,
          startPoint: point,
          startCrop: {...crop},
        };
        cropOverlay.setPointerCapture(event.pointerId);
      });
      cropOverlay?.addEventListener("pointermove", event => {
        if (!cropPointer || cropPointer.id !== event.pointerId) return;
        const point = pointerToCropPoint(event);
        if (!point) return;
        if (cropPointer.mode === "drag") {
          const dx = point.x - cropPointer.startPoint.x;
          const dy = point.y - cropPointer.startPoint.y;
          crop = normalizeCrop({
            ...cropPointer.startCrop,
            x: cropPointer.startCrop.x + dx,
            y: cropPointer.startCrop.y + dy,
          });
        } else {
          const imageAspect = point.bounds.imageWidth / point.bounds.imageHeight;
          const anchorX = cropPointer.handle.includes("w")
            ? cropPointer.startCrop.x + cropPointer.startCrop.width
            : cropPointer.startCrop.x;
          const anchorY = cropPointer.handle.includes("n")
            ? cropPointer.startCrop.y + cropPointer.startCrop.height
            : cropPointer.startCrop.y;
          const pixelWidth = Math.max(
            Math.abs(point.x - anchorX) * point.bounds.imageWidth,
            Math.abs(point.y - anchorY) * point.bounds.imageHeight * cardAspect,
          );
          const width = pixelWidth / point.bounds.imageWidth;
          const height = width * imageAspect / cardAspect;
          crop = normalizeCrop({
            x: cropPointer.handle.includes("w") ? anchorX - width : anchorX,
            y: cropPointer.handle.includes("n") ? anchorY - height : anchorY,
            width,
          });
        }
        renderCropOverlay();
        updateCropPreview();
      });
      cropOverlay?.addEventListener("pointerup", event => {
        if (cropPointer?.id === event.pointerId) cropPointer = null;
      });
      cropOverlay?.addEventListener("pointercancel", event => {
        if (cropPointer?.id === event.pointerId) cropPointer = null;
      });
      window.addEventListener("resize", () => {
        renderCropOverlay();
        updateCropPreview();
        renderCardDetectionOverlay(lastCardBackDetection);
      });
      cardDetectButton?.addEventListener("click", runCardBackDetection);
      cardTruthToggle?.addEventListener("change", updateTruthOverlay);
      updateTruthOverlay();
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
      refreshCropFrame();
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
    setInterval(refreshCropFrame, 1000);
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
    const calibrationMessage = document.querySelector("#calibration-message");
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
    const optimizerRun = document.querySelector("#lighting-opt-run");
    const optimizerPill = document.querySelector("#lighting-optimizer-pill");
    const optimizerMessage = document.querySelector("#lighting-opt-message");
    const optimizerResult = document.querySelector("#lighting-opt-result");
    const pixels = Array.from({length: 16}, () => [0, 0, 32]);
    let neopixelProfiles = [];
    let selectedPixel = 0;
    let selectedPixels = new Set([0]);
    let copiedPixel = [0, 0, 32];
    let calibrationSaving = false;
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
      const saveButton = calibrationForm.querySelector("button");
      calibrationSaving = true;
      if (saveButton) saveButton.disabled = true;
      if (calibrationMessage) calibrationMessage.textContent = "Saving calibration...";
      try {
        const result = await json("/api/calibration", {
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
        const zOffset = Number(result.calibration?.camera_offset_z_mm ?? 0).toFixed(2);
        if (calibrationMessage) calibrationMessage.textContent = `${result.message || "Calibration saved."} Camera Z offset is ${zOffset} mm.`;
      } catch (error) {
        if (calibrationMessage) calibrationMessage.textContent = `Calibration save failed: ${error.message}`;
      } finally {
        calibrationSaving = false;
        if (saveButton) saveButton.disabled = false;
      }
      await refresh();
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
    optimizerRun.onclick = async () => {
      optimizerRun.disabled = true;
      optimizerPill.textContent = "Running";
      optimizerPill.className = "pill warn-pill";
      optimizerMessage.textContent = "Sweeping generated RGB candidates and scoring camera frames...";
      try {
        const result = await json("/api/lights/optimize", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({
            mode: document.querySelector("#lighting-opt-mode").value,
            max_samples: Number(document.querySelector("#lighting-opt-samples").value),
            target_brightness: Number(document.querySelector("#lighting-opt-target").value),
            settle_ms: Number(document.querySelector("#lighting-opt-settle").value),
            crop: {
              left: Number(document.querySelector("#lighting-opt-crop-left").value),
              top: Number(document.querySelector("#lighting-opt-crop-top").value),
              right: Number(document.querySelector("#lighting-opt-crop-right").value),
              bottom: Number(document.querySelector("#lighting-opt-crop-bottom").value),
            },
          }),
        });
        optimizerMessage.textContent = result.message || "Lighting optimized";
        optimizerPill.textContent = "Applied";
        optimizerPill.className = "pill good-pill";
        renderOptimizerResult(result);
        refresh();
      } catch (error) {
        optimizerMessage.textContent = error.message;
        optimizerPill.textContent = "Blocked";
        optimizerPill.className = "pill warn-pill";
      } finally {
        optimizerRun.disabled = false;
      }
    };
    function renderOptimizerResult(result) {
      const best = result.best;
      const ranked = [...(result.samples || [])].sort((a, b) => Number(b.score) - Number(a.score)).slice(0, 5);
      const bestLabel = best && result.mode === "single_led"
        ? `LED ${best.led_index}`
        : "Best RGB";
      const bestColor = best ? [best.red, best.green, best.blue] : [0, 0, 0];
      optimizerResult.innerHTML = best ? `
        <article class="status-card">
          <div class="muted">${bestLabel}</div>
          <strong><span class="color-swatch" style="background:${rgbToHex(bestColor)}"></span>${best.red}, ${best.green}, ${best.blue}</strong>
        </article>
        <article class="status-card"><div class="muted">Score</div><strong>${Number(best.score).toFixed(4)}</strong></article>
        <article class="status-card"><div class="muted">Brightness</div><strong>${Number(best.mean_brightness).toFixed(2)}</strong></article>
        <article class="status-card"><div class="muted">Contrast</div><strong>${Number(best.contrast).toFixed(2)}</strong></article>
        <article class="status-card"><div class="muted">Glare</div><strong>${Number(best.glare_fraction || 0).toFixed(4)}</strong></article>
        ${ranked.map(sample => `
          <article class="status-card">
            <div class="muted">${result.mode === "single_led" ? `LED ${sample.led_index}` : "Candidate"} score ${Number(sample.score).toFixed(4)} / glare ${Number(sample.glare_fraction || 0).toFixed(4)}</div>
            <strong><span class="color-swatch" style="background:${rgbToHex([sample.red, sample.green, sample.blue])}"></span>${sample.red}, ${sample.green}, ${sample.blue}</strong>
          </article>
        `).join("")}
      ` : `<article class="status-card"><div class="muted">Optimizer</div><strong>No samples yet</strong></article>`;
    }
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
      optimizerRun.disabled = hardwareMode && !hardwareLive;
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
      const editingCalibration = calibrationForm.contains(document.activeElement);
      if (!calibrationSaving && !editingCalibration) {
        ["camera_offset_x_mm", "camera_offset_y_mm", "camera_offset_z_mm", "min_xy_travel_z_mm", "z_home_mm", "c_home_mm", "safe_z_mm", "pick_z_mm", "place_z_mm", "probe_retract_z_mm", "probe_place_clearance_mm", "probe_max_contact_z_mm"].forEach(name => {
          const input = calibrationForm.elements[name];
          input.value = status.calibration[name] ?? "";
        });
        calibrationForm.elements.probe_enabled.checked = Boolean(status.calibration.probe_enabled);
      }
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
    const resultSummary = document.querySelector("#recognition-summary");
    const cameraFeed = document.querySelector("#recognition-camera-feed");
    const cameraRefresh = document.querySelector("#recognition-camera-refresh");
    const cropTool = createSkewCropTool({
      feed: cameraFeed,
      cropStage: document.querySelector("#recognition-crop-stage"),
      cropOverlay: document.querySelector("#recognition-crop-overlay"),
      cropToggle: document.querySelector("#recognition-crop-toggle"),
      cropReset: document.querySelector("#recognition-crop-reset"),
      cropPreview: document.querySelector("#recognition-crop-preview"),
      cropMeta: document.querySelector("#recognition-crop-meta"),
      storageKey: "sorter-recognition-card-crop-v1",
      autoRefreshMs: 1000,
    });
    let recognitionSource = "upload";
    cameraRefresh.onclick = () => {
      cameraFeed.src = `/camera/stream?t=${Date.now()}`;
      cropTool.refreshFrame();
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
      resultSummary.hidden = true;
      result.textContent = recognitionSource === "camera" ? "Capturing live frame..." : "Recognizing...";
      if (recognitionSource === "camera") {
        const cropBlob = await cropTool.captureBlob();
        if (!cropBlob) {
          result.textContent = "Camera crop unavailable";
          return;
        }
        data.set("source", "upload");
        data.set("image", cropBlob, "live-card-crop.png");
        result.textContent = "Recognizing cropped live frame...";
      }
      const response = await fetch("/api/recognition/run", {method:"POST", body:data});
      const body = await response.json();
      if (body.ok) {
        renderRecognitionSummary(resultSummary, body.result);
        result.textContent = pretty(body.result);
      } else {
        resultSummary.hidden = true;
        result.textContent = body.message;
      }
    };
  },
  cardBackTraining() {
    const modelSelect = document.querySelector("#training-model-select");
    const baseModelSelect = document.querySelector("#training-base-model");
    const modelForm = document.querySelector("#training-model-form");
    const modelPill = document.querySelector("#training-model-pill");
    const modelMessage = document.querySelector("#training-model-message");
    const countsRoot = document.querySelector("#training-counts");
    const activateModel = document.querySelector("#training-model-activate");
    const deleteModel = document.querySelector("#training-model-delete");
    const boxFromCurrent = document.querySelector("#training-box-from-current");
    const generatePlan = document.querySelector("#training-plan-generate");
    const captureSelected = document.querySelector("#training-capture-selected");
    const captureAll = document.querySelector("#training-capture-all");
    const planMessage = document.querySelector("#training-plan-message");
    const planPill = document.querySelector("#training-plan-pill");
    const planList = document.querySelector("#training-plan-list");
    const boxCanvas = document.querySelector("#training-box-canvas");
    const detectButton = document.querySelector("#training-detect");
    const tuneCanvas = document.querySelector("#training-tune-canvas");
    const tuneMessage = document.querySelector("#training-tune-message");
    const cornerOverlay = document.querySelector("#training-corner-overlay");
    const detectionMethodSelect = document.querySelector("#training-detection-method");
    const zoomInput = document.querySelector("#training-zoom");
    const cornerStepInput = document.querySelector("#training-corner-step");
    const saveLabel = document.querySelector("#training-save-label");
    const labelTrain = document.querySelector("#training-label-train");
    const labelEval = document.querySelector("#training-label-eval");
    const lastResult = document.querySelector("#training-last-result");
    const corners = ["nw", "ne", "se", "sw"];
    let summary = {models: []};
    let plan = [];
    let selectedPlanIndex = 0;
    let currentSample = null;
    let selectedCorner = "nw";
    let expectedCorners = null;
    let truthCorners = null;
    let frameImage = null;
    let truthImage = null;
    let tuneViewport = {x: 315, y: 440};
    let tunePointer = null;
    let cornerPointer = null;

    const activeModelId = () => modelSelect.value || summary.active_model_id;
    const fieldNumber = id => Number(document.querySelector(id).value);
    const selectedSplit = () => document.querySelector("#training-split").value;
    const selectedDetectionMethod = () => detectionMethodSelect?.value || "original";
    const setFieldNumber = (id, value) => { document.querySelector(id).value = Number(value).toFixed(1); };
    const cornerObjectFromArray = points => {
      if (!Array.isArray(points) || points.length < 4) return null;
      return Object.fromEntries(corners.map((corner, index) => [corner, {x: Number(points[index][0]), y: Number(points[index][1])}]));
    };
    const cloneCorners = value => value ? Object.fromEntries(corners.map(corner => [corner, {...value[corner]}])) : null;
    const cornersToArray = value => corners.map(corner => [Number(value[corner].x), Number(value[corner].y)]);
    const cardAspect = 63 / 88;
    const outputSize = () => ({width: truthImage?.naturalWidth || 630, height: truthImage?.naturalHeight || 880});
    const clampValue = (value, min, max) => Math.max(min, Math.min(max, value));
    const cornerStep = () => clampValue(Number(cornerStepInput?.value) || 1, 0.1, 100);
    const defaultCardCorners = image => {
      const height = image.height * 0.82;
      const width = Math.min(image.width * 0.82, height * cardAspect);
      const left = (image.width - width) / 2;
      const top = (image.height - height) / 2;
      return {
        nw: {x: left, y: top},
        ne: {x: left + width, y: top},
        se: {x: left + width, y: top + height},
        sw: {x: left, y: top + height},
      };
    };
    const loadImage = src => new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("Image unavailable"));
      image.src = `${src}${src.includes("?") ? "&" : "?"}t=${Date.now()}`;
    });
    loadImage("/static/card-back-truth.jpg").then(image => {
      truthImage = image;
      const size = outputSize();
      tuneViewport = {x: size.width / 2, y: size.height / 2};
      renderTuning();
    }).catch(() => {});
    const projectiveMapForUnitSquare = points => {
      const [topLeft, topRight, bottomRight, bottomLeft] = points;
      const dx1 = topRight.x - bottomRight.x;
      const dy1 = topRight.y - bottomRight.y;
      const dx2 = bottomLeft.x - bottomRight.x;
      const dy2 = bottomLeft.y - bottomRight.y;
      const dx3 = topLeft.x - topRight.x + bottomRight.x - bottomLeft.x;
      const dy3 = topLeft.y - topRight.y + bottomRight.y - bottomLeft.y;
      let g = 0;
      let h = 0;
      if (Math.abs(dx3) > 0.000001 || Math.abs(dy3) > 0.000001) {
        const determinant = dx1 * dy2 - dx2 * dy1;
        if (Math.abs(determinant) < 0.000001) return null;
        g = (dx3 * dy2 - dx2 * dy3) / determinant;
        h = (dx1 * dy3 - dx3 * dy1) / determinant;
      }
      return {
        a: topRight.x - topLeft.x + g * topRight.x,
        b: bottomLeft.x - topLeft.x + h * bottomLeft.x,
        c: topLeft.x,
        d: topRight.y - topLeft.y + g * topRight.y,
        e: bottomLeft.y - topLeft.y + h * bottomLeft.y,
        f: topLeft.y,
        g,
        h,
      };
    };
    const transformPoint = (matrix, x, y) => {
      const denominator = matrix.g * x + matrix.h * y + 1;
      return {
        x: (matrix.a * x + matrix.b * y + matrix.c) / denominator,
        y: (matrix.d * x + matrix.e * y + matrix.f) / denominator,
      };
    };
    const selectCorner = corner => {
      selectedCorner = corner;
      document.querySelectorAll("[data-training-corner]").forEach(item => item.classList.toggle("secondary", item.dataset.trainingCorner !== selectedCorner));
      renderTuning();
      tuneCanvas.focus();
    };
    const setSelectedCornerOnly = corner => {
      selectedCorner = corner;
      document.querySelectorAll("[data-training-corner]").forEach(item => item.classList.toggle("secondary", item.dataset.trainingCorner !== selectedCorner));
    };
    const moveSelectedCorner = (deltaX, deltaY) => {
      if (!truthCorners?.[selectedCorner] || !frameImage) return;
      truthCorners[selectedCorner].x = clampValue(truthCorners[selectedCorner].x + deltaX, 0, Math.max(0, frameImage.width - 1));
      truthCorners[selectedCorner].y = clampValue(truthCorners[selectedCorner].y + deltaY, 0, Math.max(0, frameImage.height - 1));
      renderTuning();
    };
    const clearTuningView = message => {
      currentSample = null;
      frameImage = null;
      expectedCorners = null;
      truthCorners = null;
      cornerPointer = null;
      tunePointer = null;
      renderTuning();
      if (message) tuneMessage.textContent = message;
    };

    async function refreshSummary() {
      summary = await json("/api/card-back-training");
      renderModels();
    }
    function renderModels() {
      const models = summary.models || [];
      const active = models.find(model => model.model_id === summary.active_model_id) || models[0] || null;
      document.querySelectorAll(".training-sample-list").forEach(root => root.remove());
      const options = models.length
        ? models.map(model => `<option value="${escapeHtml(model.model_id)}">${escapeHtml(model.name)} (${model.train_count}/${model.eval_count}/${model.staged_count})</option>`).join("")
        : `<option value="">No models yet</option>`;
      modelSelect.innerHTML = options;
      baseModelSelect.innerHTML = `<option value="">None</option>${options}`;
      if (detectionMethodSelect) {
        const selectedMethod = detectionMethodSelect.value || "original";
        detectionMethodSelect.innerHTML = [
          `<option value="original">Original</option>`,
          `<option value="opencv">OpenCV</option>`,
          ...models.map(model => `<option value="model:${escapeHtml(model.model_id)}">Model: ${escapeHtml(model.name)}</option>`),
        ].join("");
        detectionMethodSelect.value = Array.from(detectionMethodSelect.options).some(option => option.value === selectedMethod) ? selectedMethod : "original";
      }
      if (active) modelSelect.value = active.model_id;
      modelPill.textContent = active ? active.name : "No model";
      modelPill.className = active ? "pill good-pill" : "pill warn-pill";
      countsRoot.innerHTML = active ? [
        ["Train", active.train_count],
        ["Eval", active.eval_count],
        ["Staged", active.staged_count],
        ["Tuned", active.truth_count],
      ].map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join("") : `<div><dt>Dataset</dt><dd>0</dd></div>`;
      renderRecentSamples(active);
    }
    function renderRecentSamples(model) {
      const samples = model?.recent_samples || [];
      if (!samples.length) return;
      const sampleRows = samples.map(sample => `
        <div class="training-sample-row secondary">
          <button type="button" class="training-sample-load" data-sample-id="${escapeHtml(sample.sample_id)}">
            <span>${escapeHtml(sample.split)}</span>
            <strong>${escapeHtml(sample.sample_id)}</strong>
            <span>${sample.has_truth ? "tuned" : "needs tune"}</span>
          </button>
          <button type="button" class="training-sample-delete secondary" data-sample-id="${escapeHtml(sample.sample_id)}">Delete</button>
        </div>
      `).join("");
      countsRoot.insertAdjacentHTML("afterend", `<div class="training-sample-list">${sampleRows}</div>`);
      document.querySelectorAll(".training-sample-load").forEach(button => {
        button.onclick = () => loadExistingSample(model, button.dataset.sampleId);
      });
      document.querySelectorAll(".training-sample-delete").forEach(button => {
        button.onclick = () => deleteTrainingSample(model, button.dataset.sampleId);
      });
    }
    async function loadExistingSample(model, sampleId) {
      clearTuningView(`Loading ${sampleId}...`);
      const [sampleResponse, image] = await Promise.all([
        json(`/api/card-back-training/models/${model.model_id}/samples/${sampleId}`),
        loadImage(`/api/card-back-training/models/${model.model_id}/samples/${sampleId}/image.jpg`),
      ]);
      currentSample = sampleResponse.sample;
      frameImage = image;
      expectedCorners = cornerObjectFromArray(currentSample.label?.detection?.corners_px)
        || cornerObjectFromArray(currentSample.label?.expected_crop?.corners_px)
        || defaultCardCorners(image);
      truthCorners = currentSample.label?.truth_corners_px && Object.keys(currentSample.label.truth_corners_px).length
        ? cloneCorners(currentSample.label.truth_corners_px)
        : cloneCorners(expectedCorners);
      renderTuning();
      tuneMessage.textContent = expectedCorners
        ? `Loaded ${sampleId}. Drag a corner on the source image or move it with the panel controls.`
        : `Loaded ${sampleId}. No detection corners were saved for this sample.`;
    }
    async function deleteTrainingSample(model, sampleId) {
      if (!window.confirm(`Delete sample ${sampleId}?`)) return;
      const result = await json(`/api/card-back-training/models/${model.model_id}/samples/${sampleId}`, {method:"DELETE"});
      summary = result.summary;
      if (currentSample?.sample_id === sampleId) clearTuningView(`Deleted ${sampleId}`);
      renderModels();
      modelMessage.textContent = `Deleted sample ${sampleId}`;
    }
    modelForm.onsubmit = async event => {
      event.preventDefault();
      const form = new FormData(modelForm);
      try {
        const result = await json("/api/card-back-training/models", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({name: form.get("name"), base_model_id: form.get("base_model_id"), notes: form.get("notes")}),
        });
        summary = result.summary;
        modelForm.reset();
        renderModels();
        modelSelect.value = result.model.model_id;
        modelMessage.textContent = `Created ${result.model.name}`;
      } catch (error) {
        modelMessage.textContent = error.message;
      }
    };
    activateModel.onclick = async () => {
      try {
        const result = await json("/api/card-back-training/models/active", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({model_id: activeModelId()}),
        });
        summary = result.summary;
        renderModels();
        modelMessage.textContent = `Activated ${result.model.name}`;
      } catch (error) {
        modelMessage.textContent = error.message;
      }
    };
    deleteModel.onclick = async () => {
      const modelId = activeModelId();
      if (!modelId || !window.confirm(`Delete model ${modelId} and all of its samples?`)) return;
      try {
        const result = await json(`/api/card-back-training/models/${modelId}`, {method:"DELETE"});
        summary = result.summary;
        clearTuningView(`Deleted model ${modelId}`);
        renderModels();
        modelMessage.textContent = `Deleted model ${modelId}`;
      } catch (error) {
        modelMessage.textContent = error.message;
      }
    };

    function planPayload() {
      return {
        box: {
          min_x_mm: fieldNumber("#training-min-x"),
          max_x_mm: fieldNumber("#training-max-x"),
          min_y_mm: fieldNumber("#training-min-y"),
          max_y_mm: fieldNumber("#training-max-y"),
          min_z_mm: fieldNumber("#training-min-z"),
          max_z_mm: fieldNumber("#training-max-z"),
        },
        count: fieldNumber("#training-point-count"),
        seed: document.querySelector("#training-seed").value,
        light_min: fieldNumber("#training-light-min"),
        light_max: fieldNumber("#training-light-max"),
      };
    }
    boxFromCurrent.onclick = async () => {
      try {
        const status = await json("/api/status");
        const pose = status.pose || {};
        const centerX = Number(pose.x_mm);
        const centerY = Number(pose.y_mm);
        const centerZ = Number(pose.z_mm);
        if (![centerX, centerY, centerZ].every(Number.isFinite)) throw new Error("Current XYZ pose is unavailable");
        const radiusX = Math.max(0, fieldNumber("#training-box-radius-x"));
        const radiusY = Math.max(0, fieldNumber("#training-box-radius-y"));
        const radiusZ = Math.max(0, fieldNumber("#training-box-radius-z"));
        setFieldNumber("#training-min-x", centerX - radiusX);
        setFieldNumber("#training-max-x", centerX + radiusX);
        setFieldNumber("#training-min-y", centerY - radiusY);
        setFieldNumber("#training-max-y", centerY + radiusY);
        setFieldNumber("#training-min-z", centerZ - radiusZ);
        setFieldNumber("#training-max-z", centerZ + radiusZ);
        planMessage.textContent = `Box centered at X ${centerX.toFixed(1)} / Y ${centerY.toFixed(1)} / Z ${centerZ.toFixed(1)}`;
      } catch (error) {
        planMessage.textContent = error.message;
      }
    };
    generatePlan.onclick = async () => {
      try {
        const result = await json("/api/card-back-training/plan", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(planPayload()),
        });
        plan = result.plan || [];
        selectedPlanIndex = 0;
        renderPlan();
        drawBox();
        planMessage.textContent = `Generated ${plan.length} spring-spaced points`;
      } catch (error) {
        planMessage.textContent = error.message;
      }
    };
    function renderPlan() {
      planPill.textContent = `${plan.length} points`;
      planList.innerHTML = plan.length ? plan.map((entry, index) => {
        const pixel = entry.lighting?.pixels?.[0] || [0, 0, 0];
        const point = entry.point;
        return `
          <button type="button" class="training-plan-entry${index === selectedPlanIndex ? " selected" : ""}" data-plan-index="${index}">
            <span class="color-swatch" style="background:${rgbToHex(pixel)}"></span>
            <strong>#${entry.index}</strong>
            <span>X ${point.x_mm} / Y ${point.y_mm} / Z ${point.z_mm}</span>
          </button>
        `;
      }).join("") : `<p class="muted">No generated points yet.</p>`;
      planList.querySelectorAll("[data-plan-index]").forEach(button => {
        button.onclick = () => {
          selectedPlanIndex = Number(button.dataset.planIndex);
          renderPlan();
          drawBox();
        };
      });
    }
    function drawBox() {
      const context = boxCanvas.getContext("2d");
      const width = boxCanvas.width;
      const height = boxCanvas.height;
      context.clearRect(0, 0, width, height);
      context.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--code-bg").trim() || "#020617";
      context.fillRect(0, 0, width, height);
      if (!plan.length) return;
      const xs = plan.map(item => item.point.x_mm);
      const ys = plan.map(item => item.point.y_mm);
      const zs = plan.map(item => item.point.z_mm);
      const min = {x: Math.min(...xs), y: Math.min(...ys), z: Math.min(...zs)};
      const max = {x: Math.max(...xs), y: Math.max(...ys), z: Math.max(...zs)};
      const project = point => {
        const nx = (point.x_mm - min.x) / Math.max(0.001, max.x - min.x) - 0.5;
        const ny = (point.y_mm - min.y) / Math.max(0.001, max.y - min.y) - 0.5;
        const nz = (point.z_mm - min.z) / Math.max(0.001, max.z - min.z) - 0.5;
        return {x: width / 2 + nx * 430 + ny * 150, y: height / 2 + nz * -210 + ny * 90};
      };
      context.strokeStyle = "rgba(148,163,184,.35)";
      context.lineWidth = 2;
      context.strokeRect(84, 52, width - 168, height - 104);
      plan.forEach((entry, index) => {
        const point = project(entry.point);
        const radius = index === selectedPlanIndex ? 9 : 6;
        context.beginPath();
        context.arc(point.x, point.y, radius, 0, Math.PI * 2);
        context.fillStyle = index === selectedPlanIndex ? "#f59e0b" : "#38bdf8";
        context.fill();
      });
    }

    async function capturePlanEntry(entry) {
      clearTuningView(`Capturing sample ${entry.index}...`);
      const result = await json("/api/card-back-training/capture", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          model_id: activeModelId(),
          point: entry.point,
          lighting: entry.lighting,
          split: selectedSplit(),
          settle_ms: fieldNumber("#training-settle-ms"),
          execute_motion: document.querySelector("#training-execute-motion").checked,
          run_detection: true,
          detection_method: selectedDetectionMethod(),
        }),
      });
      summary = result.summary;
      currentSample = result.sample;
      const label = result.sample.label || {};
      frameImage = await loadImage(`/api/card-back-training/models/${activeModelId()}/samples/${result.sample.sample_id}/image.jpg`);
      expectedCorners = cornerObjectFromArray(label.detection?.corners_px) || defaultCardCorners(frameImage);
      truthCorners = cloneCorners(expectedCorners);
      renderModels();
      renderTuning();
      lastResult.textContent = pretty(result.sample);
      return result;
    }
    captureSelected.onclick = async () => {
      if (!plan.length) {
        planMessage.textContent = "Generate a plan first";
        return;
      }
      captureSelected.disabled = true;
      try {
        const result = await capturePlanEntry(plan[selectedPlanIndex]);
        planMessage.textContent = `Captured ${result.sample.sample_id}`;
      } catch (error) {
        planMessage.textContent = error.message;
      } finally {
        captureSelected.disabled = false;
      }
    };
    captureAll.onclick = async () => {
      if (!plan.length) return;
      captureAll.disabled = true;
      try {
        for (let index = 0; index < plan.length; index += 1) {
          selectedPlanIndex = index;
          renderPlan();
          drawBox();
          planMessage.textContent = `Capturing ${index + 1} of ${plan.length}...`;
          await capturePlanEntry(plan[index]);
        }
        planMessage.textContent = `Captured ${plan.length} samples`;
      } catch (error) {
        planMessage.textContent = error.message;
      } finally {
        captureAll.disabled = false;
      }
    };

    detectButton.onclick = async () => {
      detectButton.disabled = true;
      clearTuningView("Detecting live card back...");
      try {
        const [detection, image] = await Promise.all([
          json("/api/card-back/detect", {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({detection_method: selectedDetectionMethod()}),
          }),
          loadImage("/api/camera/frame.jpg"),
        ]);
        frameImage = image;
        expectedCorners = cornerObjectFromArray(detection.corners_px) || defaultCardCorners(image);
        truthCorners = cloneCorners(expectedCorners);
        currentSample = null;
        lastResult.textContent = pretty(detection);
        tuneMessage.textContent = detection.found
          ? "Detected corners. Pan the reference view, drag source-image corners, or use the panel controls."
          : "No card detected; seeded a centered manual box you can tune.";
        renderTuning();
      } catch (error) {
        tuneMessage.textContent = error.message;
      } finally {
        detectButton.disabled = false;
      }
    };
    document.querySelectorAll("[data-training-corner]").forEach(button => {
      button.onclick = () => {
        selectCorner(button.dataset.trainingCorner);
      };
    });
    document.querySelectorAll("[data-training-nudge]").forEach(button => {
      button.onclick = () => {
        const [x, y] = button.dataset.trainingNudge.split(",").map(Number);
        const step = cornerStep();
        moveSelectedCorner(x * step, y * step);
      };
    });
    zoomInput.oninput = () => {
      clampViewport();
      renderTuning();
    };
    const viewportWindow = () => {
      const size = outputSize();
      const zoom = Math.max(1, Number(zoomInput.value) || 4);
      const viewWidth = size.width / zoom;
      const viewHeight = viewWidth * (tuneCanvas.height / tuneCanvas.width);
      return {
        left: clampValue(tuneViewport.x - viewWidth / 2, 0, Math.max(0, size.width - viewWidth)),
        top: clampValue(tuneViewport.y - viewHeight / 2, 0, Math.max(0, size.height - viewHeight)),
        width: viewWidth,
        height: viewHeight,
        outputWidth: size.width,
        outputHeight: size.height,
      };
    };
    const clampViewport = () => {
      const view = viewportWindow();
      tuneViewport = {x: view.left + view.width / 2, y: view.top + view.height / 2};
    };
    const outputPointFromEvent = event => {
      const rect = tuneCanvas.getBoundingClientRect();
      const view = viewportWindow();
      return {
        x: view.left + ((event.clientX - rect.left) / rect.width) * view.width,
        y: view.top + ((event.clientY - rect.top) / rect.height) * view.height,
        view,
      };
    };
    const overlayPointFromEvent = event => {
      if (!cornerOverlay?.createSVGPoint || !cornerOverlay.getScreenCTM()) return null;
      const point = cornerOverlay.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      return point.matrixTransform(cornerOverlay.getScreenCTM().inverse());
    };
    cornerOverlay?.addEventListener("pointerdown", event => {
      const handle = event.target.closest?.("[data-training-corner-handle]");
      if (!handle || !truthCorners?.[handle.dataset.trainingCornerHandle]) return;
      event.preventDefault();
      const corner = handle.dataset.trainingCornerHandle;
      setSelectedCornerOnly(corner);
      renderCornerOverlay();
      cornerPointer = {id: event.pointerId, corner};
      cornerOverlay.setPointerCapture(event.pointerId);
    });
    cornerOverlay?.addEventListener("pointermove", event => {
      if (!cornerPointer || cornerPointer.id !== event.pointerId || !frameImage) return;
      event.preventDefault();
      const point = overlayPointFromEvent(event);
      if (!point) return;
      truthCorners[cornerPointer.corner].x = clampValue(point.x, 0, Math.max(0, frameImage.width - 1));
      truthCorners[cornerPointer.corner].y = clampValue(point.y, 0, Math.max(0, frameImage.height - 1));
      renderCornerOverlay();
    });
    cornerOverlay?.addEventListener("pointerup", event => {
      if (!cornerPointer || cornerPointer.id !== event.pointerId) return;
      event.preventDefault();
      cornerPointer = null;
      renderTuning();
    });
    cornerOverlay?.addEventListener("pointercancel", event => {
      if (cornerPointer?.id !== event.pointerId) return;
      cornerPointer = null;
      renderTuning();
    });
    tuneCanvas.addEventListener("pointerdown", event => {
      tuneCanvas.focus();
      const point = outputPointFromEvent(event);
      tunePointer = {
        id: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startViewport: {...tuneViewport},
        startOutput: point,
        moved: false,
      };
      tuneCanvas.setPointerCapture(event.pointerId);
    });
    tuneCanvas.addEventListener("pointermove", event => {
      if (!tunePointer || tunePointer.id !== event.pointerId) return;
      const dx = event.clientX - tunePointer.startClientX;
      const dy = event.clientY - tunePointer.startClientY;
      if (Math.abs(dx) + Math.abs(dy) > 3) tunePointer.moved = true;
      const rect = tuneCanvas.getBoundingClientRect();
      const view = viewportWindow();
      tuneViewport = {
        x: tunePointer.startViewport.x - (dx / rect.width) * view.width,
        y: tunePointer.startViewport.y - (dy / rect.height) * view.height,
      };
      clampViewport();
      renderTuning();
    });
    tuneCanvas.addEventListener("pointerup", event => {
      if (!tunePointer || tunePointer.id !== event.pointerId) return;
      if (!tunePointer.moved) {
        const point = outputPointFromEvent(event);
        tuneViewport = {x: point.x, y: point.y};
        clampViewport();
        renderTuning();
      }
      tunePointer = null;
    });
    tuneCanvas.addEventListener("pointercancel", event => {
      if (tunePointer?.id === event.pointerId) tunePointer = null;
    });
    function renderTuning() {
      renderCornerOverlay();
      const context = tuneCanvas.getContext("2d");
      context.clearRect(0, 0, tuneCanvas.width, tuneCanvas.height);
      if (!frameImage || !expectedCorners || !truthCorners) {
        context.fillStyle = "#111827";
        context.fillRect(0, 0, tuneCanvas.width, tuneCanvas.height);
        return;
      }
      const view = viewportWindow();
      const sourceCanvas = document.createElement("canvas");
      sourceCanvas.width = frameImage.width;
      sourceCanvas.height = frameImage.height;
      const sourceContext = sourceCanvas.getContext("2d", {willReadFrequently: true});
      sourceContext.drawImage(frameImage, 0, 0, frameImage.width, frameImage.height);
      const source = sourceContext.getImageData(0, 0, frameImage.width, frameImage.height);
      const matrix = projectiveMapForUnitSquare(corners.map(corner => truthCorners[corner]));
      const warped = context.createImageData(tuneCanvas.width, tuneCanvas.height);
      if (matrix) {
        for (let y = 0; y < tuneCanvas.height; y += 1) {
          const outputY = view.top + (y / Math.max(1, tuneCanvas.height - 1)) * view.height;
          const normalizedY = outputY / Math.max(1, view.outputHeight - 1);
          for (let x = 0; x < tuneCanvas.width; x += 1) {
            const outputX = view.left + (x / Math.max(1, tuneCanvas.width - 1)) * view.width;
            const normalizedX = outputX / Math.max(1, view.outputWidth - 1);
            const sourcePoint = transformPoint(matrix, normalizedX, normalizedY);
            const sourceX = clampValue(Math.round(sourcePoint.x), 0, frameImage.width - 1);
            const sourceY = clampValue(Math.round(sourcePoint.y), 0, frameImage.height - 1);
            const sourceIndex = (sourceY * frameImage.width + sourceX) * 4;
            const outputIndex = (y * tuneCanvas.width + x) * 4;
            warped.data[outputIndex] = source.data[sourceIndex];
            warped.data[outputIndex + 1] = source.data[sourceIndex + 1];
            warped.data[outputIndex + 2] = source.data[sourceIndex + 2];
            warped.data[outputIndex + 3] = 255;
          }
        }
        context.putImageData(warped, 0, 0);
      }
      if (truthImage) {
        context.save();
        context.globalAlpha = 0.52;
        context.drawImage(truthImage, view.left, view.top, view.width, view.height, 0, 0, tuneCanvas.width, tuneCanvas.height);
        context.restore();
      }
      const drawOutputMarker = (point, color, radius) => {
        const x = ((point.x - view.left) / view.width) * tuneCanvas.width;
        const y = ((point.y - view.top) / view.height) * tuneCanvas.height;
        if (x < -radius || y < -radius || x > tuneCanvas.width + radius || y > tuneCanvas.height + radius) return;
        context.strokeStyle = color;
        context.lineWidth = 2;
        context.beginPath();
        context.arc(x, y, radius, 0, Math.PI * 2);
        context.stroke();
        context.beginPath();
        context.moveTo(x - 18, y);
        context.lineTo(x + 18, y);
        context.moveTo(x, y - 18);
        context.lineTo(x, y + 18);
        context.stroke();
      };
      const referenceCorners = {
        nw: {x: 0, y: 0},
        ne: {x: view.outputWidth - 1, y: 0},
        se: {x: view.outputWidth - 1, y: view.outputHeight - 1},
        sw: {x: 0, y: view.outputHeight - 1},
      };
      drawOutputMarker(referenceCorners[selectedCorner], "#f59e0b", 16);
      const offsetX = truthCorners ? truthCorners[selectedCorner].x - expectedCorners[selectedCorner].x : 0;
      const offsetY = truthCorners ? truthCorners[selectedCorner].y - expectedCorners[selectedCorner].y : 0;
      tuneMessage.textContent = `${selectedCorner.toUpperCase()} source offset ${offsetX.toFixed(1)}, ${offsetY.toFixed(1)} px. Reference stays fixed; warped capture moves underneath.`;
    }
    function renderCornerOverlay() {
      if (!cornerOverlay || !frameImage || !expectedCorners) {
        if (cornerOverlay) cornerOverlay.innerHTML = "";
        return;
      }
      cornerOverlay.setAttribute("viewBox", `0 0 ${frameImage.width} ${frameImage.height}`);
      const polygon = cornersToArray(expectedCorners).map(([x, y]) => `${x},${y}`).join(" ");
      const truth = truthCorners ? cornersToArray(truthCorners).map(([x, y]) => `${x},${y}`).join(" ") : "";
      const handles = truthCorners ? corners.map(corner => {
        const point = truthCorners[corner];
        return `<circle class="corner-handle${corner === selectedCorner ? " selected" : ""}" data-training-corner-handle="${corner}" cx="${Number(point.x)}" cy="${Number(point.y)}" r="12"><title>${corner.toUpperCase()}</title></circle>`;
      }).join("") : "";
      cornerOverlay.innerHTML = `
        <polygon class="expected" points="${escapeHtml(polygon)}"></polygon>
        ${truth ? `<polygon class="truth" points="${escapeHtml(truth)}"></polygon>` : ""}
        ${handles}
      `;
    }
    async function saveCurrentLabel(split = null) {
      if (!currentSample?.sample_id || !truthCorners) {
        tuneMessage.textContent = "Capture a sample before saving tuning";
        return;
      }
      const modelId = activeModelId();
      const result = await json(`/api/card-back-training/models/${modelId}/samples/${currentSample.sample_id}`, {
        method:"PATCH",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          truth_corners_px: truthCorners,
          expected_crop: expectedCorners ? {corners_px: cornersToArray(expectedCorners)} : {},
          ...(split ? {split} : {}),
        }),
      });
      summary = result.summary;
      currentSample = result.sample;
      renderModels();
      tuneMessage.textContent = `Saved ${currentSample.sample_id}`;
      lastResult.textContent = pretty(result.sample.label);
    }
    saveLabel.onclick = () => saveCurrentLabel().catch(error => tuneMessage.textContent = error.message);
    labelTrain.onclick = () => saveCurrentLabel("train").catch(error => tuneMessage.textContent = error.message);
    labelEval.onclick = () => saveCurrentLabel("eval").catch(error => tuneMessage.textContent = error.message);

    refreshSummary();
    renderPlan();
    drawBox();
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
      message.textContent = data.message || (data.restart_required ? "Update applied. Restart required." : "");
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
          <p class="eyebrow status-${escapeHtml(item.status)}">${escapeHtml(item.status)}</p>
          <h3>${escapeHtml(item.name)}</h3>
          <p class="muted">${escapeHtml(item.detail)}</p>
        </article>`).join("");
    })();
  },
};
