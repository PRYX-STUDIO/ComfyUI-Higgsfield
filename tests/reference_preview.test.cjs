const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../pryx_higgsfield/web/js/settings.js'), 'utf8');
const models = JSON.parse(fs.readFileSync(path.join(__dirname, '../pryx_higgsfield/catalog/models.json'), 'utf8')).models;

function fixture() {
    const elements = [];
    const context = { nodeTypeName: (node) => node.type, document: { createElement(tag) {
        const element = { tag, style: {}, children: [], setAttribute() {},
            append(...items) { this.children.push(...items); },
            addEventListener(name, callback) { this[name] = callback; } };
        elements.push(element);
        return element;
    } } };
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('const MEDIA_LABELS ='), source.indexOf('function updateModelCatalogNode')), context);
    vm.runInContext(source.slice(source.indexOf('function attachReferencePreview'), source.indexOf('app.registerExtension')), context);
    const node = { type: 'PRYXHiggsfieldReferencePreview', widgets: [], properties: {},
        addDOMWidget(name, type, element, options) {
            const widget = { name, element, options };
            this.widgets.push(widget);
            return widget;
        }, computeSize() { return [340, 240]; }, setSize() {}, setDirtyCanvas() {} };
    return { context, node, elements };
}

test('model info distinguishes confirmed Wan tokens from unconfirmed Seedance syntax', () => {
    const { context, node } = fixture();
    context.updateModelInfo(node, models.find(m => m.id === 'wan-3-reference-to-video'));
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /Confirmed syntax: Image 1/);
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /\{\{ref:person\}\}/);
    context.updateModelInfo(node, models.find(m => m.id === 'seedance-2-5-reference-to-video'));
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /aliases are blocked/);
    assert.doesNotMatch(node.widgets[0].__pryxInfoElement.textContent, /Confirmed syntax:/);
});

test('preview displays backend mapping as text and identifies it as last execution', () => {
    const { context, node } = fixture();
    context.attachReferencePreview(node);
    context.attachReferencePreview(node);
    assert.equal(node.widgets.length, 1);
    assert.match(node.widgets[0].element.textContent, /Disconnect downstream generators/);
    node.onExecuted({ text: ['Image 2 ← <person>\nUse Image 2'] });
    assert.match(node.widgets[0].element.textContent, /LAST EXECUTION/);
    assert.match(node.widgets[0].element.textContent, /Image 2 ← <person>/);
    assert.equal(node.widgets[0].element.innerHTML, undefined);
});
