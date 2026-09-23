import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

/* PRYX ComfyUI Higgsfield extension.
 *
 * Secrets are sent only to the local ComfyUI settings routes. They are never
 * returned to this script after saving and are not written to browser storage.
 */

const SETTINGS_ROUTE = "/pryx-comfyui-higgsfield/settings";
const VALIDATE_ROUTE = "/pryx-comfyui-higgsfield/settings/validate";
const CATALOG_ROUTE = "/pryx-comfyui-higgsfield/catalog";
const REFRESH_ROUTE = "/pryx-comfyui-higgsfield/catalog/refresh";

const GENERATOR_CAPABILITIES = {
    PRYXComfyUIHiggsfieldImageGenerateEdit: new Set(["image_generate", "image_edit"]),
    PRYXComfyUIHiggsfieldTextToVideo: new Set(["text_to_video"]),
    PRYXComfyUIHiggsfieldImageToVideo: new Set(["image_to_video"]),
    PRYXComfyUIHiggsfieldReferenceToVideo: new Set(["reference_to_video"]),
    PRYXComfyUIHiggsfieldVideoEdit: new Set(["video_edit", "video_motion"]),
    PRYXComfyUIHiggsfieldVideoExtend: new Set(["video_extend"]),
};
GENERATOR_CAPABILITIES.PRYXComfyUIHiggsfieldAdvancedRequest = new Set(Object.values(GENERATOR_CAPABILITIES).flatMap((set) => [...set]));
const NODE_UI_SCHEMA_VERSION = 6;

const ALWAYS_VISIBLE_WIDGETS = new Set(["model", "request_mode", "max_usd", "auto_save", "timeout", "model_info", "arguments_json"]);
const MEDIA_PARAMETER_NAMES = new Set([
    "image_url",
    "end_image_url",
    "last_image_url",
    "first_frame_url",
    "last_frame_url",
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
        console[error ? "error" : "info"]("[PRYX ComfyUI Higgsfield] " + message);
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
    const overlay = document.getElementById("pryx-comfyui-higgsfield-credentials");
    if (!overlay) return;
    overlay.__pryxClose?.();
    overlay.remove();
}

function openCredentialDialog(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    closeCredentialDialog();

    const overlay = document.createElement("div");
    overlay.id = "pryx-comfyui-higgsfield-credentials";
    overlay.setAttribute("role", "presentation");
    overlay.style.cssText =
        "position: fixed; inset: 0; z-index: 10000; display: grid; " +
        "place-items: center; padding: 24px; background: rgba(0, 0, 0, 0.68);";

    const panel = document.createElement("section");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "pryx-comfyui-higgsfield-credentials-title");
    panel.style.cssText =
        "width: min(520px, 100%); box-sizing: border-box; padding: 24px; " +
        "border: 1px solid var(--border-color, #4b5563); border-radius: 14px; " +
        "background: var(--interface-panel-surface, #202124); color: var(--fg-color, #fff); " +
        "box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5); font-family: inherit;";
    panel.innerHTML =
        '<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:16px;">' +
        '<div>' +
        '<h2 id="pryx-comfyui-higgsfield-credentials-title" style="margin:0 0 8px; font-size:1.15rem;">PRYX ComfyUI Higgsfield credentials</h2>' +
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
    node.properties.pryx_comfyui_higgsfield_status = {
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

const PARAMETER_HINTS = {
    aigc_watermark: "Include the provider's AI-generated-content watermark.",
    aspect_ratio: "Output framing for this model.",
    bitrate_mode: "Encoded video bitrate tier.",
    camera_movement: "Camera motion preset.",
    cfg_scale: "How strongly the model follows the prompt.",
    duration: "Video duration in seconds.",
    elements: "JSON array of provider element IDs.",
    generate_audio: "Generate or include audio where supported.",
    keep_original_sound: "Keep the source video's sound.",
    mode: "Provider quality tier, separate from request_mode (estimate or paid generation).",
    multi_prompt: "JSON array of shot objects with prompt and duration.",
    negative_prompt: "Things the model should avoid showing.",
    output_format: "Output container format.",
    resolution: "Provider resolution tier, not a width × height input.",
    seed: "Optional deterministic seed; -1 omits it.",
    sound: "Provider soundtrack setting.",
};

function parameterTooltip(parameter) {
    const pieces = [];
    const generic = parameter.description?.trim().toLowerCase().replaceAll("_", " ") === parameter.name.replaceAll("_", " ");
    pieces.push(!parameter.description || generic ? (PARAMETER_HINTS[parameter.name] || "Model-specific parameter.") : parameter.description);
    if (parameter.choices?.length) pieces.push("Choices: " + parameter.choices.join(", "));
    if (parameter.minimum != null || parameter.maximum != null) {
        pieces.push(`Range: ${parameter.minimum ?? "-∞"}–${parameter.maximum ?? "∞"}`);
    }
    if (parameter.min_items != null || parameter.max_items != null) {
        pieces.push(`Items: ${parameter.min_items ?? 0}–${parameter.max_items ?? "∞"}`);
    }
    if (parameter.min_length != null || parameter.max_length != null) {
        pieces.push(`Characters: ${parameter.min_length ?? 0}–${parameter.max_length ?? "∞"}`);
    }
    if (parameter.multiple_of != null) pieces.push(`Step: ${parameter.multiple_of}`);
    return pieces.join(" ");
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
    if (["integer", "number"].includes(parameter.type)) widget.options.step = parameter.multiple_of ?? (parameter.type === "integer" ? 1 : 0.01);
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
        request_mode: "estimate_only",
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
    if (!model) return "Choose a model from the validated PRYX ComfyUI Higgsfield catalog.";
    const media = model.input_media?.length ? model.input_media.join(", ") : "none";
    const limit = model.max_references == null ? "see per-input limits below" : `up to ${model.max_references}`;
    return `${model.display_name} (${model.id}). Capability: ${model.capability}. Supported references: ${media}; ${limit} total reference(s).`;
}

function updateMediaInputs(node, model) {
    const supported = new Set(model?.input_media || []);
    for (const input of node.inputs || []) {
        if (!MEDIA_INPUT_NAMES.has(input.name)) continue;
        const visible = input.name === "references" ? supported.size > 0 : input.name === "end_image"
            ? model?.parameters?.some((p) => ["end_image_url", "last_image_url", "last_frame_url"].includes(p.name))
            : supported.has(input.name);
        input.hidden = !visible;
        input.tooltip = visible
            ? input.name === "references"
                ? "Combined media from Reference Collector. Direct media inputs are added to this collection; all inputs share the model limits."
                : input.name === "image" && model?.parameters?.some((p) => ["image_url", "first_frame_url"].includes(p.name))
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
    image_url: "Start/source image", first_frame_url: "Start frame",
    end_image_url: "End image", last_image_url: "End image", last_frame_url: "End frame",
    image_urls: "Reference images", video_url: "Source video", video_urls: "Reference videos",
    audio_url: "Audio track", audio_urls: "Reference audio tracks",
    file_url: "Document link", link_url: "Web page link",
};

function schemaConditionLines(schema, prefix = "") {
    if (!schema || typeof schema !== "object") return [];
    const lines = [];
    const required = (rule) => (rule?.required || []).map((name) => MEDIA_LABELS[name] || name).join(" + ");
    const constraints = (rule) => Object.entries(rule?.properties || {}).flatMap(([name, value]) => {
        const label = MEDIA_LABELS[name] || name;
        const details = [];
        if (Object.hasOwn(value, "const")) details.push(`must equal ${JSON.stringify(value.const)}`);
        if (value.minItems != null || value.maxItems != null) details.push(`${value.minItems ?? 0}–${value.maxItems ?? "∞"} items`);
        if (value.minimum != null || value.maximum != null) details.push(`range ${value.minimum ?? "-∞"}–${value.maximum ?? "∞"}`);
        return details.length ? [`${label}: ${details.join(", ")}`] : [];
    });
    const conditions = [];
    for (const name of schema.if?.required || []) conditions.push(`${MEDIA_LABELS[name] || name} supplied`);
    for (const [name, rule] of Object.entries(schema.if?.properties || {})) {
        if (Object.hasOwn(rule, "const")) conditions.push(`${name} = ${String(rule.const)}`);
    }
    if (schema.if) {
        const subject = conditions.join(" and ") || "the schema condition is met";
        if (required(schema.then)) lines.push(`${prefix}When ${subject}: require ${required(schema.then)}.`);
        else if (required(schema.else) && conditions.length) lines.push(`${prefix}When ${subject}: this reference branch is satisfied; other required fields still apply.`);
        for (const limit of constraints(schema.then)) lines.push(`${prefix}When ${subject}: ${limit}.`);
        if (required(schema.else)) lines.push(`${prefix}Otherwise: require ${required(schema.else)}.`);
        for (const limit of constraints(schema.else)) lines.push(`${prefix}Otherwise: ${limit}.`);
        lines.push(...schemaConditionLines(schema.then, `${prefix}When ${subject}: `));
        lines.push(...schemaConditionLines(schema.else, `${prefix}Otherwise: `));
    }
    for (const item of schema.allOf || []) lines.push(...schemaConditionLines(item, prefix));
    return lines;
}

function nestedSchemaLimits(schema, prefix = "", depth = 0) {
    if (!schema || depth > 3) return [];
    const lines = [];
    if (schema.type === "array" && schema.items) {
        lines.push(...nestedSchemaLimits(schema.items, `${prefix}each item`, depth + 1));
    }
    for (const [name, property] of Object.entries(schema.properties || {})) {
        const parts = [];
        if (property.type) parts.push(property.type);
        if (property.enum) parts.push(`choices ${property.enum.join(" / ")}`);
        if (property.minLength != null || property.maxLength != null) parts.push(`characters ${property.minLength ?? 0}–${property.maxLength ?? "∞"}`);
        if (property.minimum != null || property.maximum != null) parts.push(`range ${property.minimum ?? "-∞"}–${property.maximum ?? "∞"}`);
        if (property.minItems != null || property.maxItems != null) parts.push(`items ${property.minItems ?? 0}–${property.maxItems ?? "∞"}`);
        if (property.multipleOf != null) parts.push(`step ${property.multipleOf}`);
        lines.push(`${prefix ? prefix + "." : ""}${name}: ${parts.join(", ") || "nested field"}${schema.required?.includes(name) ? " · required" : ""}`);
        lines.push(...nestedSchemaLimits(property, `${prefix ? prefix + "." : ""}${name}`, depth + 1));
    }
    return lines;
}

function normalizeCoreWidgetValues(node) {
    const numericWidgets = {
        max_usd: { defaultValue: 0, minimum: 0, maximum: 10000 },
        timeout: { defaultValue: 1800, minimum: 10, maximum: 7200 },
    };
    for (const widget of node.widgets || []) {
        const limits = numericWidgets[widget.name];
        if (!limits) continue;
        const numericValue = Number(widget.value);
        const valid = Number.isFinite(numericValue) &&
            numericValue >= limits.minimum && numericValue <= limits.maximum;
        setWidgetValue(node, widget, valid ? numericValue : limits.defaultValue);
    }
}

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
        // Keep the potentially long model documentation collapsed by default.
        // A deliberate user expansion is still remembered for this node.
        details.open = node.properties?.pryx_model_info_expanded === true;
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
    lines.push("", "MODEL PARAMETERS");
    for (const p of model.parameters.filter((item) => !item.media_types?.length)) {
        lines.push(`${p.name}: ${parameterTooltip(p)}${p.required ? " Required." : ""}${p.default != null && p.default !== "" ? ` Default: ${JSON.stringify(p.default)}.` : ""}`);
        if (["array", "object"].includes(p.type)) {
            lines.push(...nestedSchemaLimits(model.input_schema?.properties?.[p.name], p.name).map((line) => `  ${line}`));
        }
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
    const conditions = schemaConditionLines(model.input_schema);
    if (conditions.length) lines.push("", "CONDITIONAL INPUTS", ...conditions);
    if (model.notes?.length) lines.push("", "MODEL NOTES", ...model.notes.map(readableModelNote));
    if (media.length) {
        lines.push("", "PROMPT REFERENCES",
            "Use Reference Preview to inspect the actual media order without uploading or generating.",
            "Direct media inputs come first, followed by Collector slots in numeric order. Images, videos and audio are numbered separately. Batches keep their order.",
            "One Collector accepts multiple media connections. New empty sockets appear as you connect media. Default names: image_1, image_2, video_1, audio_1.",
            "Optional custom names: enter image_1=person and image_2=outfit on separate lines in the Collector names field. Batches use name[1], name[2], etc.");
        if (model.id === "wan-3-reference-to-video") {
            lines.push("Confirmed syntax: Image 1, Image 2, Video 1, Audio 1 (no @ or angle brackets).",
                "Named prompt example: Use {{ref:person}} for the character and {{ref:camera}} for camera movement.",
                "The plugin replaces names with the correct model tokens before upload. Unknown or duplicate names and missing numbered references stop the request.");
        } else {
            lines.push("This endpoint does not document an exact prompt reference syntax. @ mentions and angle-bracket tokens are not verified. Named {{ref:label}} aliases are blocked; plain prompts remain available. Preview numbering describes delivery order, not confirmed prompt syntax.");
        }
        lines.push("Connect Preview's prompt, references and model outputs to the generator. Do not connect the same media again at the generator.");
    }
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
    node.properties.pryx_comfyui_higgsfield_model_info = selected ? {
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
        normalizeCoreWidgetValues(node);
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
        const previousModelInfo = node.properties?.pryx_comfyui_higgsfield_model_info;
        const modelChanged = Boolean(previousModelInfo?.id && previousModelInfo.id !== model?.id);
        const legacyWorkflow = node.__pryxLegacyWorkflow === true ||
            node.properties?.pryx_comfyui_higgsfield_ui_schema !== NODE_UI_SCHEMA_VERSION;
        if (legacyWorkflow) resetLegacyWidgetValues(node, parameters);
        for (const widget of node.widgets || []) {
            if (widget.name === "request_mode") {
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
        node.properties.pryx_comfyui_higgsfield_model_info = model ? {
            id: model.id,
            display_name: model.display_name,
            capability: model.capability,
            provider: model.provider,
            input_media: model.input_media || [],
            max_references: model.max_references ?? null,
            tooltip: modelTooltip(model),
        } : null;
        node.properties.pryx_comfyui_higgsfield_active_parameters = [...parameters.keys()];
        node.properties.pryx_comfyui_higgsfield_ui_schema = NODE_UI_SCHEMA_VERSION;
        node.__pryxLegacyWorkflow = false;
        if (!node.__pryxInfoSized) {
            const size = node.computeSize?.();
            if (size) node.setSize?.([Math.max(node.size?.[0] || 0, 360), Math.max(node.size?.[1] || 0, size[1])]);
            node.__pryxInfoSized = true;
        }
        node.setDirtyCanvas?.(true, true);
        attachCatalogCallbacks(node);
    } catch (error) {
        console.debug("[PRYX ComfyUI Higgsfield] catalog widget update skipped", error);
    }
}

async function updateSoulStyleWidget(node) {
    const widget = node.widgets?.find((item) => item.name === "style_id");
    if (!widget) return;
    try {
        const id = node.widgets?.find((item) => item.name === "model")?.value;
        if (!["soul-2", "soul-standard"].includes(id)) return;
        const result = await requestJson("/pryx-comfyui-higgsfield/styles?variant=" + (id === "soul-2" ? "soul-2" : "soul"));
        widget.options.values = (result.styles || []).map((item) => item.style_id);
    } catch (error) {
        console.debug("[PRYX ComfyUI Higgsfield] style widget update skipped", error);
    }
}

const COLLECTOR_SLOT_LIMITS = { image: 30, video: 10, audio: 10 };

function syncCollectorInputs(node) {
    if (node.__pryxCollectorSyncing) return;
    node.__pryxCollectorSyncing = true;
    try {
        for (const [kind, limit] of Object.entries(COLLECTOR_SLOT_LIMITS)) {
            const slotIndex = (input) => input.name === kind ? 1
                : new RegExp(`^${kind}_(\\d+)$`).exec(input.name)?.[1] * 1 || 0;
            const connected = (node.inputs || []).filter((input) => slotIndex(input) && input.link != null);
            const last = Math.max(0, ...connected.map(slotIndex));
            const visible = Math.min(limit, Math.max(kind === "image" ? 2 : 1, last + 1));
            // Remove only unused trailing sockets. Connected slots keep their names and links.
            for (let i = (node.inputs?.length || 0) - 1; i >= 0; i--) {
                if (slotIndex(node.inputs[i]) > visible && node.inputs[i].link == null) node.removeInput(i);
            }
            for (let index = 1; index <= visible; index++) {
                const name = index === 1 ? kind : `${kind}_${index}`;
                let input = node.inputs?.find((item) => item.name === name);
                if (!input) {
                    node.addInput(name, kind.toUpperCase());
                    input = node.inputs?.find((item) => item.name === name);
                }
                if (input) {
                    input.label = `${kind}_${index}`;
                    input.tooltip = `${kind}_${index}: collected in numeric socket order. Use names to assign a custom label. Model limits apply to all connected media combined.`;
                }
            }
        }
        const legacy = node.widgets?.find((widget) => widget.name === "label");
        if (legacy) setWidgetVisibility(legacy, Boolean(legacy.value));
        const size = node.computeSize?.();
        if (size) node.setSize?.([Math.max(360, node.size?.[0] || 0), size[1]]);
        node.setDirtyCanvas?.(true, true);
    } finally {
        node.__pryxCollectorSyncing = false;
    }
}

function attachReferenceCollector(node) {
    if (!nodeTypeName(node).replace(/\s+/g, "").includes("PRYXComfyUIHiggsfieldReferenceCollector")) return;
    // A browser reload may load this script while Python still runs the old schema.
    if (!node.widgets?.some((widget) => widget.name === "names")) return;
    if (!node.__pryxCollectorAttached) {
        node.__pryxCollectorAttached = true;
        const previous = node.onConnectionsChange;
        node.onConnectionsChange = function (...args) {
            const result = previous?.apply(this, args);
            if (!node.__pryxCollectorSyncing && !node.__pryxCollectorPending) {
                node.__pryxCollectorPending = true;
                queueMicrotask(() => {
                    node.__pryxCollectorPending = false;
                    syncCollectorInputs(node);
                });
            }
            return result;
        };
    }
    syncCollectorInputs(node);
}

function attachReferencePreview(node) {
    if (!nodeTypeName(node).replace(/\s+/g, "").includes("PRYXComfyUIHiggsfieldReferencePreview") || node.__pryxPreviewAttached) return;
    node.__pryxPreviewAttached = true;
    const element = document.createElement("div");
    element.style.cssText = "white-space:pre-wrap;padding:10px;overflow:auto;font:12px/1.5 sans-serif;";
    element.textContent = "Run this node to inspect reference order and prompt expansion. No upload or API call. Connect prompt, references and model outputs to the generator; do not add the same media twice. Disconnect downstream generators for a preview-only run.";
    const widget = node.addDOMWidget("reference_preview", "pryx_reference_preview", element, { serialize: false });
    widget.computeSize = () => [340, 240];
    widget.options.getMinHeight = () => 240;
    const original = node.onExecuted;
    node.onExecuted = function (message) {
        const result = original?.apply(this, arguments);
        element.textContent = "LAST EXECUTION — rerun after changing inputs, labels or model\n\n" + (message?.text || []).join("\n");
        node.setDirtyCanvas?.(true, true);
        return result;
    };
}

app.registerExtension({
    name: "PRYX.ComfyUI.Higgsfield",
    settings: [
        {
            id: "PRYX.ComfyUI.Higgsfield.Credentials",
            name: "Higgsfield API credentials",
            category: ["PRYX ComfyUI Higgsfield", "Credentials"],
            type: createCredentialSetting,
            defaultValue: false,
        },
        {
            id: "PRYX.ComfyUI.Higgsfield.CatalogRefresh",
            name: "Model catalog",
            category: ["PRYX ComfyUI Higgsfield", "Catalog"],
            type: createCatalogRefreshSetting,
            defaultValue: false,
        },
    ],
    setup() {
        api?.addEventListener?.("pryx_comfyui_higgsfield.progress", handleProgress);
        // Trigger one read so settings/catalog errors are visible in the
        // browser console without placing credentials in the page.
        requestJson(CATALOG_ROUTE).catch(() => {});
    },
    nodeCreated(node) {
        attachReferenceCollector(node);
        attachReferencePreview(node);
        if (modelCapabilitiesForNode(node) || nodeTypeName(node).replace(/\s+/g, "").includes("PRYXComfyUIHiggsfieldModelCatalog")) {
            updateCatalogWidgets(node);
            updateSoulStyleWidget(node);
        }
    },
    loadedGraphNode(node) {
        attachReferenceCollector(node);
        attachReferencePreview(node);
        if (!modelCapabilitiesForNode(node) && !nodeTypeName(node).replace(/\s+/g, "").includes("PRYXComfyUIHiggsfieldModelCatalog")) return;
        node.__pryxLoadedGraphNode = true;
        node.__pryxLegacyWorkflow = node.properties?.pryx_comfyui_higgsfield_ui_schema !== NODE_UI_SCHEMA_VERSION;
        updateCatalogWidgets(node);
        updateSoulStyleWidget(node);
    },
});
