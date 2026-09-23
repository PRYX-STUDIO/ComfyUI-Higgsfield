const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../pryx_comfyui_higgsfield/web/js/settings.js'), 'utf8');

function fixture() {
    const factories = {};
    for (const [factoryType, widgetType] of Object.entries({
        COMBO: 'combo', FLOAT: 'number', INT: 'number', STRING: 'text', BOOLEAN: 'toggle',
    })) {
        factories[factoryType] = (node, name, inputData) => {
            const options = inputData[inputData.length - 1] || {};
            const widget = { name, type: widgetType, value: options.default, options: { ...options } };
            node.widgets.push(widget);
            return { widget };
        };
    }

    const context = { ComfyWidgets: factories, app: {} };
    vm.createContext(context);
    const start = source.indexOf('const PARAMETER_HINTS =');
    const end = source.indexOf('function modelTooltip', start);
    assert.notEqual(start, -1);
    assert.notEqual(end, -1);
    vm.runInContext(source.slice(start, end), context);
    return context;
}

function makeNode(widget) {
    const before = { name: 'before', type: 'text', value: 'a' };
    const after = { name: 'after', type: 'text', value: 'b' };
    return {
        widgets: [before, widget, after],
        widgets_values: ['a', widget.value, 'b'],
    };
}

test('a dynamic duration dropdown becomes a native, working numeric widget', () => {
    const context = fixture();
    const oldWidget = { name: 'duration', type: 'combo', value: 7, options: { values: [5, 7, 10], widgetType: 'COMBO' } };
    const node = makeNode(oldWidget);
    let removed = false;
    oldWidget.onRemove = () => { removed = true; };

    const parameter = { name: 'duration', type: 'integer', default: 5, minimum: 1, maximum: 15 };
    const widget = context.setWidgetFromParameter(node, oldWidget, parameter);

    assert.equal(widget.type, 'number');
    assert.equal(widget.value, 7);
    assert.equal(widget.options.min, 1);
    assert.equal(widget.options.max, 15);
    assert.equal(widget.options.step, 1);
    assert.deepEqual(node.widgets.map(item => item.name), ['before', 'duration', 'after']);
    assert.equal(node.widgets_values[1], 7);
    assert.equal(removed, true);

    assert.strictEqual(context.setWidgetFromParameter(node, widget, parameter), widget);
});

test('switching the same field back to enumerated durations restores a native dropdown', () => {
    const context = fixture();
    const oldWidget = { name: 'duration', type: 'number', value: 10, options: { min: 5, max: 15, step: 1 } };
    const node = makeNode(oldWidget);
    const parameter = { name: 'duration', type: 'integer', default: 5, choices: [5, 10, 15] };

    const widget = context.setWidgetFromParameter(node, oldWidget, parameter);

    assert.equal(widget.type, 'combo');
    assert.equal(widget.value, 10);
    assert.deepEqual(widget.options.values, [5, 10, 15]);
    assert.deepEqual(node.widgets.map(item => item.name), ['before', 'duration', 'after']);
    assert.equal(node.widgets_values[1], 10);
});

test('duration outside a newly selected model range resets to its supported default', () => {
    const context = fixture();
    const oldWidget = { name: 'duration', type: 'combo', value: 30, options: { values: [5, 10, 30], widgetType: 'COMBO' } };
    const node = makeNode(oldWidget);
    const parameter = { name: 'duration', type: 'integer', default: 5, minimum: 1, maximum: 15 };

    const widget = context.setWidgetFromParameter(node, oldWidget, parameter);

    assert.equal(widget.type, 'number');
    assert.equal(widget.value, 5);
    assert.equal(node.widgets_values[1], 5);
});
