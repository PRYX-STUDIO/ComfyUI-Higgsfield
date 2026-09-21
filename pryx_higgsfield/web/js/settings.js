import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

/* PRYX Higgsfield ComfyUI extension.
 *
 * Secrets are sent only to the local ComfyUI settings routes. They are never
 * returned to this script after saving and are not written to browser storage.
 */

const SETTINGS_ROUTE = "/pryx-higgsfield/settings";
const VALIDATE_ROUTE = "/pryx-higgsfield/settings/validate";
const CATALOG_ROUTE = "/pryx-higgsfield/catalog";
const REFRESH_ROUTE = "/pryx-higgsfield/catalog/refresh";

const GENERATOR_CAPABILITIES = {
    PRYXHiggsfieldImageGenerateEdit: new Set(["image_generate", "image_edit"]),
    PRYXHiggsfieldTextToVideo: new Set(["text_to_video"]),
    PRYXHiggsfieldImageToVideo: new Set(["image_to_video"]),
    PRYXHiggsfieldReferenceToVideo: new Set(["reference_to_video"]),
    PRYXHiggsfieldVideoEdit: new Set(["video_edit"]),
    PRYXHiggsfieldVideoExtend: new Set(["video_extend"]),
};
GENERATOR_CAPABILITIES.PRYXHiggsfieldAdvancedRequest = new Set(Object.values(GENERATOR_CAPABILITIES).flatMap((set) => [...set]));
const NODE_UI_SCHEMA_VERSION = 4;

const ALWAYS_VISIBLE_WIDGETS = new Set(["model", "mode", "max_usd", "auto_save", "timeout", "model_info", "arguments_json"]);
const MEDIA_PARAMETER_NAMES = new Set([
    "image_url",
    "end_image_url",
    "last_image_url",
    "image_urls",
    "video_url",
    "video_urls",
    "audio_url",
    "audio_urls",
    "file_url",
    "link_url",
]);
const MEDIA_INPUT_NAMES = new Set(["references", "image", "end_image", "video", "audio"]);
let catalogPromise;

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || "Request failed (" + response.status + ")");
    }
    return data;
}

function notify(message, error = false) {
    if (app?.ui?.dialog) {
        app.ui.dialog.show(message);
    } else {
        console[error ? "error" : "info"]("[PRYX Higgsfield] " + message);
    }
}

function createSettingsButton(text, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.style.cssText =
        "padding: 6px 12px; border: 1px solid var(--border-color, #666); " +
        "border-radius: 6px; cursor: pointer;";
    button.addEventListener("click", onClick);
    return button;
}

function createCredentialSetting() {
    const wrapper = document.createElement("div");
    wrapper.style.cssText = "display: flex; align-items: center; gap: 10px;";

    const button = createSettingsButton("Manage credentials", openCredentialDialog);
    const status = document.createElement("span");
    status.textContent = "Checking...";
    status.style.opacity = "0.75";
    wrapper.append(button, status);

    requestJson(SETTINGS_ROUTE)
        .then((result) => {
            status.textContent = result.configured
                ? "Configured (" + (result.key_id || "key") + ")"
                : "Not configured";
        })
        .catch(() => {
            status.textContent = "Unavailable";
        });

    return wrapper;
}

function createCatalogRefreshSetting() {
    return createSettingsButton("Refresh catalog", refreshCatalog);
}

function closeCredentialDialog() {
    const overlay = document.getElementById("pryx-higgsfield-credentials");
    if (!overlay) return;
    overlay.__pryxClose?.();
    overlay.remove();
}

function openCredentialDialog(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    closeCredentialDialog();

    const overlay = document.createElement("div");
    overlay.id = "pryx-higgsfield-credentials";
    overlay.setAttribute("role", "presentation");
    overlay.style.cssText =
        "position: fixed; inset: 0; z-index: 10000; display: grid; " +
        "place-items: center; padding: 24px; background: rgba(0, 0, 0, 0.68);";

    const panel = document.createElement("section");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "pryx-higgsfield-credentials-title");
    panel.style.cssText =
        "width: min(520px, 100%); box-sizing: border-box; padding: 24px; " +
        "border: 1px solid var(--border-color, #4b5563); border-radius: 14px; " +
        "background: var(--interface-panel-surface, #202124); color: var(--fg-color, #fff); " +
        "box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5); font-family: inherit;";
    panel.innerHTML =
        '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:16px;">' +
        '<div>' +
        '<h2 id="pryx-higgsfield-credentials-title" style="margin:0 0 8px; font-size:1.15rem;">PRYX Higgsfield credentials</h2>' +
        '<p style="margin:0 0 20px; opacity:.75; line-height:1.45;">The credentials stay on this ComfyUI installation and never become workflow inputs.</p>' +
        '</div>' +
        '<button type="button" data-action="close" aria-label="Close" style="border:0; background:transparent; color:inherit; font-size:1.4rem; cursor:pointer;">×</button>' +
        '</div>' +
        '<form>' +
        '<label style="display:block; margin-bottom:14px;">Key ID' +
        '<input name="key_id" autocomplete="off" required style="display:block; box-sizing:border-box; width:100%; margin-top:6px; padding:10px 12px; border:1px solid var(--border-color, #4b5563); border-radius:8px; background:var(--comfy-input-bg, #151515); color:inherit;" />' +
        '</label>' +
        '<label style="display:block; margin-bottom:14px;">Secret' +
        '<input name="secret" type="password" autocomplete="new-password" required style="display:block; box-sizing:border-box; width:100%; margin-top:6px; padding:10px 12px; border:1px solid var(--border-color, #4b5563); border-radius:8px; background:var(--comfy-input-bg, #151515); color:inherit;" />' +
        '</label>' +
        '<output name="status" aria-live="polite" style="display:block; min-height:1.5em; margin:4px 0 18px; opacity:.8;"></output>' +
        '<div style="display:flex; justify-content:flex-end; gap:10px; flex-wrap:wrap;">' +
        '<button type="button" data-action="cancel" style="padding:9px 14px; border:1px solid var(--border-color, #4b5563); border-radius:8px; background:transparent; color:inherit; cursor:pointer;">Cancel</button>' +
        '<button type="button" data-action="validate" style="padding:9px 14px; border:1px solid var(--border-color, #4b5563); border-radius:8px; background:transparent; color:inherit; cursor:pointer;">Validate estimate</button>' +
        '<button type="button" data-action="save" style="padding:9px 14px; border:0; border-radius:8px; background:#4f46e5; color:white; cursor:pointer;">Save locally</button>' +
        '</div>' +
        '</form>';
    overlay.appendChild(panel);

    const form = panel.querySelector("form");
    const status = form.elements.status;
    const values = () => ({
        key_id: form.elements.key_id.value,
        secret: form.elements.secret.value,
    });
    const close = () => {
        document.removeEventListener("keydown", onKeyDown);
        overlay.remove();
    };
    const onKeyDown = (keyEvent) => {
        if (keyEvent.key === "Escape") {
            keyEvent.preventDefault();
            keyEvent.stopPropagation();
            close();
        }
    };
    overlay.__pryxClose = close;
    overlay.addEventListener("click", (clickEvent) => {
        if (clickEvent.target !== overlay) return;
        clickEvent.preventDefault();
        clickEvent.stopPropagation();
        close();
    });
    panel.addEventListener("click", (clickEvent) => clickEvent.stopPropagation());
    overlay.querySelector('[data-action="close"]').addEventListener("click", close);
    overlay.querySelector('[data-action="cancel"]').addEventListener("click", close);
    overlay.querySelector('[data-action="validate"]').addEventListener("click", async () => {
        status.textContent = "Validating...";
        try {
            const result = await requestJson(VALIDATE_ROUTE, { method: "POST", body: JSON.stringify(values()) });
            status.textContent = "Valid. Estimate: " + (result.credits ?? "n/a") + " credits / " + (result.usd ?? "n/a") + " USD.";
        } catch (error) {
            status.textContent = error.message;
        }
    });
    overlay.querySelector('[data-action="save"]').addEventListener("click", async () => {
        status.textContent = "Saving...";
        try {
            await requestJson(SETTINGS_ROUTE, { method: "PUT", body: JSON.stringify(values()) });
            form.elements.secret.value = "";
            status.textContent = "Saved locally. The secret was cleared from the form.";
        } catch (error) {
            status.textContent = error.message;
        }
    });
    form.addEventListener("submit", (submitEvent) => submitEvent.preventDefault());
    const settingsDialog =
        [...document.querySelectorAll('[role="dialog"]')].find((dialog) =>
            dialog.contains(document.activeElement),
        ) || document.querySelector('[role="dialog"]:not([aria-modal="true"])');
    (settingsDialog || document.body).appendChild(overlay);
    document.addEventListener("keydown", onKeyDown);
    form.elements.key_id.focus();
}

async function refreshCatalog() {
    try {
        const result = await requestJson(REFRESH_ROUTE, { method: "POST", body: "{}" });
        notify("Catalog downloaded: " + result.catalog_version + ". Restart ComfyUI and reload the browser to activate it consistently in all nodes.");
    } catch (error) {
        notify(error.message, true);
    }
}

function handleProgress(event) {
    const data = event.detail || event;
    if (!data || !app?.graph) return;
    const node = data.node_id ? app.graph.getNodeById?.(Number(data.node_id)) : null;
    if (!node) return;
    node.properties = node.properties || {};
    node.properties.pryx_higgsfield_status = {
        phase: data.phase,
        status: data.status || null,
        request_id: data.request_id || null,
        elapsed_seconds: data.elapsed_seconds,
        usd: data.usd ?? null,
    };
    node.setDirtyCanvas?.(true, false);
}

function getCatalog() {
    if (!catalogPromise) {
        catalogPromise = requestJson(CATALOG_ROUTE).catch((error) => {
            catalogPromise = null;
            throw error;
        });
    }
    return catalogPromise;
}

function nodeTypeName(node) {
    return node?.type || node?.comfyClass || "";
}

function modelCapabilitiesForNode(node) {
    const type = nodeTypeName(node);
    if (GENERATOR_CAPABILITIES[type]) return GENERATOR_CAPABILITIES[type];
    const normalized = type.replace(/\s+/g, "");
    const entry = Object.entries(GENERATOR_CAPABILITIES).find(([name]) => normalized.includes(name));
    return entry?.[1] || null;
}

function modelForNode(node, models) {
    const modelWidget = node.widgets?.find((item) => item.name === "model");
    let modelId = modelWidget?.value;
    const modelInput = node.inputs?.find((item) => item.name === "model");
    if (modelInput?.link && app?.graph?.links) {
        const link = app.graph.links[modelInput.link];
        const sourceNode = link ? app.graph.getNodeById?.(link.origin_id) : null;
        const sourceWidget = sourceNode?.widgets?.find((item) => item.name === "model_id" || item.name === "model");
        if (sourceWidget?.value) modelId = sourceWidget.value;
    }
    return models.find((item) => item.id === modelId) || null;
}

function parameterTooltip(parameter) {
    const pieces = [];
    if (parameter.description) pieces.push(parameter.description);
    if (parameter.choices?.length) pieces.push("Choices: " + parameter.choices.join(", "));
    if (parameter.minimum != null || parameter.maximum != null) {
        pieces.push(`Range: ${parameter.minimum ?? "-∞"}–${parameter.maximum ?? "∞"}`);
    }
    if (parameter.min_items != null || parameter.max_items != null) {
        pieces.push(`Items: ${parameter.min_items ?? 0}–${parameter.max_items ?? "∞"}`);
    }
    return pieces.join(" ") || "Catalog-defined model parameter.";
}

function setWidgetVisibility(widget, visible) {
    widget.hidden = !visible;
    widget.options = widget.options || {};
    widget.options.hidden = !visible;
}

function setWidgetValue(node, widget, value) {
    widget.value = value;
    const index = node.widgets?.indexOf(widget) ?? -1;
    if (index >= 0 && Array.isArray(node.widgets_values)) node.widgets_values[index] = value;
    for (const element of [widget.element, widget.inputEl]) {
        if (element && "value" in element) element.value = String(value);
    }
}

function setWidgetFromParameter(node, widget, parameter) {
    widget.options = widget.options || {};
    const currentValue = widget.value;
    const choices = parameter.choices || [];
    if (choices.length) {
        widget.type = "combo";
        widget.options.values = choices;
        widget.options.options = choices;
        widget.options.widgetType = "COMBO";
    } else {
        if (widget.type === "combo") widget.type = parameter.type === "integer" || parameter.type === "number" ? "number" : "text";
        delete widget.options.values;
        delete widget.options.options;
        if (widget.options.widgetType === "COMBO") delete widget.options.widgetType;
    }
    if (parameter.minimum != null) widget.options.min = parameter.minimum;
    else delete widget.options.min;
    if (parameter.maximum != null) widget.options.max = parameter.maximum;
    else delete widget.options.max;
    const tooltip = parameterTooltip(parameter);
    widget.options.tooltip = tooltip + (parameter.name === "seed" ? " Use -1 for a random provider seed (field omitted)." : "");
    widget.tooltip = widget.options.tooltip;
    if (parameter.name === "seed") widget.options.min = -1;

    if (choices.length && !choices.includes(currentValue)) {
        setWidgetValue(node, widget, parameter.default ?? choices[0]);
    } else if (parameter.type === "integer" || parameter.type === "number") {
        const numericValue = Number(currentValue);
        const defaultValue = Number(parameter.default);
        const hasMinimum = parameter.minimum != null;
        const hasMaximum = parameter.maximum != null;
        const isInRange = (value) => (parameter.name === "seed" && value === -1) || Number.isFinite(value) &&
            (!hasMinimum || value >= parameter.minimum) &&
            (!hasMaximum || value <= parameter.maximum);
        let normalizedValue = numericValue;
        if (!isInRange(normalizedValue)) {
            normalizedValue = isInRange(defaultValue)
                ? defaultValue
                : (hasMinimum ? parameter.minimum : (hasMaximum ? parameter.maximum : 0));
        }
        setWidgetValue(node, widget, parameter.type === "integer" ? Math.round(normalizedValue) : normalizedValue);
    }
    if (parameter.type === "boolean" && typeof parameter.default === "boolean") {
        setWidgetValue(node, widget, Boolean(widget.value));
    }
}

function parameterDefault(parameter) {
    if (parameter.name === "seed" && parameter.default == null) return -1;
    if (["array", "list", "object", "json"].includes(parameter.type)) {
        return parameter.default == null ? "" : JSON.stringify(parameter.default);
    }
    if (parameter.default != null) return parameter.default;
    if (parameter.choices?.length) return parameter.choices[0];
    if (parameter.type === "boolean") return false;
    if (parameter.type === "integer" || parameter.type === "number") {
        if (parameter.minimum != null) return parameter.minimum;
        return 0;
    }
    if (parameter.type === "array" || parameter.type === "list" || parameter.type === "object" || parameter.type === "json") {
        return parameter.name === "shots" ? "[]" : "{}";
    }
    return "";
}

function resetLegacyWidgetValues(node, parameters) {
    const defaults = {
        mode: "estimate_only",
        max_usd: 0,
        auto_save: true,
        timeout: 1800,
    };
    for (const widget of node.widgets || []) {
        if (widget.name === "model") continue;
        if (Object.prototype.hasOwnProperty.call(defaults, widget.name)) {
            setWidgetValue(node, widget, defaults[widget.name]);
            continue;
        }
        const parameter = parameters.get(widget.name);
        if (parameter) setWidgetValue(node, widget, parameterDefault(parameter));
    }
}

function modelTooltip(model) {
    if (!model) return "Choose a model from the validated PRYX Higgsfield catalog.";
    const media = model.input_media?.length ? model.input_media.join(", ") : "none";
    const limit = model.max_references == null ? "see per-input limits below" : `up to ${model.max_references}`;
    return `${model.display_name} (${model.id}). Capability: ${model.capability}. Supported references: ${media}; ${limit} total reference(s).`;
}

function updateMediaInputs(node, model) {
    const supported = new Set(model?.input_media || []);
    for (const input of node.inputs || []) {
        if (!MEDIA_INPUT_NAMES.has(input.name)) continue;
        const visible = input.name === "references" ? supported.size > 0 : input.name === "end_image"
            ? model?.parameters?.some((p) => ["end_image_url", "last_image_url"].includes(p.name))
            : supported.has(input.name);
        input.hidden = !visible;
        input.tooltip = visible
            ? input.name === "references"
                ? "Combined media from Reference Collector. Direct media inputs are added to this collection; all inputs share the model limits."
                : input.name === "image" && model?.parameters?.some((p) => p.name === "image_url")
                    ? "One start/source image. Use end_image for the final frame when supported."
                    : `${input.name} connected directly from a matching ComfyUI loader or processing node. Counts toward the same limits as Reference Collector.`
            : `Hidden for the selected model; it does not accept ${input.name} references.`;
    }
    const outputHints = {
        video: "Generated video. Connect to Save Video or another VIDEO-compatible node. Empty in estimate-only mode.",
        local_file: "Path of the downloaded video on this computer. auto_save chooses output versus temporary storage.",
        remote_url: "Provider download links as JSON text. Not a local video input.",
        request_id: "Provider request identifier for troubleshooting. Empty before a generation is submitted.",
        credits: "Estimated cost in provider credits, not your balance or a final billing receipt.",
        usd: "Estimated cost in USD, not your balance or a final billing receipt.",
        status: "JSON text containing request status and diagnostic information.",
    };
    for (const output of node.outputs || []) {
        if (outputHints[output.name]) output.tooltip = outputHints[output.name];
    }
}

const MEDIA_LABELS = {
    image_url: "Start/source image", end_image_url: "End image", last_image_url: "End image",
    image_urls: "Reference images", video_url: "Source video", video_urls: "Reference videos",
    audio_url: "Audio track", audio_urls: "Reference audio tracks",
    file_url: "Document link", link_url: "Web page link",
};

function readableModelNote(text) {
    let result = text.replace(/Use public media URLs; `asset:\/\/` references are not supported\.\s*/gi, "");
    for (const [field, label] of Object.entries(MEDIA_LABELS).sort((a, b) => b[0].length - a[0].length)) {
        result = result.replaceAll(field, label.toLowerCase());
    }
    return result.replaceAll("`", "").replace(/public(?:ly accessible)?\s+/gi, "")
        .replace(/\bURLs\b/g, "connected media");
}

function updateModelInfo(node, model) {
    let widget = node.widgets?.find((item) => item.name === "model_info");
    if (!widget) {
        const element = document.createElement("div");
        element.className = "pryx-model-info";
        element.setAttribute("role", "note");
        element.style.cssText = "box-sizing:border-box; padding:12px; overflow:auto; white-space:pre-wrap; " +
            "font:12px/1.5 sans-serif; color:var(--fg-color,#ddd); background:var(--comfy-input-bg,#202020); " +
            "border:1px solid var(--border-color,#555); border-radius:8px;";
        widget = node.addDOMWidget("model_info", "pryx_model_info", element, {
            serialize: false, hideOnZoom: false,
            getValue: () => "", setValue: () => {},
        });
        const details = document.createElement("details");
        details.open = node.properties?.pryx_model_info_expanded !== false;
        const summary = document.createElement("summary");
        summary.style.cssText = "cursor:pointer;font-weight:600;white-space:normal;";
        const body = document.createElement("div");
        body.style.paddingTop = "8px";
        details.append(summary, body);
        element.append(details);
        details.addEventListener("toggle", () => {
            node.properties ||= {};
            node.properties.pryx_model_info_expanded = details.open;
            node.setSize(node.computeSize());
            node.setDirtyCanvas(true, true);
        });
        widget.computeSize = () => [320, details.open ? 240 : 48];
        widget.options.getMinHeight = () => details.open ? 240 : 48;
        widget.options.getMaxHeight = () => details.open ? 400 : 48;
        widget.__pryxInfoElement = body;
        widget.__pryxInfoSummary = summary;
    }
    const element = widget.__pryxInfoElement || widget.element;
    if (!element) return;
    if (widget.__pryxInfoSummary) widget.__pryxInfoSummary.textContent = `${model?.display_name || "Model"} · Inputs & limits (click to expand/collapse)`;
    if (!model) {
        element.textContent = "INCOMPATIBLE MODEL\nThe connected model is not supported by this node. Select a matching capability in Model Catalog.";
        return;
    }
    const lines = [model.display_name, `${model.provider} · ${model.capability.replaceAll("_", " ")}`, "", "INPUTS & LIMITS"];
    const media = model.parameters.filter((p) => p.media_types?.length);
    if (!media.length) lines.push("No reference media accepted.");
    if (media.some((p) => p.media_types.some((kind) => ["image", "video", "audio"].includes(kind)))) {
        lines.push("Connect media directly from ComfyUI, or combine several inputs with Reference Collector.");
    }
    for (const p of media) {
        const count = p.type === "array"
            ? `${p.min_items ?? 0}–${p.max_items ?? "no documented maximum"} when connected`
            : "1";
        lines.push(`${MEDIA_LABELS[p.name] || p.media_types.join("/")}: ${count} · ${p.required ? "required" : "optional"}`);
    }
    lines.push("", "OUTPUT");
    for (const name of ["resolution", "aspect_ratio", "duration", "output_format", "batch_size"]) {
        const p = model.parameters.find((p) => p.name === name);
        if (!p) continue;
        lines.push(`${name}: ${p.choices?.join(" / ") || `${p.minimum ?? "?"}–${p.maximum ?? "?"}`}${p.default != null ? ` · default ${p.default}` : ""}`);
    }
    if (model.parameters.some((p) => p.name === "resolution")) {
        lines.push("Resolution is the API quality/size tier, not width × height. Framing uses aspect_ratio when supported; otherwise the source media/model determines it.");
    }
    if (model.notes?.length) lines.push("", "MODEL NOTES", ...model.notes.map(readableModelNote));
    if (model.id === "marketing-studio-image") lines.push("Enhanced mode: preset_id + 1 product image required; 1 optional model image. Direct mode: up to 16 images.");
    lines.push("", "Limits checked before upload. Media content, duration and account availability are also validated by the provider.");
    if (media.length) lines.push("", "Technical note: connected media is uploaded to the provider automatically. No manual hosting is needed. Document/web links remain external links.");
    element.textContent = lines.join("\n");
}

function updateModelCatalogNode(node, models) {
    if (!nodeTypeName(node).includes("ModelCatalog")) return false;
    const providerWidget = node.widgets?.find((item) => item.name === "provider");
    const capabilityWidget = node.widgets?.find((item) => item.name === "capability");
    const statusWidget = node.widgets?.find((item) => item.name === "status");
    const modelWidget = node.widgets?.find((item) => item.name === "model_id");
    if (!modelWidget) return true;
    const provider = providerWidget?.value || "all";
    const capability = capabilityWidget?.value || "all";
    const status = statusWidget?.value || "active";
    const matches = models.filter((item) =>
        (provider === "all" || item.provider === provider) &&
        (capability === "all" || item.capability === capability) &&
        (status === "all" || item.status === status),
    );
    modelWidget.options = modelWidget.options || {};
    modelWidget.options.values = matches.map((item) => item.id);
    if (!matches.some((item) => item.id === modelWidget.value)) modelWidget.value = matches[0]?.id || "";
    const selected = matches.find((item) => item.id === modelWidget.value);
    updateModelInfo(node, selected);
    modelWidget.options.tooltip = modelTooltip(selected);
    modelWidget.tooltip = modelTooltip(selected);
    node.properties = node.properties || {};
    node.properties.pryx_higgsfield_model_info = selected ? {
        display_name: selected.display_name,
        capability: selected.capability,
        input_media: selected.input_media || [],
        max_references: selected.max_references ?? null,
    } : null;
    node.setDirtyCanvas?.(true, true);
    return true;
}

function attachCatalogCallbacks(node) {
    if (node.__pryxCatalogCallbacksAttached) return;
    node.__pryxCatalogCallbacksAttached = true;
    for (const widget of node.widgets || []) {
        if (!["model", "model_id", "provider", "capability", "status"].includes(widget.name)) continue;
        const original = widget.callback;
        widget.callback = function (...args) {
            const result = original?.apply(this, args);
            updateCatalogWidgets(node);
            for (const other of app.graph?._nodes || []) {
                if (other !== node && modelCapabilitiesForNode(other)) updateCatalogWidgets(other);
            }
            return result;
        };
    }
    const originalConnectionsChange = node.onConnectionsChange;
    node.onConnectionsChange = function (...args) {
        const result = originalConnectionsChange?.apply(this, args);
        updateCatalogWidgets(node);
        return result;
    };
}

async function updateCatalogWidgets(node) {
    try {
        const catalog = await getCatalog();
        const models = catalog.models || [];
        if (updateModelCatalogNode(node, models)) {
            attachCatalogCallbacks(node);
            return;
        }
        const capabilities = modelCapabilitiesForNode(node);
        if (!capabilities) return;
        const compatible = models.filter((item) => item.status === "active" && capabilities.has(item.capability));
        const modelWidget = node.widgets?.find((item) => item.name === "model");
        if (!modelWidget || !compatible.length) return;
        modelWidget.options = modelWidget.options || {};
        modelWidget.options.values = compatible.map((item) => item.id);
        modelWidget.type = "combo";
        if (!compatible.some((item) => item.id === modelWidget.value)) modelWidget.value = compatible[0].id;
        const model = modelForNode(node, compatible);
        updateModelInfo(node, model);
        if (!model) return;
        modelWidget.options.tooltip = modelTooltip(model);
        modelWidget.tooltip = modelTooltip(model);

        const parameters = new Map((model?.parameters || []).map((item) => [item.name === "shots" ? "shots_json" : item.name, item]));
        const previousModelInfo = node.properties?.pryx_higgsfield_model_info;
        const modelChanged = Boolean(previousModelInfo?.id && previousModelInfo.id !== model?.id);
        const legacyWorkflow = node.__pryxLegacyWorkflow === true ||
            node.properties?.pryx_higgsfield_ui_schema !== NODE_UI_SCHEMA_VERSION;
        if (legacyWorkflow) resetLegacyWidgetValues(node, parameters);
        for (const widget of node.widgets || []) {
            if (widget.name === "mode") {
                widget.options = widget.options || {};
                widget.options.values = ["estimate_only", "generate"];
                if (!widget.options.values.includes(widget.value)) setWidgetValue(node, widget, "estimate_only");
                widget.options.tooltip = "Estimate cost without generating, or submit the paid generation request.";
                continue;
            }
            if (ALWAYS_VISIBLE_WIDGETS.has(widget.name)) continue;
            if (widget.name === "model_id") continue;
            const parameter = parameters.get(widget.name);
            if (MEDIA_PARAMETER_NAMES.has(widget.name)) {
                setWidgetVisibility(widget, false);
            } else {
                setWidgetVisibility(widget, Boolean(parameter));
                if (parameter) {
                    if (modelChanged) {
                        setWidgetValue(node, widget, parameterDefault(parameter));
                    }
                    setWidgetFromParameter(node, widget, parameter);
                }
            }
        }
        updateMediaInputs(node, model);
        node.properties = node.properties || {};
        node.properties.pryx_higgsfield_model_info = model ? {
            id: model.id,
            display_name: model.display_name,
            capability: model.capability,
            provider: model.provider,
            input_media: model.input_media || [],
            max_references: model.max_references ?? null,
            tooltip: modelTooltip(model),
        } : null;
        node.properties.pryx_higgsfield_active_parameters = [...parameters.keys()];
        node.properties.pryx_higgsfield_ui_schema = NODE_UI_SCHEMA_VERSION;
        node.__pryxLegacyWorkflow = false;
        if (!node.__pryxInfoSized) {
            const size = node.computeSize?.();
            if (size) node.setSize?.([Math.max(node.size?.[0] || 0, 360), Math.max(node.size?.[1] || 0, size[1])]);
            node.__pryxInfoSized = true;
        }
        node.setDirtyCanvas?.(true, true);
        attachCatalogCallbacks(node);
    } catch (error) {
        console.debug("[PRYX Higgsfield] catalog widget update skipped", error);
    }
}

async function updateSoulStyleWidget(node) {
    const widget = node.widgets?.find((item) => item.name === "style_id");
    if (!widget) return;
    try {
        const id = node.widgets?.find((item) => item.name === "model")?.value;
        if (!["soul-2", "soul-standard"].includes(id)) return;
        const result = await requestJson("/pryx-higgsfield/styles?variant=" + (id === "soul-2" ? "soul-2" : "soul"));
        widget.options.values = (result.styles || []).map((item) => item.style_id);
    } catch (error) {
        console.debug("[PRYX Higgsfield] style widget update skipped", error);
    }
}

app.registerExtension({
    name: "PRYX.Higgsfield",
    settings: [
        {
            id: "PRYX.Higgsfield.Credentials",
            name: "Higgsfield API credentials",
            category: ["PRYX Higgsfield", "Credentials"],
            type: createCredentialSetting,
            defaultValue: false,
        },
        {
            id: "PRYX.Higgsfield.CatalogRefresh",
            name: "Model catalog",
            category: ["PRYX Higgsfield", "Catalog"],
            type: createCatalogRefreshSetting,
            defaultValue: false,
        },
    ],
    setup() {
        api?.addEventListener?.("pryx_higgsfield.progress", handleProgress);
        // Trigger one read so settings/catalog errors are visible in the
        // browser console without placing credentials in the page.
        requestJson(CATALOG_ROUTE).catch(() => {});
    },
    nodeCreated(node) {
        if (modelCapabilitiesForNode(node) || nodeTypeName(node).replace(/\s+/g, "").includes("PRYXHiggsfieldModelCatalog")) {
            updateCatalogWidgets(node);
            updateSoulStyleWidget(node);
        }
    },
    loadedGraphNode(node) {
        if (!modelCapabilitiesForNode(node) && !nodeTypeName(node).replace(/\s+/g, "").includes("PRYXHiggsfieldModelCatalog")) return;
        node.__pryxLoadedGraphNode = true;
        node.__pryxLegacyWorkflow = node.properties?.pryx_higgsfield_ui_schema !== NODE_UI_SCHEMA_VERSION;
        updateCatalogWidgets(node);
        updateSoulStyleWidget(node);
    },
});
