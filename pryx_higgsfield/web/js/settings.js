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
        notify("Catalog refreshed: " + result.catalog_version);
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

async function updateCatalogWidgets(node) {
    try {
        const catalog = await requestJson(CATALOG_ROUTE);
        const models = catalog.models || [];
        const widget = node.widgets?.find((item) => item.name === "model");
        if (widget && models.length) {
            const nodeName = node.type || "";
            let values = models.filter((item) => item.status === "active");
            if (nodeName.includes("TextToVideo")) values = values.filter((item) => item.capability === "text_to_video");
            if (nodeName.includes("ImageToVideo")) values = values.filter((item) => item.capability === "image_to_video");
            if (nodeName.includes("ReferenceToVideo")) values = values.filter((item) => item.capability === "reference_to_video");
            if (nodeName.includes("VideoEdit")) values = values.filter((item) => item.capability === "video_edit");
            if (nodeName.includes("VideoExtend")) values = values.filter((item) => item.capability === "video_extend");
            if (nodeName.includes("ImageGenerateEdit")) values = values.filter((item) => item.output === "image");
            widget.options.values = values.map((item) => item.id);
            if (!widget.options.values.includes(widget.value)) widget.value = widget.options.values[0];
        }
    } catch (error) {
        console.debug("[PRYX Higgsfield] catalog widget update skipped", error);
    }
}

async function updateSoulStyleWidget(node) {
    const widget = node.widgets?.find((item) => item.name === "style_id");
    if (!widget) return;
    try {
        const result = await requestJson("/pryx-higgsfield/styles?variant=soul-2");
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
        if (node.type?.startsWith("PRYXHiggsfield")) {
            updateCatalogWidgets(node);
            updateSoulStyleWidget(node);
        }
    },
});
