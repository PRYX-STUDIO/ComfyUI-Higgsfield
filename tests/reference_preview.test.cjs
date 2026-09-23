const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../pryx_comfyui_higgsfield/web/js/settings.js'), 'utf8');
const models = JSON.parse(fs.readFileSync(path.join(__dirname, '../pryx_comfyui_higgsfield/catalog/models.json'), 'utf8')).models;

function fixture() {
    const elements = [];
    const animationFrames = [];
    const context = { nodeTypeName: (node) => node.type, queueMicrotask,
        requestAnimationFrame(callback) { animationFrames.push(callback); },
        setWidgetVisibility(widget, visible) { widget.hidden = !visible; },
        setWidgetValue(node, widget, value) {
            widget.value = value;
            const index = node.widgets?.indexOf(widget) ?? -1;
            if (index >= 0 && Array.isArray(node.widgets_values)) node.widgets_values[index] = value;
        }, document: { createElement(tag) {
        const element = { tag, style: {}, children: [], setAttribute() {},
            append(...items) { this.children.push(...items); },
            addEventListener(name, callback) { this[name] = callback; } };
        elements.push(element);
        return element;
    } } };
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('const PARAMETER_HINTS ='), source.indexOf('function modelTooltip')), context);
    vm.runInContext(source.slice(source.indexOf('const MEDIA_LABELS ='), source.indexOf('function updateModelCatalogNode')), context);
    vm.runInContext(source.slice(source.indexOf('function attachReferencePreview'), source.indexOf('app.registerExtension')), context);
    vm.runInContext(source.slice(source.indexOf('const COLLECTOR_SLOT_LIMITS'), source.indexOf('function attachReferencePreview')), context);
    const node = { type: 'PRYXComfyUIHiggsfieldReferencePreview', widgets: [], properties: {},
        size: [500, 720],
        addDOMWidget(name, type, element, options) {
            const widget = { name, element, options };
            this.widgets.push(widget);
            return widget;
        }, computeSize() { return [340, 240]; }, setSize(size) { this.size = size; }, setDirtyCanvas() {} };
    return { context, node, elements, animationFrames };
}

test('initial node fitting shrinks a stale saved height to its current collapsed content', () => {
    const { context, node } = fixture();
    context.fitNodeToContent(node);
    assert.equal(node.size[0], 500);
    assert.equal(node.size[1], 240);
});

test('loaded nodes are fitted after graph restoration and DOM layout settle', () => {
    const { context, node, animationFrames } = fixture();
    context.scheduleNodeFitAfterLoad(node);
    assert.equal(node.size[1], 720);
    assert.equal(animationFrames.length, 1);
    animationFrames.shift()();
    assert.equal(node.size[1], 720);
    assert.equal(animationFrames.length, 1);
    animationFrames.shift()();
    assert.equal(node.size[0], 500);
    assert.equal(node.size[1], 240);
});

test('model info distinguishes confirmed Wan tokens from unconfirmed Seedance syntax', () => {
    const { context, node } = fixture();
    context.updateModelInfo(node, models.find(m => m.id === 'wan-3-reference-to-video'));
    assert.equal(node.widgets[0].element.children[0].open, false);
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /Confirmed syntax: Image 1/);
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /\{\{ref:person\}\}/);
    context.updateModelInfo(node, models.find(m => m.id === 'seedance-2-5-reference-to-video'));
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /aliases are blocked/);
    assert.doesNotMatch(node.widgets[0].__pryxInfoElement.textContent, /Confirmed syntax:/);
});

test('empty safety widgets are normalized to numeric defaults', () => {
    const { context } = fixture();
    const node = {
        widgets: [
            { name: 'max_usd', value: '' },
            { name: 'timeout', value: '' },
        ],
        widgets_values: ['', ''],
    };
    context.normalizeCoreWidgetValues(node);
    assert.equal(node.widgets[0].value, 0);
    assert.equal(node.widgets[1].value, 1800);
    assert.deepEqual(node.widgets_values, [0, 1800]);
});

test('image-edit model info also explains reference order and naming', () => {
    const { context, node } = fixture();
    context.updateModelInfo(node, models.find(m => m.id === 'grok-image-2'));
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /PROMPT REFERENCES/);
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /image_1=person/);
});

test('collector grows sockets and preserves connected slots across reloads', () => {
    const { context, node } = fixture();
    node.type = 'PRYXComfyUIHiggsfieldReferenceCollector';
    node.widgets = [{ name: 'names', value: '' }];
    node.inputs = [];
    node.addInput = (name, type) => node.inputs.push({ name, type, link: null });
    node.removeInput = (index) => node.inputs.splice(index, 1);
    for (const [kind, count] of Object.entries({ image: 30, video: 10, audio: 10 })) {
        for (let i = 1; i <= count; i++) node.addInput(i === 1 ? kind : `${kind}_${i}`, kind.toUpperCase());
    }
    context.attachReferenceCollector(node);
    assert.equal(node.inputs.length, 4);
    assert.equal(node.inputs.find(i => i.name === 'image').label, 'image_1');
    node.inputs.find(i => i.name === 'image_2').link = 42;
    context.syncCollectorInputs(node);
    assert(node.inputs.find(i => i.name === 'image_3'));
    context.attachReferenceCollector(node);
    assert.equal(node.inputs.find(i => i.name === 'image_2').link, 42);
    node.inputs.find(i => i.name === 'image_2').link = null;
    context.syncCollectorInputs(node);
    assert(!node.inputs.find(i => i.name === 'image_3'));
    assert(node.inputs.find(i => i.name === 'image_2'));
});

test('old backend schema does not receive unsupported dynamic sockets', () => {
    const { context, node } = fixture();
    node.type = 'PRYXComfyUIHiggsfieldReferenceCollector';
    node.inputs = [{ name: 'image', type: 'IMAGE', link: null }];
    context.attachReferenceCollector(node);
    assert.equal(node.inputs.length, 1);
    assert.equal(node.__pryxCollectorAttached, undefined);
});

test('every reference-capable model has ordering guidance', () => {
    for (const model of models.filter(m => m.input_media?.length)) {
        const { context, node } = fixture();
        context.updateModelInfo(node, model);
        assert.match(node.widgets[0].__pryxInfoElement.textContent, /PROMPT REFERENCES/, model.id);
    }
});

test('conditional media limits and provider mode are visible for supported models', () => {
    const { context, node } = fixture();
    context.updateModelInfo(node, models.find(m => m.id === 'minimax-h3-reference-to-video'));
    const info = node.widgets[0].__pryxInfoElement.textContent;
    assert.match(info, /Reference images: 1–9/);
    assert.match(info, /Reference videos: 1–3/);
    assert.match(info, /Otherwise: require reference videos/i);
    const kling = models.find(m => m.id === 'kling-video-o3-first-last-frame');
    assert.match(context.parameterTooltip(kling.parameters.find(p => p.name === 'mode')), /Provider quality tier/);
    assert.match(context.parameterTooltip(kling.parameters.find(p => p.name === 'mode')), /std, pro, 4k/);
    context.updateModelInfo(node, models.find(m => m.id === 'marketing-studio-image'));
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /quality: must equal "high"/);
    assert.match(node.widgets[0].__pryxInfoElement.textContent, /Reference images: 1–2 items/);
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
