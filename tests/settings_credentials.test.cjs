const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../pryx_comfyui_higgsfield/web/js/settings.js'), 'utf8');

function loadCredentialSettings(context) {
    const start = source.indexOf('const SETTINGS_ROUTE =');
    const end = source.indexOf('\nasync function refreshCatalog()', start);
    assert.notEqual(start, -1);
    assert.notEqual(end, -1);
    vm.createContext(context);
    vm.runInContext(source.slice(start, end), context);
    return context;
}

test('combined Higgsfield key splits at the first colon and trims pasted whitespace', () => {
    const context = loadCredentialSettings({
        document: { querySelectorAll: () => [] },
        fetch: async () => ({ ok: true, json: async () => ({}) }),
    });
    const parsed = context.splitCombinedApiKey('  key-id : secret:with:colon  ');

    assert.equal(parsed.key_id, 'key-id');
    assert.equal(parsed.secret, 'secret:with:colon');
});

test('combined Higgsfield key rejects missing ID or secret without echoing input', () => {
    const context = loadCredentialSettings({
        document: { querySelectorAll: () => [] },
        fetch: async () => ({ ok: true, json: async () => ({}) }),
    });

    for (const value of ['', 'id-only', ':secret', 'id:']) {
        assert.throws(
            () => context.splitCombinedApiKey(value),
            { message: 'Paste the full Higgsfield API key in KEY_ID:SECRET format.' },
        );
    }
});

test('saving a combined key stores both parts, clears and closes the dialog, and refreshes status', async () => {
    const requests = [];
    const statusElement = { textContent: 'Checking...' };
    const form = {
        elements: {
            api_key: { value: 'test-id:test-secret', focus() {} },
            status: { textContent: '' },
        },
        addEventListener() {},
    };
    const buttons = new Map();
    const document = {
        activeElement: null,
        body: {
            appendChild(element) {
                element.parent = this;
                this.overlay = element;
            },
        },
        createElement(tag) {
            return {
                tag,
                style: {},
                listeners: {},
                attributes: {},
                setAttribute(name, value) { this.attributes[name] = value; },
                addEventListener(name, callback) { this.listeners[name] = callback; },
                appendChild(element) { this.children = [...(this.children || []), element]; },
                querySelector(selector) {
                    if (selector === 'form') return form;
                    return buttons.get(selector);
                },
                remove() { this.removed = true; },
            };
        },
        getElementById() { return null; },
        querySelectorAll(selector) {
            if (selector === '[data-pryx-comfyui-higgsfield-credential-status]') return [statusElement];
            return [];
        },
        querySelector() { return null; },
        addEventListener() {},
        removeEventListener() {},
    };
    for (const action of ['close', 'cancel', 'validate', 'save']) {
        buttons.set(`[data-action="${action}"]`, {
            addEventListener(name, callback) { this[name] = callback; },
        });
    }

    const context = loadCredentialSettings({
        document,
        app: {},
        console,
        fetch: async (url, options) => {
            requests.push({ url, options });
            return {
                ok: true,
                json: async () => ({ configured: true, source: 'local', key_id: 'te…id' }),
            };
        },
    });

    context.openCredentialDialog();
    const overlay = document.body.overlay;
    await buttons.get('[data-action="save"]').click();

    assert.equal(requests.length, 1);
    assert.equal(requests[0].options.method, 'PUT');
    assert.deepEqual(JSON.parse(requests[0].options.body), {
        key_id: 'test-id',
        secret: 'test-secret',
    });
    assert.equal(form.elements.api_key.value, '');
    assert.equal(overlay.removed, true);
    assert.equal(statusElement.textContent, 'Configured (te…id)');
});
