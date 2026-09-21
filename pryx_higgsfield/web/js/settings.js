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
    if (globalThis.app?.ui?.dialog) {
        globalThis.app.ui.dialog.show(message);
    } else {
        console[error ? "error" : "info"]("[PRYX Higgsfield] " + message);
    }
}

function openCredentialDialog() {
    const existing = document.getElementById("pryx-higgsfield-credentials");
    if (existing) existing.remove();

    const dialog = document.createElement("dialog");
    dialog.id = "pryx-higgsfield-credentials";
    dialog.innerHTML =
        '<form method="dialog" style="min-width: 360px">' +
        '<h3>PRYX Higgsfield credentials</h3>' +
        '<p>The secret is stored locally by ComfyUI and is never included in a workflow.</p>' +
        '<label>Key ID<br><input name="key_id" autocomplete="off" required></label><br>' +
        '<label>Secret<br><input name="secret" type="password" autocomplete="new-password" required></label><br>' +
        '<output name="status" style="display:block; min-height:1.5em"></output>' +
        '<button value="cancel">Cancel</button>' +
        '<button type="button" data-action="validate">Validate estimate</button>' +
        '<button type="button" data-action="save">Save locally</button>' +
        '</form>';
    document.body.appendChild(dialog);
    const form = dialog.querySelector("form");
    const status = form.elements.status;
    const values = () => ({
        key_id: form.elements.key_id.value,
        secret: form.elements.secret.value,
    });
    form.querySelector('[data-action="validate"]').addEventListener("click", async () => {
        status.textContent = "Validating...";
        try {
            const result = await requestJson(VALIDATE_ROUTE, { method: "POST", body: JSON.stringify(values()) });
            status.textContent = "Valid. Estimate: " + (result.credits ?? "n/a") + " credits / " + (result.usd ?? "n/a") + " USD.";
        } catch (error) {
            status.textContent = error.message;
        }
    });
    form.querySelector('[data-action="save"]').addEventListener("click", async () => {
        status.textContent = "Saving...";
        try {
            await requestJson(SETTINGS_ROUTE, { method: "PUT", body: JSON.stringify(values()) });
            form.elements.secret.value = "";
            status.textContent = "Saved locally. The secret was cleared from the form.";
        } catch (error) {
            status.textContent = error.message;
        }
    });
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    dialog.showModal();
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
    if (!data || !globalThis.app?.graph) return;
    const node = data.node_id ? globalThis.app.graph.getNodeById?.(Number(data.node_id)) : null;
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
            id: "pryx_higgsfield.credentials",
            name: "PRYX Higgsfield: Credentials",
            type: "button",
            text: "Manage",
            action: openCredentialDialog,
        },
        {
            id: "pryx_higgsfield.catalog_refresh",
            name: "PRYX Higgsfield: Refresh catalog",
            type: "button",
            text: "Refresh",
            action: refreshCatalog,
        },
    ],
    setup() {
        globalThis.api?.addEventListener?.("pryx_higgsfield.progress", handleProgress);
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
