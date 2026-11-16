/* Studio: a node editor for ffmpeg filtergraphs.
 *
 * The document (S.doc) has the exact shape of the server's FilterGraphDoc; every edit goes through
 * mutate() (undo history, draft autosave) and is compiled by the server, which returns the filtergraph,
 * the command, problems, and how each link is labelled. Pads of filter nodes are computed here from
 * the filter's spec with the same rules as the server (filtergraph/model.py: filter_pads).
 */
(() => {
'use strict';

const API = '/api/studio';
const $ = (id) => document.getElementById(id);
const SVG_NS = 'http://www.w3.org/2000/svg';
const NAME_RE = /^[A-Za-z][A-Za-z0-9_-]{0,31}$/;
const KIND_ICON = { input: 'fa-file-video', output: 'fa-file-export', graph: 'fa-cubes', filter: 'fa-filter' };

function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === 'class') node.className = v;
        else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
        else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'selected') node[k] = v;
        else node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat(Infinity)) if (c != null && c !== false) node.append(c instanceof Node ? c : String(c));
    return node;
}
function svgEl(tag, attrs = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    return node;
}
const icon = (name, cls = '') => el('i', { class: `fas ${name} ${cls}`, 'aria-hidden': 'true' });
const clone = (o) => JSON.parse(JSON.stringify(o));

function errorText(body, fallback) {
    if (!body || body.detail == null) return fallback;
    if (typeof body.detail === 'string') return body.detail;
    return body.detail.map(d => `${(d.loc || []).slice(1).join('.') || 'request'}: ${d.msg}`).join('; ');
}

async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, init);
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) throw new Error(errorText(data, `HTTP ${res.status}`));
    return data;
}

let toastTimer = null;
function toast(message, isError = false) {
    const t = $('toast');
    t.textContent = message;
    t.className = `toast${isError ? ' error' : ''}`;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, isError ? 6000 : 2500);
}

// ------------------------------------------------------------------ ffmpeg escaping (mirrors filtergraph/syntax.py)

const WS = ' \n\t\r';
function escapeValue(v, positional = false) {
    const sp = positional ? "\\':=" : "\\':";
    let out = '';
    for (let i = 0; i < v.length; i++) {
        const c = v[i];
        out += (sp.includes(c) || (WS.includes(c) && (i === 0 || i === v.length - 1))) ? `\\${c}` : c;
    }
    return out;
}
function quoteArgs(a) {
    if (!a) return a;
    if (!/[\[\],;'\\]/.test(a) && !WS.includes(a[0]) && !WS.includes(a[a.length - 1])) return a;
    return a.split("'").map(p => (p ? `'${p}'` : '')).join("\\'");
}
function formatFilter(node) {
    const parts = node.args.map(a => escapeValue(a, true))
        .concat(Object.entries(effectiveOptions(node)).map(([k, v]) => `${k}=${escapeValue(v)}`));
    const joined = quoteArgs(parts.join(':'));
    return joined ? `${node.filter}=${joined}` : node.filter;
}

// ------------------------------------------------------------------ state

const S = {
    doc: { version: 1, nodes: [], edges: [] },
    meta: { id: null, name: 'Untitled graph', description: '', tags: [], revision: null },
    dirty: false,
    sel: { nodes: new Set(), edge: null },
    view: { x: 60, y: 60, k: 1 },
    compiled: null,
    catalog: [],
    catalogByName: new Map(),
    specs: new Map(),
    io: { inputs: [], outputs: [] },
    library: [],
    libById: new Map(),
    examples: [],
    history: { undo: [], redo: [] },
    portOffsets: new Map(),
    nodeSize: new Map(),
    showLabels: true,
    drag: null,
    lastPointer: null,
    optFilter: '',
    optOnlySet: false,
    bindMenu: null,
};

// ------------------------------------------------------------------ pads (mirrors filtergraph/model.py)

function optSpec(spec, name) {
    return spec.options.find(o => o.name === name || o.aliases.includes(name));
}

function filterPads(spec, node) {
    const named = { ...node.options };
    spec.positional.forEach((name, i) => { if (i < node.args.length && !(name in named)) named[name] = node.args[i]; });
    const count = (option, def) => {
        if (!option) return def;
        let raw = named[option];
        if (raw === undefined) {
            const o = optSpec(spec, option);
            if (o) for (const a of o.aliases) if (a in named) raw = named[a];
        }
        return raw !== undefined && /^-?\d+$/.test(raw.trim()) ? Math.max(0, Math.min(64, parseInt(raw, 10))) : def;
    };
    const side = (which) => {
        const rule = which === 'in' ? spec.input_rule : spec.output_rule;
        const listed = which === 'in' ? spec.input_pads : spec.output_pads;
        const prefix = which === 'in' ? 'in' : 'out';
        let pads = [];
        if (rule.kind === 'concat') {
            const n = count('n', 2), v = count('v', 1), a = count('a', 0);
            if (which === 'in') {
                for (let s = 0; s < n; s++) {
                    for (let j = 0; j < v; j++) pads.push({ name: `s${s}.v${j}`, type: 'video' });
                    for (let j = 0; j < a; j++) pads.push({ name: `s${s}.a${j}`, type: 'audio' });
                }
            } else {
                for (let j = 0; j < v; j++) pads.push({ name: `v${j}`, type: 'video' });
                for (let j = 0; j < a; j++) pads.push({ name: `a${j}`, type: 'audio' });
            }
        } else if (rule.kind === 'count') {
            const n = count(rule.option, rule.default);
            for (let i = 0; i < n; i++) pads.push({ name: `${prefix}${i}`, type: rule.type });
        } else {
            pads = listed.map(p => ({ name: p.name, type: p.type }));
            if (rule.kind === 'manual') {
                const extra = which === 'in' ? node.extra_inputs : node.extra_outputs;
                const n = extra == null ? rule.default : extra;
                const base = pads.length;
                for (let i = 0; i < n; i++) pads.push({ name: `${prefix}${base + i}`, type: rule.type });
            }
        }
        return pads.slice(0, 64).map((p, i) => ({ ...p, key: String(i) }));
    };
    return { inputs: side('in'), outputs: side('out') };
}

const INPUT_PADS = [{ key: 'v', name: 'v', type: 'video' }, { key: 'a', name: 'a', type: 'audio' }];

function padsOf(node) {
    if (!node) return { inputs: [], outputs: [] };
    if (node.kind === 'input') return { inputs: [], outputs: INPUT_PADS };
    if (node.kind === 'output') return { inputs: node.pads.map(p => ({ key: p.name, name: p.name, type: p.type })), outputs: [] };
    if (node.kind === 'graph') {
        const g = S.libById.get(node.graph_id);
        return g ? g.interface : (S.compiled?.pads?.[node.id] || { inputs: [], outputs: [] });
    }
    const spec = S.specs.get(node.filter);
    if (spec) return filterPads(spec, { ...node, options: effectiveOptions(node) });
    return S.compiled?.pads?.[node.id] || { inputs: [], outputs: [] };
}

function padsKnown(node) {
    if (node.kind === 'filter') return Boolean(S.specs.get(node.filter));
    if (node.kind === 'graph') return S.libById.has(node.graph_id);
    return true;
}

function padOf(nodeId, side, key) {
    const pads = padsOf(nodeById(nodeId));
    return (side === 'in' ? pads.inputs : pads.outputs).find(p => p.key === key);
}

// ------------------------------------------------------------------ document helpers

const nodeById = (id) => S.doc.nodes.find(n => n.id === id);

function nodeLabel(node) {
    if (!node) return '?';
    if (node.kind === 'filter') return node.id;
    if (node.kind === 'graph') return S.libById.get(node.graph_id)?.name || 'saved graph';
    return `${node.name} (${node.kind})`;
}

function newId(stem) {
    stem = String(stem).replace(/[^A-Za-z0-9_]/g, '') || 'node';
    const ids = new Set(S.doc.nodes.map(n => n.id));
    let i = 1;
    while (ids.has(`${stem}${i}`)) i++;
    return `${stem}${i}`;
}

function uniqueName(kind, base) {
    const names = new Set(S.doc.nodes.filter(n => n.kind === kind).map(n => n.name));
    if (!names.has(base)) return base;
    let i = 2;
    while (names.has(`${base}${i}`)) i++;
    return `${base}${i}`;
}

function makeNode(kind, extra = {}) {
    if (kind === 'input') return { kind, id: newId('in'), name: uniqueName('input', 'in'), options: {}, params: {}, sample_path: null, note: '', position: null };
    if (kind === 'output') {
        return { kind, id: newId('out'), name: uniqueName('output', 'out'), pads: [{ name: 'v', type: 'video' }, { name: 'a', type: 'audio' }],
                 options: {}, params: {}, filename: '{stem}-{output}.mp4', note: '', position: null };
    }
    if (kind === 'graph') return { kind, id: newId('graph'), graph_id: extra.graph_id, options: {}, params: {}, note: '', position: null };
    return { kind: 'filter', id: newId(extra.filter), filter: extra.filter, args: [], options: {}, params: {}, extra_inputs: null, extra_outputs: null, note: '', position: null };
}

// Older drafts and documents may lack the parameter fields.
function normalizeDoc(doc) {
    doc.params = doc.params || [];
    for (const n of doc.nodes) {
        n.params = n.params || {};
        n.options = n.options || {};
    }
    return doc;
}

// ------------------------------------------------------------------ graph parameters

const paramOf = (name) => S.doc.params.find(p => p.name === name);

// Options as the compiler sees them with every parameter at its default.
function effectiveOptions(node) {
    const out = { ...(node.options || {}) };
    for (const [key, name] of Object.entries(node.params || {})) {
        delete out[key];
        const v = paramOf(name)?.default ?? '';
        if (v !== '') out[key] = v;
    }
    return out;
}

const boundKey = (node, keys) => keys.find(k => k in (node.params || {})) ?? null;
const paramUses = (name) => S.doc.nodes.flatMap(n => Object.entries(n.params || {}).filter(([, p]) => p === name).map(([key]) => ({ node: n, key })));

function uniqueParamName(base) {
    base = String(base).replace(/[^A-Za-z0-9_-]/g, '_').replace(/^[^A-Za-z]+/, '').slice(0, 28) || 'param';
    const names = new Set(S.doc.params.map(p => p.name));
    if (!names.has(base)) return base;
    let i = 2;
    while (names.has(`${base}${i}`)) i++;
    return `${base}${i}`;
}

// Bind an option to parameter `name`, or to a new parameter that starts from the option's current value.
function bindParam(node, key, name, { aliases = [], base = key, description = '' } = {}) {
    S.bindMenu = null;
    mutate(() => {
        const n = nodeById(node.id);
        const keys = [key, ...aliases];
        if (!name) {
            name = uniqueParamName(base);
            const current = keys.map(k => n.options[k]).find(v => v !== undefined) ?? '';
            S.doc.params.push({ name, description, default: current });
        }
        for (const k of keys) { delete n.options[k]; delete n.params[k]; }
        n.params[key] = name;
    });
}

// Back to a fixed value: the parameter's current default.
function unbindParam(node, key) {
    mutate(() => {
        const n = nodeById(node.id);
        const v = paramOf(n.params[key])?.default ?? '';
        delete n.params[key];
        if (v !== '') n.options[key] = v;
    });
}

function renameParam(oldName, newName) {
    mutate(() => {
        paramOf(oldName).name = newName;
        for (const { node, key } of paramUses(oldName)) node.params[key] = newName;
    });
}

function removeParam(name) {
    mutate(() => {
        const v = paramOf(name)?.default ?? '';
        for (const { node, key } of paramUses(name)) {
            delete node.params[key];
            if (v !== '') node.options[key] = v;
        }
        S.doc.params = S.doc.params.filter(p => p.name !== name);
    });
}

// Shown instead of the value field when the option is bound to a parameter.
function boundWidget(node, keys) {
    const key = boundKey(node, keys);
    if (!key) return null;
    const name = node.params[key];
    const p = paramOf(name);
    return el('div', { class: 'param-bound' },
        icon('fa-sliders'),
        el('select', { 'data-key': `bind:${node.id}:${key}`, title: 'Graph parameter this option takes its value from',
            onchange: (ev) => bindParam(node, key, ev.target.value) },
            S.doc.params.map(q => el('option', { value: q.name, selected: q.name === name }, q.name)),
            p ? null : el('option', { value: name, selected: true }, `${name} (missing)`)),
        el('span', { class: 'hint', title: 'The parameter\'s default; runs and graphs embedding this one can change it' },
            p ? (p.default === '' ? 'default: unset' : `default: ${p.default}`) : ''),
        el('button', { type: 'button', class: 'small btn-ghost reset', title: 'Use a fixed value again', onclick: () => unbindParam(node, key) }, icon('fa-link-slash')));
}

// The sliders button that turns an option into a graph parameter.
function paramButton(node, keys, opts) {
    if (boundKey(node, keys)) return null;
    const key = keys[0];
    const menuKey = `${node.id}:${key}`;
    if (S.bindMenu === menuKey) {
        return el('select', { class: 'param-menu', 'data-key': `bindmenu:${menuKey}`, onchange: (ev) => {
            if (ev.target.value === '__cancel__') { S.bindMenu = null; renderInspector(); return; }
            bindParam(node, key, ev.target.value === '__new__' ? null : ev.target.value, { aliases: keys.slice(1), ...opts });
        } },
            el('option', { value: '__cancel__' }, 'Make a graph parameter…'),
            el('option', { value: '__new__' }, `New parameter "${uniqueParamName(opts.base || key)}"`),
            S.doc.params.map(p => el('option', { value: p.name }, `Use "${p.name}"`)));
    }
    return el('button', { type: 'button', class: 'small btn-ghost param-btn', title: 'Make this a graph parameter (set when running, or by graphs that use this one)',
        onclick: () => {
            if (!S.doc.params.length) { bindParam(node, key, null, { aliases: keys.slice(1), ...opts }); return; }
            S.bindMenu = menuKey;
            renderInspector();
        } }, icon('fa-sliders'));
}

function starterDoc() {
    return {
        version: 1,
        params: [],
        nodes: [
            { kind: 'input', id: 'in1', name: 'in', options: {}, params: {}, sample_path: null, note: '', position: { x: 40, y: 80 } },
            { kind: 'output', id: 'out1', name: 'out', pads: [{ name: 'v', type: 'video' }, { name: 'a', type: 'audio' }],
              options: {}, params: {}, filename: '{stem}-{output}.mp4', note: '', position: { x: 520, y: 80 } },
        ],
        edges: [
            { source: 'in1', source_pad: 'v', target: 'out1', target_pad: 'v' },
            { source: 'in1', source_pad: 'a', target: 'out1', target_pad: 'a' },
        ],
    };
}

// Drop links whose pads disappeared (e.g. after lowering `inputs` on hstack).
function pruneEdges() {
    S.doc.edges = S.doc.edges.filter(e => {
        const src = nodeById(e.source), dst = nodeById(e.target);
        if (!src || !dst) return false;
        if (padsKnown(src) && !padsOf(src).outputs.some(p => p.key === e.source_pad)) return false;
        if (padsKnown(dst) && !padsOf(dst).inputs.some(p => p.key === e.target_pad)) return false;
        return true;
    });
}

// ------------------------------------------------------------------ history, dirty state, drafts

function mutate(fn, opts = {}) {
    const now = Date.now();
    const coalesced = opts.coalesce && S.lastCoalesce === opts.coalesce && now - S.lastCoalesceAt < 1500;
    if (!coalesced) {
        S.history.undo.push(opts.snapshot || JSON.stringify(S.doc));
        if (S.history.undo.length > 200) S.history.undo.shift();
    }
    S.lastCoalesce = opts.coalesce || null;
    S.lastCoalesceAt = now;
    S.history.redo = [];
    fn();
    afterChange();
}

function afterChange() {
    pruneEdges();
    cleanSelection();
    setDirty(true);
    renderAll();
    scheduleCompile();
    saveDraft();
}

function undo() {
    if (!S.history.undo.length) return;
    S.history.redo.push(JSON.stringify(S.doc));
    S.doc = JSON.parse(S.history.undo.pop());
    S.lastCoalesce = null;
    afterChange();
}

function redo() {
    if (!S.history.redo.length) return;
    S.history.undo.push(JSON.stringify(S.doc));
    S.doc = JSON.parse(S.history.redo.pop());
    S.lastCoalesce = null;
    afterChange();
}

function cleanSelection() {
    for (const id of [...S.sel.nodes]) if (!nodeById(id)) S.sel.nodes.delete(id);
    if (S.sel.edge != null && !S.doc.edges[S.sel.edge]) S.sel.edge = null;
}

function setDirty(dirty) {
    S.dirty = dirty;
    const st = $('saveState');
    st.classList.toggle('dirty', dirty);
    st.textContent = dirty ? (S.meta.id ? '● unsaved changes' : '● not in library yet')
        : (S.meta.id ? `saved · rev ${S.meta.revision}` : '');
    $('btnUndo').disabled = !S.history.undo.length;
    $('btnRedo').disabled = !S.history.redo.length;
}

let draftTimer = null;
function saveDraft() {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => {
        try { localStorage.setItem('studio.draft', JSON.stringify({ doc: S.doc, meta: S.meta, dirty: S.dirty })); } catch (e) { /* storage full or disabled */ }
    }, 400);
}

function confirmDiscard() {
    return !S.dirty || confirm('Discard unsaved changes to this graph?');
}

// ------------------------------------------------------------------ loading documents

async function ensureSpecs(names) {
    const missing = [...new Set(names)].filter(n => !S.specs.has(n));
    await Promise.all(missing.map(async (n) => {
        try { S.specs.set(n, await api(`${API}/filters/${encodeURIComponent(n)}`)); } catch (e) { S.specs.set(n, null); }
    }));
}

async function loadDoc(doc, meta, { dirty = false } = {}) {
    await ensureSpecs(doc.nodes.filter(n => n.kind === 'filter').map(n => n.filter));
    S.doc = normalizeDoc(doc);
    S.meta = { id: null, name: 'Untitled graph', description: '', tags: [], revision: null, ...meta };
    S.sel = { nodes: new Set(), edge: null };
    S.history = { undo: [], redo: [] };
    S.compiled = null;
    $('graphName').value = S.meta.name;
    renderAll();
    if (doc.nodes.some(n => !n.position)) {
        autoLayout(false);
        renderAll();
    }
    fitView();
    setDirty(dirty);
    renderLibrary();
    scheduleCompile(0);
    saveDraft();
    const url = S.meta.id ? `/studio?graph=${encodeURIComponent(S.meta.id)}` : '/studio';
    if (location.pathname + location.search !== url) history.replaceState(null, '', url);
}

async function newGraph() {
    if (!confirmDiscard()) return;
    await loadDoc(starterDoc(), {});
}

// ------------------------------------------------------------------ rendering: nodes and wires

function issuesByNode() {
    const map = new Map();
    for (const i of S.compiled?.issues || []) {
        if (!i.node) continue;
        if (!map.has(i.node)) map.set(i.node, []);
        map.get(i.node).push(i);
    }
    return map;
}

function summaryText(node) {
    const bound = (fmt) => Object.entries(node.params || {}).map(([k, p]) => fmt(k, `$${p}`));
    if (node.kind === 'filter') {
        const parts = node.args.map((a, i) => `#${i + 1}=${a}`).concat(Object.entries(node.options).map(([k, v]) => `${k}=${v}`), bound((k, v) => `${k}=${v}`));
        return parts.join('  ');
    }
    if (node.kind === 'input') {
        const parts = Object.entries(node.options).map(([k, v]) => `-${k} ${v}`).concat(bound((k, v) => `-${k} ${v}`));
        if (node.sample_path) parts.unshift(node.sample_path.split('/').pop());
        return parts.join('  ') || 'file chosen at run time';
    }
    if (node.kind === 'output') {
        return [node.filename, ...Object.entries(node.options).map(([k, v]) => `-${k} ${v}`), ...bound((k, v) => `-${k} ${v}`)].join('  ');
    }
    const g = S.libById.get(node.graph_id);
    const values = Object.entries(node.options || {}).map(([k, v]) => `${k}=${v}`).concat(bound((k, v) => `${k}=${v}`));
    if (values.length) return values.join('  ');
    return g ? (g.filters.join(', ') || 'no filters') : 'not in library';
}

function portTitle(node, pad, side) {
    const edges = S.doc.edges.filter(e => (side === 'in' ? e.target === node.id && e.target_pad === pad.key : e.source === node.id && e.source_pad === pad.key));
    const head = `${side === 'in' ? 'Input' : 'Output'} pad #${pad.key} '${pad.name}' (${pad.type})`;
    if (!edges.length) return `${head}\nnot connected`;
    return `${head}\n` + edges.map(e => (side === 'in'
        ? `← ${nodeLabel(nodeById(e.source))} › ${padOf(e.source, 'out', e.source_pad)?.name ?? e.source_pad}`
        : `→ ${nodeLabel(nodeById(e.target))} › ${padOf(e.target, 'in', e.target_pad)?.name ?? e.target_pad}`)).join('\n');
}

function nodeElement(node, issues) {
    const pads = padsOf(node);
    const errors = issues.filter(i => i.level === 'error');
    const pos = node.position || { x: 0, y: 0 };
    const usedIn = new Set(S.doc.edges.filter(e => e.target === node.id).map(e => e.target_pad));
    const usedOut = new Set(S.doc.edges.filter(e => e.source === node.id).map(e => e.source_pad));
    const badPads = new Set(issues.filter(i => i.pad != null).map(i => `${i.side}|${i.pad}`));
    let title, sub;
    if (node.kind === 'filter') { title = node.filter; sub = ''; }
    else if (node.kind === 'graph') { title = S.libById.get(node.graph_id)?.name || 'missing graph'; sub = 'saved graph'; }
    else { title = node.name; sub = node.kind; }

    const port = (pad, side) => el('div', {
        class: `port ${side}${(side === 'in' ? usedIn : usedOut).has(pad.key) ? '' : ' unconnected'}${badPads.has(`${side}|${pad.key}`) ? ' port-error' : ''}`,
        'data-side': side, 'data-pad': pad.key, 'data-type': pad.type, title: portTitle(node, pad, side),
    }, side === 'in' ? [el('span', { class: 'dot' }), el('span', { class: 'pname' }, pad.name)]
                     : [el('span', { class: 'pname' }, pad.name), el('span', { class: 'dot' })]);

    const e = el('div', {
        class: `node kind-${node.kind}${S.sel.nodes.has(node.id) ? ' selected' : ''}${errors.length ? ' has-error' : ''}`,
        'data-id': node.id, title: errors.map(i => i.message).join('\n') || null,
    },
        el('div', { class: 'node-head' },
            icon(KIND_ICON[node.kind], 'kind'),
            el('span', { class: 'title' }, title),
            sub ? el('span', { class: 'sub' }, sub) : null,
            errors.length ? el('span', { class: 'err' }, `!${errors.length}`) : null),
        (pads.inputs.length || pads.outputs.length) ? el('div', { class: 'node-ports' },
            el('div', { class: 'port-col' }, pads.inputs.map(p => port(p, 'in'))),
            el('div', { class: 'port-col' }, pads.outputs.map(p => port(p, 'out')))) : null,
        summaryText(node) ? el('div', { class: 'node-summary', title: summaryText(node) }, summaryText(node)) : null,
        node.note ? el('div', { class: 'node-note' }, node.note) : null);
    e.style.left = `${pos.x}px`;
    e.style.top = `${pos.y}px`;
    return e;
}

function offsetWithin(elm, ancestor) {
    let x = 0, y = 0;
    for (let e = elm; e && e !== ancestor; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; }
    return { x, y };
}

function renderNodes() {
    const host = $('nodes');
    const issues = issuesByNode();
    host.replaceChildren(...S.doc.nodes.map(n => nodeElement(n, issues.get(n.id) || [])));
    S.portOffsets = new Map();
    S.nodeSize = new Map();
    for (const ne of host.children) {
        const offs = {};
        for (const p of ne.querySelectorAll('.port')) {
            const dot = p.querySelector('.dot');
            const o = offsetWithin(dot, ne);
            offs[`${p.dataset.side}|${p.dataset.pad}`] = { x: o.x + dot.offsetWidth / 2, y: o.y + dot.offsetHeight / 2 };
        }
        S.portOffsets.set(ne.dataset.id, offs);
        S.nodeSize.set(ne.dataset.id, { w: ne.offsetWidth, h: ne.offsetHeight });
    }
    $('emptyHint').hidden = S.doc.nodes.length > 0;
}

function portPos(nodeId, side, pad) {
    const n = nodeById(nodeId);
    const off = S.portOffsets.get(nodeId)?.[`${side}|${pad}`];
    if (!n || !off) return null;
    const pos = n.position || { x: 0, y: 0 };
    return { x: pos.x + off.x, y: pos.y + off.y };
}

function wirePath(a, b) {
    const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
    return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
}

function linkFor(e) {
    return (S.compiled?.links || []).find(l => l.source === e.source && l.source_pad === e.source_pad && l.target === e.target && l.target_pad === e.target_pad);
}

function renderEdges() {
    const svg = $('edges');
    svg.replaceChildren();
    const labels = [];
    S.doc.edges.forEach((e, i) => {
        const a = portPos(e.source, 'out', e.source_pad), b = portPos(e.target, 'in', e.target_pad);
        if (!a || !b) return;
        const type = padOf(e.source, 'out', e.source_pad)?.type || 'video';
        const d = wirePath(a, b);
        svg.append(svgEl('path', { d, class: 'hit', 'data-edge': i }),
                   svgEl('path', { d, class: `wire ${type}${S.sel.edge === i ? ' selected' : ''}`, 'data-edge': i }));
        const link = S.showLabels && linkFor(e);
        if (link && link.label) {
            const text = link.chained ? ',' : (/^\d+:/.test(link.label) ? link.label : `[${link.label}]`);
            labels.push({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, text, chained: link.chained, i });
        }
    });
    for (const l of labels) {
        const w = l.text.length * 6.7 + 10;
        const g = svgEl('g', { class: `lbl${l.chained ? ' chained' : ''}`, 'data-edge': l.i });
        g.append(svgEl('rect', { x: l.x - w / 2, y: l.y - 9, width: w, height: 18, rx: 4 }));
        const t = svgEl('text', { x: l.x, y: l.y + 4, 'text-anchor': 'middle' });
        t.textContent = l.text;
        g.append(t);
        svg.append(g);
    }
    if (S.drag?.type === 'connect' && S.drag.cur) {
        const p = portPos(S.drag.from.node, S.drag.from.side, S.drag.from.pad);
        if (p) {
            const [a, b] = S.drag.from.side === 'out' ? [p, S.drag.cur] : [S.drag.cur, p];
            svg.append(svgEl('path', { d: wirePath(a, b), class: `temp ${S.drag.from.type}`, stroke: S.drag.from.type === 'audio' ? 'var(--audio)' : 'var(--video)' }));
        }
    }
}

function renderAll() {
    renderNodes();
    renderEdges();
    renderInspector();
    setDirty(S.dirty);
}

// ------------------------------------------------------------------ view (pan / zoom)

const canvas = $('canvas');

function applyView() {
    const { x, y, k } = S.view;
    $('world').style.transform = `translate(${x}px, ${y}px) scale(${k})`;
    canvas.style.backgroundSize = `${24 * k}px ${24 * k}px`;
    canvas.style.backgroundPosition = `${x}px ${y}px`;
    $('zoomLabel').textContent = `${Math.round(k * 100)}%`;
}

function toWorld(cx, cy) {
    const r = canvas.getBoundingClientRect();
    return { x: (cx - r.left - S.view.x) / S.view.k, y: (cy - r.top - S.view.y) / S.view.k };
}

function viewCenter() {
    const r = canvas.getBoundingClientRect();
    return toWorld(r.left + r.width / 2, r.top + r.height / 2);
}

function fitView() {
    if (!S.doc.nodes.length) { S.view = { x: 60, y: 60, k: 1 }; applyView(); return; }
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of S.doc.nodes) {
        const p = n.position || { x: 0, y: 0 }, s = S.nodeSize.get(n.id) || { w: 200, h: 80 };
        x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + s.w); y1 = Math.max(y1, p.y + s.h);
    }
    const r = canvas.getBoundingClientRect();
    const k = Math.max(0.3, Math.min(1.1, (r.width - 80) / (x1 - x0), (r.height - 80) / (y1 - y0)));
    S.view = { k, x: (r.width - (x1 - x0) * k) / 2 - x0 * k, y: (r.height - (y1 - y0) * k) / 2 - y0 * k };
    applyView();
}

function zoomAt(cx, cy, factor) {
    const r = canvas.getBoundingClientRect();
    const k = Math.max(0.2, Math.min(2.5, S.view.k * factor));
    const px = cx - r.left, py = cy - r.top;
    S.view.x = px - (px - S.view.x) * (k / S.view.k);
    S.view.y = py - (py - S.view.y) * (k / S.view.k);
    S.view.k = k;
    applyView();
}

function autoLayout(withHistory = true) {
    const nodes = S.doc.nodes;
    const preds = new Map(nodes.map(n => [n.id, []]));
    for (const e of S.doc.edges) if (preds.has(e.target) && preds.has(e.source)) preds.get(e.target).push(e.source);
    const depth = new Map();
    const visiting = new Set();
    const dfs = (id) => {
        if (depth.has(id)) return depth.get(id);
        if (visiting.has(id)) return 0;
        visiting.add(id);
        const ps = preds.get(id) || [];
        const d = ps.length ? 1 + Math.max(...ps.map(dfs)) : 0;
        visiting.delete(id);
        depth.set(id, d);
        return d;
    };
    nodes.forEach(n => dfs(n.id));
    const maxInner = Math.max(0, ...nodes.filter(n => n.kind !== 'output').map(n => depth.get(n.id)));
    for (const n of nodes) {
        if (n.kind === 'output') depth.set(n.id, maxInner + 1);
        if (n.kind === 'input') depth.set(n.id, 0);
    }
    const columns = [];
    for (const n of nodes) (columns[depth.get(n.id)] ||= []).push(n);
    const order = new Map();
    const apply = () => {
        let x = 40;
        const heights = columns.map(col => (col || []).reduce((h, n) => h + (S.nodeSize.get(n.id)?.h || 90) + 40, -40));
        const tallest = Math.max(0, ...heights);
        columns.forEach((col, ci) => {
            if (!col) return;
            col.forEach((n, i) => order.set(n.id, i));
            if (ci > 0) {
                const bary = (n) => {
                    const ps = preds.get(n.id) || [];
                    return ps.length ? ps.reduce((s, p) => s + (order.get(p) ?? 0), 0) / ps.length : order.get(n.id);
                };
                col.sort((a, b) => bary(a) - bary(b));
                col.forEach((n, i) => order.set(n.id, i));
            }
            let y = 40 + (tallest - heights[ci]) / 2;
            const width = Math.max(...col.map(n => S.nodeSize.get(n.id)?.w || 200));
            for (const n of col) {
                n.position = { x, y };
                y += (S.nodeSize.get(n.id)?.h || 90) + 40;
            }
            x += width + 90;
        });
    };
    if (withHistory) mutate(apply);
    else apply();
}

// ------------------------------------------------------------------ canvas interaction

function portInfo(portEl) {
    const nodeEl = portEl.closest('.node');
    return { node: nodeEl.dataset.id, side: portEl.dataset.side, pad: portEl.dataset.pad, type: portEl.dataset.type };
}

function connect(from, to, snapshot) {
    const [src, dst] = from.side === 'out' ? [from, to] : [to, from];
    mutate(() => {
        S.doc.edges = S.doc.edges.filter(e => !(e.target === dst.node && e.target_pad === dst.pad));
        S.doc.edges.push({ source: src.node, source_pad: src.pad, target: dst.node, target_pad: dst.pad });
        S.sel = { nodes: new Set(), edge: S.doc.edges.length - 1 };
    }, { snapshot });
}

function compatible(from, portEl) {
    if (!portEl) return false;
    const to = portInfo(portEl);
    return to.node !== from.node && to.side !== from.side && to.type === from.type;
}

function highlightTargets(from) {
    for (const p of document.querySelectorAll('#nodes .port')) {
        const ok = compatible(from, p);
        p.classList.toggle('dim', !ok && !(p.closest('.node').dataset.id === from.node && p.dataset.pad === from.pad && p.dataset.side === from.side));
    }
}

function clearHighlights() {
    for (const p of document.querySelectorAll('#nodes .port.dim, #nodes .port.hot')) p.classList.remove('dim', 'hot');
}

canvas.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0 && ev.button !== 1) return;
    ev.preventDefault(); // suppresses the browser's native text/element drag
    hideQuickAdd();
    canvas.focus({ preventScroll: true });
    const portEl = ev.target.closest('.dot')?.closest('.port');
    const nodeEl = ev.target.closest('.node');
    const edgeEl = ev.target.closest('[data-edge]');
    const start = { x: ev.clientX, y: ev.clientY };
    if (ev.button === 1 || (!nodeEl && !edgeEl)) {
        S.drag = { type: 'pan', start, view: { ...S.view }, moved: false };
        canvas.classList.add('panning');
    } else if (portEl) {
        let from = portInfo(portEl);
        const snapshot = JSON.stringify(S.doc);
        if (from.side === 'in') {
            const existing = S.doc.edges.findIndex(e => e.target === from.node && e.target_pad === from.pad);
            if (existing >= 0) {
                // Pick the wire up from its input end, keeping its source.
                const e = S.doc.edges[existing];
                S.doc.edges.splice(existing, 1);
                from = { node: e.source, side: 'out', pad: e.source_pad, type: from.type };
                renderNodes();
            }
        }
        S.drag = { type: 'connect', from, snapshot, cur: toWorld(ev.clientX, ev.clientY) };
        highlightTargets(from);
        renderEdges();
    } else if (edgeEl) {
        S.sel = { nodes: new Set(), edge: Number(edgeEl.dataset.edge) };
        renderAll();
        return;
    } else {
        const id = nodeEl.dataset.id;
        if (ev.shiftKey) {
            if (S.sel.nodes.has(id)) S.sel.nodes.delete(id); else S.sel.nodes.add(id);
        } else if (!S.sel.nodes.has(id)) {
            S.sel.nodes = new Set([id]);
        }
        S.sel.edge = null;
        const origins = new Map([...S.sel.nodes].map(n => [n, { ...(nodeById(n).position || { x: 0, y: 0 }) }]));
        S.drag = { type: 'move', start, origins, moved: false, snapshot: JSON.stringify(S.doc), clicked: id, shift: ev.shiftKey };
        for (const ne of $('nodes').children) ne.classList.toggle('selected', S.sel.nodes.has(ne.dataset.id));
        renderInspector();
    }
    canvas.setPointerCapture(ev.pointerId);
});

canvas.addEventListener('pointermove', (ev) => {
    S.lastPointer = { x: ev.clientX, y: ev.clientY };
    const d = S.drag;
    if (!d) return;
    if (d.type === 'pan') {
        const dx = ev.clientX - d.start.x, dy = ev.clientY - d.start.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
        S.view.x = d.view.x + dx;
        S.view.y = d.view.y + dy;
        applyView();
    } else if (d.type === 'move') {
        const dx = (ev.clientX - d.start.x) / S.view.k, dy = (ev.clientY - d.start.y) / S.view.k;
        if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
        if (!d.moved) return;
        for (const [id, o] of d.origins) {
            const n = nodeById(id);
            n.position = { x: Math.round(o.x + dx), y: Math.round(o.y + dy) };
            const ne = $('nodes').querySelector(`[data-id="${CSS.escape(id)}"]`);
            if (ne) { ne.style.left = `${n.position.x}px`; ne.style.top = `${n.position.y}px`; }
        }
        renderEdges();
    } else if (d.type === 'connect') {
        d.cur = toWorld(ev.clientX, ev.clientY);
        const target = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('.port');
        for (const p of document.querySelectorAll('#nodes .port.hot')) p.classList.remove('hot');
        if (compatible(d.from, target)) target.classList.add('hot');
        renderEdges();
    }
});

canvas.addEventListener('pointerup', (ev) => {
    const d = S.drag;
    S.drag = null;
    canvas.classList.remove('panning');
    if (!d) return;
    if (d.type === 'pan') {
        if (!d.moved && ev.button === 0) {
            S.sel = { nodes: new Set(), edge: null };
            renderAll();
        }
    } else if (d.type === 'move') {
        if (d.moved) {
            S.history.undo.push(d.snapshot);
            S.history.redo = [];
            setDirty(true);
            saveDraft();
        } else if (!d.shift) {
            S.sel.nodes = new Set([d.clicked]);
            renderAll();
        }
    } else if (d.type === 'connect') {
        clearHighlights();
        const target = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('.port');
        if (compatible(d.from, target)) {
            connect(d.from, portInfo(target), d.snapshot);
        } else if (!ev.target.closest?.('.node') && !document.elementFromPoint(ev.clientX, ev.clientY)?.closest('.node')) {
            // Dropped on empty canvas: offer matching filters and connect the new node.
            const changed = d.snapshot !== JSON.stringify(S.doc);
            showQuickAdd(ev.clientX, ev.clientY, { connect: d.from, snapshot: changed ? d.snapshot : null });
            renderEdges();
        } else {
            if (d.snapshot !== JSON.stringify(S.doc)) {
                S.history.undo.push(d.snapshot);
                S.history.redo = [];
                afterChange();
            } else {
                renderEdges();
            }
        }
    }
});

canvas.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    zoomAt(ev.clientX, ev.clientY, Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015)));
}, { passive: false });

canvas.addEventListener('dblclick', (ev) => {
    if (ev.target.closest('.node')) return;
    showQuickAdd(ev.clientX, ev.clientY, {});
});

canvas.addEventListener('dragstart', (ev) => ev.preventDefault());
canvas.addEventListener('selectstart', (ev) => ev.preventDefault());

canvas.addEventListener('dragover', (ev) => {
    if (ev.dataTransfer.types.includes('application/x-studio-node')) ev.preventDefault();
});
canvas.addEventListener('drop', (ev) => {
    const raw = ev.dataTransfer.getData('application/x-studio-node');
    if (!raw) return;
    ev.preventDefault();
    const item = JSON.parse(raw);
    const p = toWorld(ev.clientX, ev.clientY);
    addNode(item.kind, item, { x: p.x - 90, y: p.y - 20 });
});

// ------------------------------------------------------------------ adding, deleting, duplicating

async function addNode(kind, extra = {}, at = null, after = null, snapshot = null) {
    if (kind === 'filter') {
        const summary = S.catalogByName.get(extra.filter);
        if (summary?.blocked) { toast(`${extra.filter} isn't available in the studio (it reads/writes server files or loads code).`, true); return null; }
        await ensureSpecs([extra.filter]);
    }
    if (kind === 'graph' && extra.graph_id === S.meta.id) { toast("A graph can't contain itself.", true); return null; }
    const node = makeNode(kind, extra);
    const c = viewCenter();
    node.position = at || { x: Math.round(c.x - 90), y: Math.round(c.y - 40) };
    mutate(() => {
        S.doc.nodes.push(node);
        after?.(node);
        S.sel = { nodes: new Set([node.id]), edge: null };
    }, { snapshot });
    return node;
}

function deleteSelection() {
    if (S.sel.edge != null) {
        const i = S.sel.edge;
        mutate(() => { S.doc.edges.splice(i, 1); S.sel.edge = null; });
        return;
    }
    if (!S.sel.nodes.size) return;
    const ids = new Set(S.sel.nodes);
    mutate(() => {
        S.doc.nodes = S.doc.nodes.filter(n => !ids.has(n.id));
        S.doc.edges = S.doc.edges.filter(e => !ids.has(e.source) && !ids.has(e.target));
        S.sel.nodes = new Set();
    });
}

function duplicateSelection() {
    if (!S.sel.nodes.size) return;
    const ids = new Set(S.sel.nodes);
    mutate(() => {
        const map = new Map();
        for (const n of S.doc.nodes.filter(n => ids.has(n.id))) {
            const copy = clone(n);
            copy.id = newId(n.kind === 'filter' ? n.filter : n.kind === 'graph' ? 'graph' : n.kind === 'input' ? 'in' : 'out');
            if (n.kind === 'input' || n.kind === 'output') copy.name = uniqueName(n.kind, n.name);
            copy.position = { x: (n.position?.x || 0) + 40, y: (n.position?.y || 0) + 40 };
            map.set(n.id, copy.id);
            S.doc.nodes.push(copy);
        }
        for (const e of S.doc.edges.filter(e => map.has(e.source) && map.has(e.target))) {
            S.doc.edges.push({ ...e, source: map.get(e.source), target: map.get(e.target) });
        }
        S.sel = { nodes: new Set(map.values()), edge: null };
    });
}

// Put a new node on an existing wire: source -> node -> target.
async function insertOnEdge(index, filterName) {
    const e = S.doc.edges[index];
    if (!e) return;
    const type = padOf(e.source, 'out', e.source_pad)?.type || 'video';
    const a = portPos(e.source, 'out', e.source_pad), b = portPos(e.target, 'in', e.target_pad);
    const at = a && b ? { x: Math.round((a.x + b.x) / 2 - 90), y: Math.round((a.y + b.y) / 2 - 30) } : null;
    await addNode('filter', { filter: filterName }, at, (node) => {
        const pads = padsOf(node);
        const pin = pads.inputs.find(p => p.type === type), pout = pads.outputs.find(p => p.type === type);
        if (!pin || !pout) return;
        S.doc.edges.splice(S.doc.edges.indexOf(e), 1);
        S.doc.edges.push({ source: e.source, source_pad: e.source_pad, target: node.id, target_pad: pin.key });
        S.doc.edges.push({ source: node.id, source_pad: pout.key, target: e.target, target_pad: e.target_pad });
        if (at) {
            // Make room: move everything right of the insertion point further right.
            for (const n of S.doc.nodes) if (n !== node && n.position && n.position.x > at.x - 60) n.position.x += 260;
            node.position.x = Math.max(at.x, (nodeById(e.source)?.position?.x ?? at.x) + (S.nodeSize.get(e.source)?.w ?? 180) + 60);
        }
    });
}

// ------------------------------------------------------------------ quick add

const QA = { ctx: null, items: [], active: 0 };

function ioAccepts(code, type) {
    return code === 'N' || code.includes(type === 'audio' ? 'A' : 'V');
}

function quickItems(query, ctx) {
    const q = query.trim().toLowerCase();
    const want = ctx.connect ? { side: ctx.connect.side === 'out' ? 'in' : 'out', type: ctx.connect.type }
        : ctx.insertEdge != null ? { side: 'both', type: padOf(S.doc.edges[ctx.insertEdge].source, 'out', S.doc.edges[ctx.insertEdge].source_pad)?.type || 'video' } : null;
    const items = [];
    if (!want || want.side === 'out') {
        if (!q || 'input file'.includes(q)) items.push({ kind: 'input', label: 'Input file', desc: 'Read a file (-i)', io: '|->VA', score: 2 });
    }
    if (!want || want.side === 'in') {
        if (!q || 'output file'.includes(q)) items.push({ kind: 'output', label: 'Output file', desc: 'Write a file (-map …)', io: 'VA->|', score: 2 });
    }
    if (ctx.insertEdge == null) {
        for (const g of S.library) {
            if (g.id === S.meta.id) continue;
            if (q && !g.name.toLowerCase().includes(q) && !g.description.toLowerCase().includes(q)) continue;
            if (want) {
                const pads = want.side === 'in' ? g.interface.inputs : g.interface.outputs;
                if (!pads.some(p => p.type === want.type)) continue;
            }
            items.push({ kind: 'graph', graph_id: g.id, label: g.name, desc: g.description || 'saved graph', io: 'saved', score: 1.5 });
        }
    }
    for (const f of S.catalog) {
        if (f.blocked) continue;
        if (want) {
            if (want.side === 'in' && !ioAccepts(f.inputs, want.type)) continue;
            if (want.side === 'out' && !ioAccepts(f.outputs, want.type)) continue;
            if (want.side === 'both' && !(ioAccepts(f.inputs, want.type) && ioAccepts(f.outputs, want.type))) continue;
        }
        let score = 0;
        if (!q) score = f.popular ? 1 : 0;
        else if (f.name === q) score = 10;
        else if (f.name.startsWith(q)) score = 6;
        else if (f.name.includes(q)) score = 4;
        else if (f.description.toLowerCase().includes(q)) score = 2;
        else if (f.category.toLowerCase().includes(q)) score = 1.5;
        else continue;
        if (f.popular) score += 0.5;
        items.push({ kind: 'filter', filter: f.name, label: f.name, desc: f.description, io: `${f.inputs}->${f.outputs}`, score });
    }
    items.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label));
    return items.slice(0, q ? 80 : 40);
}

function showQuickAdd(cx, cy, ctx) {
    QA.ctx = { ...ctx, world: toWorld(cx, cy) };
    const box = $('quickAdd');
    box.hidden = false;
    box.style.left = `${Math.min(cx, window.innerWidth - 400)}px`;
    box.style.top = `${Math.min(cy, window.innerHeight - 440)}px`;
    $('quickSearch').value = '';
    renderQuick();
    $('quickSearch').focus();
}

function hideQuickAdd() {
    if ($('quickAdd').hidden) return;
    $('quickAdd').hidden = true;
    if (QA.ctx?.snapshot) {
        // A wire was picked up and dropped: record its removal.
        S.history.undo.push(QA.ctx.snapshot);
        S.history.redo = [];
        afterChange();
    }
    QA.ctx = null;
}

function renderQuick() {
    QA.items = quickItems($('quickSearch').value, QA.ctx || {});
    QA.active = 0;
    const list = $('quickList');
    list.replaceChildren(...(QA.items.length ? QA.items.map((it, i) => el('div', {
        class: `qi${i === 0 ? ' active' : ''}`, role: 'option',
        onpointerdown: (ev) => { ev.preventDefault(); chooseQuick(i); },
    }, el('span', { class: 'nm' }, it.label), el('span', { class: 'ds' }, it.desc), el('span', { class: 'io' }, it.io)))
        : [el('div', { class: 'qh' }, 'Nothing matches')]));
}

async function chooseQuick(i) {
    const it = QA.items[i];
    const ctx = QA.ctx;
    if (!it || !ctx) return;
    QA.ctx = null;
    $('quickAdd').hidden = true;
    if (ctx.insertEdge != null) {
        await insertOnEdge(ctx.insertEdge, it.filter);
        return;
    }
    const at = { x: Math.round(ctx.world.x - (ctx.connect?.side === 'in' ? 200 : 10)), y: Math.round(ctx.world.y - 30) };
    await addNode(it.kind, it, at, (node) => {
        if (!ctx.connect) return;
        const pads = padsOf(node);
        const from = ctx.connect;
        const list = from.side === 'out' ? pads.inputs : pads.outputs;
        const pad = list.find(p => p.type === from.type);
        if (!pad) return;
        if (from.side === 'out') {
            S.doc.edges.push({ source: from.node, source_pad: from.pad, target: node.id, target_pad: pad.key });
        } else {
            S.doc.edges = S.doc.edges.filter(e => !(e.target === from.node && e.target_pad === from.pad));
            S.doc.edges.push({ source: node.id, source_pad: pad.key, target: from.node, target_pad: from.pad });
        }
    }, ctx.snapshot);
}

$('quickSearch').addEventListener('input', renderQuick);
$('quickSearch').addEventListener('keydown', (ev) => {
    const rows = $('quickList').querySelectorAll('.qi');
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        ev.preventDefault();
        QA.active = Math.max(0, Math.min(rows.length - 1, QA.active + (ev.key === 'ArrowDown' ? 1 : -1)));
        rows.forEach((r, i) => r.classList.toggle('active', i === QA.active));
        rows[QA.active]?.scrollIntoView({ block: 'nearest' });
    } else if (ev.key === 'Enter') {
        ev.preventDefault();
        chooseQuick(QA.active);
    } else if (ev.key === 'Escape') {
        hideQuickAdd();
        canvas.focus();
    }
});
document.addEventListener('pointerdown', (ev) => {
    if (!$('quickAdd').hidden && !ev.target.closest('#quickAdd') && !ev.target.closest('#canvas')) hideQuickAdd();
});

// ------------------------------------------------------------------ inspector

function preserveFocus(container, render) {
    const active = document.activeElement;
    const key = container.contains(active) ? active.dataset.key : null;
    const typed = key && (active.tagName === 'TEXTAREA' || (active.tagName === 'INPUT' && /^(text|search|number)$/.test(active.type))) ? active.value : null;
    const sel = key && 'selectionStart' in active ? [active.selectionStart, active.selectionEnd] : null;
    const scroll = container.scrollTop;
    render();
    container.scrollTop = scroll;
    if (key) {
        const again = container.querySelector(`[data-key="${CSS.escape(key)}"]`);
        if (again) {
            // Keep text that was typed but not committed yet.
            if (typed != null && again.value !== typed) again.value = typed;
            again.focus({ preventScroll: true });
            if (sel && 'setSelectionRange' in again) { try { again.setSelectionRange(...sel); } catch (e) { /* not a text input */ } }
        }
    }
}

function section(title, ...children) {
    return el('div', { class: 'insp-section' }, el('h3', {}, ...[title].flat()), ...children);
}

let inspectorQueued = false;

// Deferred, so a change committed by Tab re-renders after focus has moved to the next field.
function renderInspector() {
    if (inspectorQueued) return;
    inspectorQueued = true;
    setTimeout(() => { inspectorQueued = false; renderInspectorNow(); }, 0);
}

function renderInspectorNow() {
    const box = $('inspector');
    preserveFocus(box, () => {
        box.replaceChildren();
        let parts;
        if (S.sel.edge != null && S.doc.edges[S.sel.edge]) parts = inspectEdge(S.sel.edge);
        else if (S.sel.nodes.size === 1) {
            const node = nodeById([...S.sel.nodes][0]);
            parts = node.kind === 'filter' ? inspectFilter(node) : node.kind === 'input' ? inspectInput(node)
                : node.kind === 'output' ? inspectOutput(node) : inspectGraphNode(node);
        } else if (S.sel.nodes.size > 1) {
            parts = [el('div', { class: 'insp-head' }, el('h2', {}, `${S.sel.nodes.size} nodes`),
                el('p', {}, 'Drag to move them together.')),
                el('div', { class: 'insp-actions' },
                    el('button', { type: 'button', class: 'small', onclick: duplicateSelection }, icon('fa-clone'), ' Duplicate'),
                    el('button', { type: 'button', class: 'small btn-danger', onclick: deleteSelection }, icon('fa-trash'), ' Delete'))];
        } else {
            parts = inspectGraph();
        }
        box.append(...parts.filter(Boolean));
    });
}

function textField(label, value, onCommit, { key, placeholder, mono = false, area = false, validate = null } = {}) {
    const input = el(area ? 'textarea' : 'input', {
        type: area ? null : 'text', value: value ?? '', placeholder, 'data-key': key, rows: area ? 3 : null,
        style: mono ? 'font-family: var(--mono)' : null, spellcheck: 'false',
    });
    const err = el('div', { class: 'field-err' });
    input.addEventListener('change', () => {
        const v = input.value;
        const problem = validate?.(v);
        err.textContent = problem || '';
        if (!problem) onCommit(v);
    });
    return el('label', {}, label, input, err);
}

function setNodeField(node, field, value, coalesce) {
    mutate(() => { nodeById(node.id)[field] = value; }, { coalesce });
}

function noteField(node) {
    return textField('Note (shown on the node)', node.note, (v) => setNodeField(node, 'note', v, `note:${node.id}`), { key: `note:${node.id}`, area: true });
}

function padsTable(node) {
    const pads = padsOf(node);
    const required = node.kind === 'filter' || node.kind === 'graph';
    const rows = [];
    const go = (id) => el('a', { onclick: () => { S.sel = { nodes: new Set([id]), edge: null }; renderAll(); } }, nodeLabel(nodeById(id)));
    const label = (e) => {
        const l = linkFor(e);
        if (!l || !l.label) return null;
        return el('span', { class: 'lbl', title: l.chained ? 'written as a chain with ","' : 'link label in the filtergraph' },
            l.chained ? ' ,' : /^\d+:/.test(l.label) ? ` ${l.label}` : ` [${l.label}]`);
    };
    for (const p of pads.inputs) {
        const e = S.doc.edges.find(x => x.target === node.id && x.target_pad === p.key);
        rows.push(el('tr', {},
            el('td', {}, el('span', { class: `dot ${p.type}` }), ` in #${p.key}`),
            el('td', {}, el('code', {}, p.name)),
            el('td', {}, e ? [ '← ', go(e.source), ` › ${padOf(e.source, 'out', e.source_pad)?.name ?? e.source_pad}`, label(e)]
                : el('span', { class: required ? 'bad' : 'none' }, required ? 'not connected (required)' : 'not connected'))));
    }
    for (const p of pads.outputs) {
        const es = S.doc.edges.filter(x => x.source === node.id && x.source_pad === p.key);
        rows.push(el('tr', {},
            el('td', {}, el('span', { class: `dot ${p.type}` }), ` out #${p.key}`),
            el('td', {}, el('code', {}, p.name)),
            el('td', {}, es.length ? es.map((e, i) => [i ? el('br') : null, '→ ', go(e.target), ` › ${padOf(e.target, 'in', e.target_pad)?.name ?? e.target_pad}`, label(e)])
                : el('span', { class: node.kind === 'filter' ? 'bad' : 'none' }, node.kind === 'filter' ? 'not connected (connect or end with nullsink)' : 'not connected'))));
    }
    if (!rows.length) return el('p', { class: 'hint' }, 'No pads.');
    return el('table', { class: 'pad-table' }, el('tbody', {}, rows));
}

function nodeActions(node) {
    return el('div', { class: 'insp-actions' },
        el('button', { type: 'button', class: 'small', onclick: duplicateSelection }, icon('fa-clone'), ' Duplicate'),
        el('button', { type: 'button', class: 'small btn-danger', onclick: deleteSelection }, icon('fa-trash'), ' Delete'));
}

function nodeIssues(node) {
    const issues = (S.compiled?.issues || []).filter(i => i.node === node.id && i.level !== 'info');
    if (!issues.length) return null;
    return el('ul', { class: 'problems' }, issues.map(i => el('li', { class: i.level }, icon(i.level === 'error' ? 'fa-circle-xmark' : 'fa-triangle-exclamation'), el('span', {}, i.message))));
}

// ---- filter node

function optionKey(node, opt) {
    return [opt.name, ...opt.aliases].find(k => k in node.options) ?? null;
}

function setOption(node, opt, value) {
    mutate(() => {
        const n = nodeById(node.id);
        const key = optionKey(n, opt) || opt.name;
        for (const k of [opt.name, ...opt.aliases]) delete n.options[k];
        if (value !== '') n.options[key] = value;
    });
}

const NUMERIC = new Set(['int', 'int64', 'uint64', 'float', 'double', 'rational', 'boolean']);

function optionRow(node, opt) {
    const key = optionKey(node, opt);
    const value = key ? node.options[key] : '';
    const dataKey = `opt:${node.id}:${opt.name}`;
    const bound = opt.blocked ? null : boundWidget(node, [opt.name, ...opt.aliases]);
    let widget;
    if (bound) {
        widget = bound;
    } else if (opt.blocked) {
        widget = el('input', { type: 'text', disabled: true, value: '', placeholder: 'not allowed: reads or writes server files' });
    } else if (opt.type === 'boolean') {
        widget = el('select', { 'data-key': dataKey, onchange: (ev) => setOption(node, opt, ev.target.value) },
            el('option', { value: '' }, `default (${opt.default ?? 'unset'})`),
            ['true', 'false'].map(v => el('option', { value: v, selected: value === v }, v)),
            value && !['true', 'false'].includes(value) ? el('option', { value, selected: true }, value) : null);
    } else if (opt.constants.length && opt.type !== 'flags') {
        const known = opt.constants.some(c => c.name === value);
        widget = el('select', { 'data-key': dataKey, onchange: (ev) => {
            if (ev.target.value === '__custom__') {
                const v = prompt(`Value for ${opt.name}:`, value);
                if (v != null) setOption(node, opt, v.trim()); else renderInspector();
            } else setOption(node, opt, ev.target.value);
        } },
            el('option', { value: '' }, `default (${opt.default ?? 'unset'})`),
            opt.constants.map(c => el('option', { value: c.name, selected: c.name === value }, c.help ? `${c.name} — ${c.help}` : c.name)),
            value && !known ? el('option', { value, selected: true }, `${value} (custom)`) : null,
            el('option', { value: '__custom__' }, 'Custom value…'));
    } else {
        const listId = opt.constants.length ? `dl-${node.id}-${opt.name}` : null;
        widget = el('input', {
            type: 'text', value, 'data-key': dataKey, placeholder: opt.default != null && opt.default !== '' ? `default: ${opt.default}` : '', list: listId, spellcheck: 'false',
            onchange: (ev) => setOption(node, opt, ev.target.value.trim()),
        });
        if (listId) widget = [widget, el('datalist', { id: listId }, opt.constants.map(c => el('option', { value: c.name }, c.help)))];
    }
    const extras = [];
    if (opt.type === 'color' && !opt.blocked && !bound) {
        const hex = /^#?[0-9a-f]{6}$/i.test(value) ? (value.startsWith('#') ? value : `#${value}`) : /^0x[0-9a-f]{6}$/i.test(value) ? `#${value.slice(2)}` : '#000000';
        extras.push(el('input', { type: 'color', value: hex, title: 'Pick a color', onchange: (ev) => setOption(node, opt, ev.target.value) }));
    }
    if (value !== '' && !opt.blocked && !bound) {
        extras.push(el('button', { type: 'button', class: 'small btn-ghost reset', title: 'Reset to default', onclick: () => setOption(node, opt, '') }, icon('fa-xmark')));
    }
    let warn = null;
    if (value !== '' && !bound && NUMERIC.has(opt.type) && opt.type !== 'boolean' && /^-?\d+(\.\d+)?$/.test(value)) {
        const v = parseFloat(value), lo = parseFloat(opt.min), hi = parseFloat(opt.max);
        if ((!isNaN(lo) && v < lo) || (!isNaN(hi) && v > hi)) warn = `Outside the allowed range ${opt.min} … ${opt.max}`;
    }
    const range = opt.min != null && opt.max != null ? ` Range ${opt.min} … ${opt.max}.` : '';
    const consts = opt.type === 'flags' && opt.constants.length
        ? el('div', { class: 'consts' }, 'Flags (combine with +): ', opt.constants.map((c, i) => [i ? ', ' : '', el('b', { title: c.help }, c.name)])) : null;
    return el('div', { class: `opt${value !== '' || bound ? ' set' : ''}${opt.blocked ? ' blocked' : ''}` },
        el('div', { class: 'opt-top' },
            el('span', { class: 'opt-name' }, opt.name),
            opt.aliases.length ? el('span', { class: 'opt-alias' }, `(${opt.aliases.join(', ')})`) : null,
            el('span', { class: 'opt-type' }, opt.type),
            opt.runtime ? el('span', { class: 'opt-rt', title: 'Can change while running (sendcmd/zmq)' }, 'runtime') : null,
            opt.blocked ? icon('fa-lock') : paramButton(node, [opt.name, ...opt.aliases], { base: `${node.filter}_${opt.name}`, description: opt.help })),
        (opt.help || range) ? el('div', { class: 'opt-help' }, `${opt.help}${opt.help && !/[.!?]$/.test(opt.help) ? '.' : ''}${range}`) : null,
        el('div', { class: 'opt-row' }, widget, extras),
        consts,
        warn ? el('div', { class: 'opt-warn' }, warn) : null);
}

function inspectFilter(node) {
    const spec = S.specs.get(node.filter);
    const summ = S.catalogByName.get(node.filter);
    const head = el('div', { class: 'insp-head' },
        el('h2', {}, icon('fa-filter'), node.filter),
        el('p', {}, spec?.description || summ?.description || 'Unknown filter'),
        el('div', { class: 'links' },
            spec ? el('a', { href: spec.doc_url, target: '_blank', rel: 'noopener' }, icon('fa-book'), ' ffmpeg docs') : null,
            summ ? el('span', { class: 'chip mono', title: 'ffmpeg input -> output types (V video, A audio, N dynamic, | none)' }, `${summ.inputs}->${summ.outputs}`) : null,
            summ ? el('span', { class: 'chip' }, summ.category) : null,
            spec?.timeline ? el('span', { class: 'badge tiny', title: "Supports the 'enable' option" }, 'timeline') : null,
            spec?.slice_threading ? el('span', { class: 'badge tiny' }, 'threads') : null));
    const out = [head];
    if (spec?.blocked) out.push(el('p', { class: 'field-err' }, `Not allowed here: ${spec.blocked_reason}.`));
    const issues = nodeIssues(node);
    if (issues) out.push(issues);

    const padExtras = [];
    if (spec) {
        for (const [side, rule] of [['in', spec.input_rule], ['out', spec.output_rule]]) {
            const word = side === 'in' ? 'input' : 'output';
            if (rule.kind === 'count') {
                padExtras.push(el('p', { class: 'hint' }, `The number of ${word} pads is the `, el('code', {}, rule.option), ' option below.'));
            } else if (rule.kind === 'concat') {
                if (side === 'in') padExtras.push(el('p', { class: 'hint' }, 'Pads come from ', el('code', {}, 'n'), ' (segments) × (', el('code', {}, 'v'), ' video + ', el('code', {}, 'a'), ' audio).'));
            } else if (rule.kind === 'manual') {
                const field = side === 'in' ? 'extra_inputs' : 'extra_outputs';
                const current = node[field] ?? rule.default;
                padExtras.push(el('label', {}, `Extra ${word} pads (this filter's ${word}s depend on its options)`,
                    el('input', { type: 'number', min: 0, max: 64, value: current, 'data-key': `${field}:${node.id}`,
                        onchange: (ev) => setNodeField(node, field, Math.max(0, Math.min(64, parseInt(ev.target.value, 10) || 0))) })));
            }
        }
    }
    out.push(section('Pads', padsTable(node), ...padExtras));
    out.push(section('In the filtergraph', el('pre', { class: 'preview-code' }, formatFilter(node))));

    if (node.args.length) {
        out.push(section('Positional values',
            el('p', { class: 'hint' }, 'Values without a name fill options in order.'),
            node.args.map((a, i) => textField(`#${i + 1}${spec?.positional[i] ? ` → ${spec.positional[i]}` : ''}`, a, (v) => mutate(() => { nodeById(node.id).args[i] = v; }), { key: `arg:${node.id}:${i}`, mono: true })),
            spec ? el('button', { type: 'button', class: 'small', onclick: () => mutate(() => {
                const n = nodeById(node.id);
                const named = {};
                n.args.forEach((a, i) => { if (spec.positional[i]) named[spec.positional[i]] = a; });
                n.options = { ...named, ...n.options };
                n.args = [];
            }) }, 'Convert to named options') : null));
    }

    if (spec) {
        const isSet = (o) => optionKey(node, o) !== null || boundKey(node, [o.name, ...o.aliases]) !== null;
        const setCount = spec.options.filter(isSet).length;
        const q = S.optFilter.toLowerCase();
        const shown = spec.options.filter(o => (!S.optOnlySet || isSet(o))
            && (!q || o.name.includes(q) || o.aliases.some(a => a.includes(q)) || o.help.toLowerCase().includes(q)));
        out.push(section([`Options `, el('span', { class: 'hint' }, `${setCount} set of ${spec.options.length}`)],
            el('div', { class: 'opt-tools' },
                el('input', { type: 'search', placeholder: 'Find option', value: S.optFilter, 'data-key': 'optfilter',
                    oninput: (ev) => { S.optFilter = ev.target.value; renderInspector(); } }),
                el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: S.optOnlySet,
                    onchange: (ev) => { S.optOnlySet = ev.target.checked; renderInspector(); } }), 'Only set')),
            shown.length ? shown.map(o => optionRow(node, o)) : el('p', { class: 'hint' }, 'No options match.')));
    } else {
        out.push(el('p', { class: 'hint' }, 'The filter description could not be loaded.'));
    }
    out.push(section('Node', noteField(node), el('p', { class: 'hint' }, `Node id: ${node.id}`)), nodeActions(node));
    return out;
}

// ---- input / output nodes

function ioOptionRow(node, spec) {
    const value = node.options[spec.name] ?? '';
    const dataKey = `io:${node.id}:${spec.name}`;
    const set = (v) => mutate(() => {
        const n = nodeById(node.id);
        if (v === '' || v === false) delete n.options[spec.name]; else n.options[spec.name] = v === true ? 'true' : v;
    });
    let widget;
    const bound = boundWidget(node, [spec.name]);
    if (bound) {
        widget = bound;
    } else if (spec.kind === 'flag') {
        widget = el('label', { class: 'check' }, el('input', { type: 'checkbox', checked: ['true', '1', 'yes', ''].includes(value) && spec.name in node.options, 'data-key': dataKey,
            onchange: (ev) => set(ev.target.checked) }), `-${spec.name}`);
    } else if (spec.kind === 'choice') {
        widget = el('select', { 'data-key': dataKey, onchange: (ev) => set(ev.target.value) },
            el('option', { value: '' }, '(not set)'), spec.choices.map(c => el('option', { value: c, selected: c === value }, c)));
    } else {
        const listId = spec.suggestions.length ? `io-${node.id}-${spec.name.replace(/\W/g, '_')}` : null;
        widget = [el('input', { type: 'text', value, list: listId, 'data-key': dataKey, spellcheck: 'false', placeholder: spec.kind === 'time' ? 'e.g. 5 or 00:01:30' : '',
            onchange: (ev) => set(ev.target.value.trim()) }),
            listId ? el('datalist', { id: listId }, spec.suggestions.map(s => el('option', { value: s }))) : null];
    }
    return el('div', { class: `opt${value !== '' || bound ? ' set' : ''}` },
        el('div', { class: 'opt-top' }, el('span', { class: 'opt-name' }, `-${spec.name}`), el('span', { class: 'opt-type' }, spec.kind),
            paramButton(node, [spec.name], { base: `${node.name}_${spec.name}`, description: spec.help })),
        el('div', { class: 'opt-help' }, spec.help),
        el('div', { class: 'opt-row' }, widget,
            value !== '' && !bound && spec.kind !== 'flag' ? el('button', { type: 'button', class: 'small btn-ghost reset', title: 'Clear', onclick: () => set('') }, icon('fa-xmark')) : null));
}

function ioOptionSections(node, specs) {
    const groups = new Map();
    for (const s of specs) {
        if (!groups.has(s.group)) groups.set(s.group, []);
        groups.get(s.group).push(s);
    }
    return [...groups].map(([g, list]) => {
        const anySet = list.some(s => s.name in node.options || s.name in node.params);
        return el('details', { class: 'insp-section', open: anySet || g === 'Trim' || g === 'Video encoding' },
            el('summary', { class: 'hint' }, g, anySet ? el('span', { class: 'chip', style: 'margin-left:6px' }, `${list.filter(s => s.name in node.options || s.name in node.params).length} set`) : null),
            list.map(s => ioOptionRow(node, s)));
    });
}

function nameValidator(kind, node) {
    return (v) => {
        if (!NAME_RE.test(v)) return 'Start with a letter; use letters, digits, - and _ (max 32).';
        if (S.doc.nodes.some(n => n.kind === kind && n.id !== node.id && n.name === v)) return `Another ${kind} is already called ${v}.`;
        return null;
    };
}

function inspectInput(node) {
    const idx = S.compiled?.inputs?.find(i => i.node === node.id)?.index;
    return [
        el('div', { class: 'insp-head' }, el('h2', {}, icon('fa-file-video', 'kind'), node.name),
            el('p', {}, 'One input file, read with ', el('code', {}, '-i'), '. You choose the actual file when you run the graph.',
                idx != null ? [' Its streams are ', el('code', {}, `[${idx}:v]`), ' and ', el('code', {}, `[${idx}:a]`), '.'] : '')),
        nodeIssues(node),
        el('div', { class: 'form-grid' },
            textField('Name', node.name, (v) => setNodeField(node, 'name', v), { key: `name:${node.id}`, mono: true, validate: nameValidator('input', node) }),
            el('label', {}, 'Sample file (pre-fills the Run dialog)',
                el('span', { class: 'opt-row' },
                    el('input', { type: 'text', value: node.sample_path || '', 'data-key': `sample:${node.id}`, placeholder: 'path in the gallery', spellcheck: 'false',
                        onchange: (ev) => setNodeField(node, 'sample_path', ev.target.value.trim() || null) }),
                    el('button', { type: 'button', class: 'small', onclick: () => openFileDialog({ title: `Sample file for ${node.name}`, multi: false,
                        start: node.sample_path ? node.sample_path.split('/').slice(0, -1).join('/') : '.',
                        onChoose: (paths) => setNodeField(node, 'sample_path', paths[0] || null) }) }, 'Browse…')))),
        section('Pads', padsTable(node)),
        section('Input options', el('p', { class: 'hint' }, 'Placed before ', el('code', {}, '-i'), '; they apply to this file only.')),
        ...ioOptionSections(node, S.io.inputs),
        section('Node', noteField(node)),
        nodeActions(node),
    ];
}

const OUTPUT_PRESETS = [
    { label: 'H.264 MP4', title: 'Plays everywhere', options: { 'c:v': 'libx264', crf: '20', preset: 'medium', pix_fmt: 'yuv420p', 'c:a': 'aac', 'b:a': '160k', movflags: '+faststart' } },
    { label: 'H.265 MP4', title: 'Smaller files, newer players', options: { 'c:v': 'libx265', crf: '24', preset: 'medium', pix_fmt: 'yuv420p', 'c:a': 'aac', 'b:a': '160k', movflags: '+faststart' } },
    { label: 'VP9 WebM', title: 'For browsers', options: { 'c:v': 'libvpx-vp9', crf: '32', 'b:v': '0', 'c:a': 'libopus', 'b:a': '128k' } },
    { label: 'Copy audio', title: 'Keep the audio stream unchanged', options: { 'c:a': 'copy' } },
    { label: 'No audio', title: 'Drop audio', options: { an: 'true' } },
];

function inspectOutput(node) {
    const out = S.compiled?.outputs?.find(o => o.node === node.id);
    const renamePad = (i, name) => mutate(() => {
        const n = nodeById(node.id);
        const old = n.pads[i].name;
        n.pads[i].name = name;
        for (const e of S.doc.edges) if (e.target === n.id && e.target_pad === old) e.target_pad = name;
    });
    const padRows = node.pads.map((p, i) => el('div', { class: 'row' },
        el('span', { class: `dot ${p.type}` }),
        el('input', { type: 'text', value: p.name, 'data-key': `pad:${node.id}:${i}`, spellcheck: 'false', onchange: (ev) => {
            const v = ev.target.value.trim();
            if (!NAME_RE.test(v) || node.pads.some((q, j) => j !== i && q.name === v)) { toast('Pad names must be unique: letters, digits, - and _.', true); renderInspector(); return; }
            renamePad(i, v);
        } }),
        el('select', { onchange: (ev) => mutate(() => { nodeById(node.id).pads[i].type = ev.target.value; }) },
            ['video', 'audio'].map(t => el('option', { value: t, selected: t === p.type }, t))),
        el('button', { type: 'button', class: 'small btn-ghost reset', title: 'Remove pad', onclick: () => mutate(() => { nodeById(node.id).pads.splice(i, 1); }) }, icon('fa-xmark'))));
    const addPad = (type) => mutate(() => {
        const n = nodeById(node.id);
        const base = type === 'video' ? 'v' : 'a';
        let name = base, k = 2;
        while (n.pads.some(p => p.name === name)) name = `${base}${k++}`;
        n.pads.push({ name, type });
    });
    return [
        el('div', { class: 'insp-head' }, el('h2', {}, icon('fa-file-export', 'kind'), node.name),
            el('p', {}, 'One output file. Each connected pad becomes a ', el('code', {}, '-map'), ', in this order.'),
            out?.maps?.length ? el('pre', { class: 'preview-code' }, out.maps.map(m => `-map ${m}`).join(' ')) : null),
        nodeIssues(node),
        el('div', { class: 'form-grid' },
            textField('Name', node.name, (v) => setNodeField(node, 'name', v), { key: `name:${node.id}`, mono: true, validate: nameValidator('output', node) }),
            textField('File name (template)', node.filename, (v) => setNodeField(node, 'filename', v), { key: `fn:${node.id}`, mono: true,
                validate: (v) => (!v.trim() ? 'Required' : v.includes('/') ? 'Just a file name; the folder is chosen when running.' : null) }),
            el('p', { class: 'hint' }, 'The extension picks the container (.mp4, .mkv, .webm, .gif, .jpg, .mp3 …). Placeholders: {stem} {output} {graph} {n} {date}.')),
        section('Pads', el('div', { class: 'out-pads' }, padRows),
            el('div', { class: 'insp-actions' },
                el('button', { type: 'button', class: 'small', onclick: () => addPad('video') }, el('span', { class: 'dot video' }), ' Add video pad'),
                el('button', { type: 'button', class: 'small', onclick: () => addPad('audio') }, el('span', { class: 'dot audio' }), ' Add audio pad')),
            padsTable(node)),
        section('Encoding presets', el('div', { class: 'presets' }, OUTPUT_PRESETS.map(p => el('button', { type: 'button', class: 'small', title: p.title,
            onclick: () => mutate(() => { Object.assign(nodeById(node.id).options, p.options); }) }, p.label)),
            el('button', { type: 'button', class: 'small btn-ghost', title: 'Remove all output options', onclick: () => mutate(() => { nodeById(node.id).options = {}; }) }, 'Clear'))),
        ...ioOptionSections(node, S.io.outputs),
        section('Node', noteField(node)),
        nodeActions(node),
    ];
}

function graphNodeParams(node, g) {
    if (!g.params.length) return section('Parameters', el('p', { class: 'hint' }, `${g.name} has no parameters.`));
    const set = (key, v) => mutate(() => {
        const n = nodeById(node.id);
        if (v === '') delete n.options[key]; else n.options[key] = v;
    }, { coalesce: `gopt:${node.id}:${key}` });
    return section('Parameters', el('p', { class: 'hint' }, 'Values for this use of the saved graph. Empty fields use its defaults.'),
        g.params.map(p => {
            const value = node.options[p.name] ?? '';
            const bound = boundWidget(node, [p.name]);
            return el('div', { class: `opt${value !== '' || bound ? ' set' : ''}` },
                el('div', { class: 'opt-top' }, el('span', { class: 'opt-name' }, p.name),
                    paramButton(node, [p.name], { base: p.name, description: p.description })),
                p.description ? el('div', { class: 'opt-help' }, p.description) : null,
                el('div', { class: 'opt-row' }, bound || [
                    el('input', { type: 'text', value, 'data-key': `gopt:${node.id}:${p.name}`, spellcheck: 'false',
                        placeholder: p.default === '' ? 'default: unset' : `default: ${p.default}`, onchange: (ev) => set(p.name, ev.target.value) }),
                    value !== '' ? el('button', { type: 'button', class: 'small btn-ghost reset', title: 'Use the default', onclick: () => set(p.name, '') }, icon('fa-xmark')) : null]));
        }));
}

function inspectGraphNode(node) {
    const g = S.libById.get(node.graph_id);
    return [
        el('div', { class: 'insp-head' }, el('h2', {}, icon('fa-cubes', 'kind'), g?.name || 'Missing graph'),
            el('p', {}, g ? (g.description || 'A saved graph used as one node.') : `Saved graph ${node.graph_id} is not in the library any more.`),
            g ? el('div', { class: 'links' }, el('span', { class: 'chip' }, `rev ${g.revision}`), g.filters.slice(0, 8).map(f => el('span', { class: 'chip mono' }, f))) : null),
        nodeIssues(node),
        el('p', { class: 'hint' }, "When the graph runs, this node is replaced by the saved graph's filters. Its pads are the saved graph's used input streams (left) and output pads (right)."),
        g ? graphNodeParams(node, g) : null,
        section('Pads', padsTable(node)),
        g ? el('div', { class: 'insp-actions' }, el('button', { type: 'button', class: 'small', onclick: () => openSaved(g.id) }, icon('fa-pen'), ' Open to edit')) : null,
        section('Node', noteField(node)),
        nodeActions(node),
    ];
}

// ---- links

function inspectEdge(index) {
    const e = S.doc.edges[index];
    const src = nodeById(e.source), dst = nodeById(e.target);
    const sp = padOf(e.source, 'out', e.source_pad), tp = padOf(e.target, 'in', e.target_pad);
    const link = linkFor(e);
    let explain;
    if (!link) explain = 'Fix the problems in the graph to see how this link is written.';
    else if (link.chained) explain = `The two filters are written as one chain, "${src?.filter},${dst?.filter}": no label is needed.`;
    else if (/^\d+:/.test(link.label)) explain = `The stream ${link.label} of input file #${link.label.split(':')[0]} feeds this pad directly.`;
    else explain = `Written as [${link.label}] after the source and ${dst?.kind === 'output' ? `as -map [${link.label}]` : 'before the target'}.`;
    return [
        el('div', { class: 'insp-head' }, el('h2', {}, icon('fa-link'), 'Link'),
            el('p', {}, el('span', { class: `dot ${sp?.type || 'video'}` }), ` ${sp?.type || ''} stream`)),
        el('table', { class: 'pad-table' }, el('tbody', {},
            el('tr', {}, el('td', {}, 'From'), el('td', {}, `${nodeLabel(src)} › ${sp?.name ?? e.source_pad} (#${e.source_pad})`)),
            el('tr', {}, el('td', {}, 'To'), el('td', {}, `${nodeLabel(dst)} › ${tp?.name ?? e.target_pad} (#${e.target_pad})`)),
            el('tr', {}, el('td', {}, 'In ffmpeg'), el('td', {}, link?.label ? el('code', {}, link.chained ? ',' : /^\d+:/.test(link.label) ? link.label : `[${link.label}]`) : '—')))),
        el('p', { class: 'hint', style: 'margin-top: 8px' }, explain),
        el('div', { class: 'insp-actions' },
            el('button', { type: 'button', class: 'small', onclick: () => {
                const r = canvas.getBoundingClientRect();
                showQuickAdd(r.left + r.width / 2 - 190, r.top + 80, { insertEdge: index });
            } }, icon('fa-plus'), ' Insert filter here…'),
            el('button', { type: 'button', class: 'small btn-danger', onclick: deleteSelection }, icon('fa-trash'), ' Delete link')),
    ];
}

// ---- whole graph

function graphParamsSection() {
    const go = (id) => { S.sel = { nodes: new Set([id]), edge: null }; renderAll(); centerOn(id); };
    const edit = (name, field, v) => mutate(() => { paramOf(name)[field] = v; }, { coalesce: `param:${name}:${field}` });
    const cards = S.doc.params.map(p => {
        const uses = paramUses(p.name);
        return el('div', { class: 'param-card' },
            el('div', { class: 'opt-row' },
                icon('fa-sliders'),
                el('input', { type: 'text', value: p.name, class: 'mono', 'data-key': `pname:${p.name}`, spellcheck: 'false', title: 'Parameter name', onchange: (ev) => {
                    const v = ev.target.value.trim();
                    if (v === p.name) return;
                    if (!NAME_RE.test(v)) { toast('Parameter names start with a letter; use letters, digits, - and _ (max 32).', true); renderInspector(); return; }
                    if (paramOf(v)) { toast(`There is already a parameter called ${v}.`, true); renderInspector(); return; }
                    renameParam(p.name, v);
                } }),
                el('button', { type: 'button', class: 'small btn-ghost reset', title: 'Remove the parameter (options keep its default as a fixed value)',
                    onclick: () => removeParam(p.name) }, icon('fa-trash'))),
            el('label', {}, 'Default', el('input', { type: 'text', value: p.default, 'data-key': `pdef:${p.name}`, spellcheck: 'false', placeholder: 'empty: leave the options unset',
                onchange: (ev) => edit(p.name, 'default', ev.target.value) })),
            el('label', {}, 'Description', el('input', { type: 'text', value: p.description, 'data-key': `pdesc:${p.name}`, maxlength: 1000,
                onchange: (ev) => edit(p.name, 'description', ev.target.value) })),
            el('div', { class: 'links' }, uses.length ? ['Sets ', uses.map(u => el('a', { class: 'chip mono', onclick: () => go(u.node.id) },
                `${u.node.kind === 'filter' ? u.node.id : nodeLabel(u.node)} › ${u.key}`))]
                : el('span', { class: 'bad' }, 'Not used by any option')));
    });
    return section(['Parameters ', el('span', { class: 'hint' }, `${S.doc.params.length}`)],
        el('p', { class: 'hint' }, 'Values of the graph that can be changed when running it, or on its node when it is used inside another graph. ',
            'To add one, click ', icon('fa-sliders'), ' next to an option of a node.'),
        cards);
}

function inspectGraph() {
    const c = S.compiled;
    const filters = S.doc.nodes.filter(n => n.kind === 'filter').length;
    const iface = (list) => list.map(p => el('span', { class: 'chip mono' }, el('span', { class: `dot ${p.type}` }), ` ${p.name}`));
    const pads = { inputs: [], outputs: [] };
    for (const n of S.doc.nodes) {
        if (n.kind === 'input') for (const p of INPUT_PADS) { if (S.doc.edges.some(e => e.source === n.id && e.source_pad === p.key)) pads.inputs.push({ name: `${n.name}:${p.key}`, type: p.type }); }
        if (n.kind === 'output') for (const p of n.pads) { if (S.doc.edges.some(e => e.target === n.id && e.target_pad === p.name)) pads.outputs.push({ name: `${n.name}:${p.name}`, type: p.type }); }
    }
    return [
        el('div', { class: 'insp-head' }, el('h2', {}, icon('fa-diagram-project'), 'Graph'),
            el('p', {}, S.meta.id ? `In the library · revision ${S.meta.revision}` : 'Not saved to the library yet.')),
        el('div', { class: 'form-grid' },
            textField('Description', S.meta.description, (v) => { S.meta.description = v; setDirty(true); saveDraft(); }, { key: 'meta:desc', area: true }),
            textField('Tags (comma separated)', S.meta.tags.join(', '), (v) => {
                S.meta.tags = v.split(',').map(t => t.trim()).filter(Boolean).slice(0, 20); setDirty(true); saveDraft();
            }, { key: 'meta:tags' })),
        section('Interface', el('p', { class: 'hint' }, 'What this graph looks like when added to another graph as a node.'),
            el('div', { class: 'links' }, 'In: ', pads.inputs.length ? iface(pads.inputs) : el('span', { class: 'hint' }, 'none')),
            el('div', { class: 'links', style: 'margin-top: 4px' }, 'Out: ', pads.outputs.length ? iface(pads.outputs) : el('span', { class: 'hint' }, 'none'))),
        graphParamsSection(),
        section('Summary', el('p', { class: 'hint' }, `${filters} filter(s), ${S.doc.edges.length} link(s). `,
            c ? (c.ok ? 'Ready to run.' : `${c.issues.filter(i => i.level === 'error').length} problem(s) to fix.`) : '')),
        el('p', { class: 'hint', style: 'margin-top: 16px' }, 'Select a node to edit it, or a wire to see how it is written in the filtergraph. Press Tab to add a filter.'),
    ];
}

// ------------------------------------------------------------------ compile

let compileTimer = null;
let compileSeq = 0;

function scheduleCompile(delay = 250) {
    clearTimeout(compileTimer);
    compileTimer = setTimeout(compileNow, delay);
}

async function compileNow() {
    const seq = ++compileSeq;
    let result;
    try {
        result = await api(`${API}/compile`, { method: 'POST', body: { graph: S.doc } });
    } catch (e) {
        result = { ok: false, issues: [{ level: 'error', message: e.message }], pads: {}, links: [], inputs: [], outputs: [],
                   filter_complex: '', filter_complex_pretty: '', command: '' };
    }
    if (seq !== compileSeq) return;
    S.compiled = result;
    renderCompiled();
}

function renderCompiled() {
    const c = S.compiled;
    $('fcText').textContent = c.ok ? (c.filter_complex_pretty || '(no filters: input streams are mapped straight to the outputs)') : '— fix the problems first —';
    $('cmdText').textContent = c.ok ? c.command : '';
    const errors = c.issues.filter(i => i.level === 'error');
    const pc = $('problemCount');
    pc.textContent = c.issues.filter(i => i.level !== 'info').length || '';
    pc.classList.toggle('bad', errors.length > 0);
    $('problems').replaceChildren(...(c.issues.length ? c.issues.map(i => el('li', {
        class: i.level, onclick: () => { if (i.node && nodeById(i.node)) { S.sel = { nodes: new Set([i.node]), edge: null }; renderAll(); centerOn(i.node); } },
    }, icon(i.level === 'error' ? 'fa-circle-xmark' : i.level === 'warning' ? 'fa-triangle-exclamation' : 'fa-circle-info'),
        el('span', {}, i.message), i.node ? el('span', { class: 'where' }, nodeLabel(nodeById(i.node))) : null))
        : [el('li', { class: 'info' }, icon('fa-circle-check'), el('span', {}, 'No problems.'))]));
    $('btnRun').title = c.ok ? 'Run this graph on files' : 'Fix the problems first (see the Problems tab)';
    renderNodes();
    renderEdges();
    renderInspector();
}

function centerOn(id) {
    const n = nodeById(id);
    if (!n?.position) return;
    const r = canvas.getBoundingClientRect();
    const s = S.nodeSize.get(id) || { w: 200, h: 80 };
    S.view.x = r.width / 2 - (n.position.x + s.w / 2) * S.view.k;
    S.view.y = r.height / 2 - (n.position.y + s.h / 2) * S.view.k;
    applyView();
}

// ------------------------------------------------------------------ palette, library, examples

function dragItem(payload) {
    return (ev) => {
        ev.dataTransfer.setData('application/x-studio-node', JSON.stringify(payload));
        ev.dataTransfer.effectAllowed = 'copy';
    };
}

function renderPalette() {
    const q = $('paletteSearch').value.trim().toLowerCase();
    const groups = new Map();
    const add = (cat, item) => { if (!groups.has(cat)) groups.set(cat, []); groups.get(cat).push(item); };
    const ioItem = (kind, label, desc) => el('div', { class: 'pal-item', draggable: 'true', ondragstart: dragItem({ kind }), onclick: () => addNode(kind) },
        el('span', { class: 'nm' }, icon(KIND_ICON[kind]), label), el('span', { class: 'ds' }, desc));
    if (!q || 'input output file'.includes(q)) {
        add('Files', ioItem('input', 'Input file', 'A file read with -i'));
        add('Files', ioItem('output', 'Output file', 'A file written with -map'));
    }
    for (const g of S.library) {
        if (q && !g.name.toLowerCase().includes(q) && !g.description.toLowerCase().includes(q)) continue;
        add('Saved graphs', el('div', { class: 'pal-item', draggable: 'true', ondragstart: dragItem({ kind: 'graph', graph_id: g.id }), onclick: () => addNode('graph', { graph_id: g.id }), title: g.description },
            el('span', { class: 'nm' }, icon('fa-cubes'), g.name), el('span', { class: 'ds' }, g.description || g.filters.join(', '))));
    }
    const order = ['Resize', 'Rotate & flip', 'Blur & sharpen', 'Color', 'Time', 'Compose', 'Text & draw', 'GIF', 'Repair', 'Audio', 'Pass-through'];
    const popular = S.catalog.filter(f => f.popular && !q);
    for (const f of popular) add(`Common: ${f.category}`, filterItem(f));
    if (q) {
        for (const f of S.catalog) {
            if (f.name.includes(q) || f.description.toLowerCase().includes(q) || f.category.toLowerCase().includes(q)) add(f.category, filterItem(f));
        }
    } else {
        for (const f of S.catalog) if (!f.popular) add(`All: ${f.category}`, filterItem(f));
    }
    const rank = (name) => {
        if (name === 'Files') return -2;
        if (name === 'Saved graphs') return -1;
        const base = name.replace(/^(Common|All): /, '');
        const i = order.indexOf(base);
        return (name.startsWith('All: ') ? 100 : 0) + (i < 0 ? 50 : i);
    };
    const host = $('palette');
    host.replaceChildren(...[...groups].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0])).map(([name, items]) =>
        el('details', { class: 'pal-group', open: Boolean(q) || !name.startsWith('All: ') },
            el('summary', {}, `${name.replace(/^Common: /, '')} `, el('span', { class: 'hint' }, `(${items.length})`)), items)));
    if (!groups.size) host.append(el('p', { class: 'hint pad' }, 'No filters match.'));
}

function filterItem(f) {
    return el('div', {
        class: `pal-item${f.blocked ? ' blocked' : ''}`, draggable: f.blocked ? null : 'true', title: f.blocked ? 'Not available: reads/writes server files or loads code' : f.description,
        ondragstart: dragItem({ kind: 'filter', filter: f.name }), onclick: () => addNode('filter', { filter: f.name }),
    }, el('span', { class: 'nm' }, f.name, el('span', { class: 'io' }, `${f.inputs}->${f.outputs}`)), el('span', { class: 'ds' }, f.description));
}

async function loadLibrary() {
    try {
        const r = await api(`${API}/graphs`);
        S.library = r.items;
        S.libById = new Map(r.items.map(g => [g.id, g]));
    } catch (e) {
        toast(`Could not load the library: ${e.message}`, true);
    }
    renderLibrary();
    renderPalette();
    renderAll();
}

function renderLibrary() {
    const q = $('librarySearch').value.trim().toLowerCase();
    const items = S.library.filter(g => !q || g.name.toLowerCase().includes(q) || g.description.toLowerCase().includes(q)
        || g.tags.some(t => t.toLowerCase().includes(q)) || g.filters.some(f => f.includes(q)));
    const host = $('library');
    if (!S.library.length) {
        host.replaceChildren(el('p', { class: 'hint' }, 'Nothing saved yet. Build or open a graph and press Save; saved graphs can be reused here and inside other graphs.'));
        return;
    }
    host.replaceChildren(...items.map(g => el('div', { class: `card${g.id === S.meta.id ? ' current' : ''}` },
        el('h4', {}, g.name),
        g.description ? el('p', {}, g.description) : null,
        el('div', { class: 'meta' }, g.tags.map(t => el('span', { class: 'chip' }, t)), g.filters.slice(0, 6).map(f => el('span', { class: 'chip mono' }, f))),
        el('div', { class: 'meta' }, el('span', { class: 'hint' }, `in ${g.interface.inputs.map(p => p.name).join(', ') || '—'} · out ${g.interface.outputs.map(p => p.name).join(', ') || '—'} · ${new Date(g.updated_at).toLocaleDateString()}`)),
        g.params.length ? el('div', { class: 'meta' }, el('span', { class: 'hint' }, icon('fa-sliders'), ` ${g.params.map(p => p.name).join(', ')}`)) : null,
        el('div', { class: 'actions' },
            el('button', { type: 'button', class: 'small', onclick: () => openSaved(g.id) }, icon('fa-folder-open'), ' Open'),
            el('button', { type: 'button', class: 'small', title: 'Use it as one node in the current graph', disabled: g.id === S.meta.id, onclick: () => addNode('graph', { graph_id: g.id }) }, icon('fa-plus'), ' Add as node'),
            el('button', { type: 'button', class: 'small btn-ghost btn-danger', title: 'Delete from library', onclick: () => deleteSaved(g) }, icon('fa-trash'))))));
    if (!items.length) host.append(el('p', { class: 'hint' }, 'No saved graphs match.'));
}

async function openSaved(id) {
    if (!confirmDiscard()) return;
    try {
        const g = await api(`${API}/graphs/${encodeURIComponent(id)}`);
        await loadDoc(g.graph, { id: g.id, name: g.name, description: g.description, tags: g.tags, revision: g.revision });
    } catch (e) {
        toast(e.message, true);
    }
}

async function deleteSaved(g) {
    if (!confirm(`Delete "${g.name}" from the library? Runs that used it are not affected.`)) return;
    try {
        await api(`${API}/graphs/${encodeURIComponent(g.id)}`, { method: 'DELETE' });
        if (S.meta.id === g.id) { S.meta.id = null; S.meta.revision = null; setDirty(true); saveDraft(); history.replaceState(null, '', '/studio'); }
        toast(`Deleted ${g.name}`);
        loadLibrary();
    } catch (e) {
        toast(e.message, true);
    }
}

async function loadExamples() {
    try {
        S.examples = (await api(`${API}/examples`)).items;
    } catch (e) {
        $('examples').replaceChildren(el('p', { class: 'hint' }, `Could not load examples: ${e.message}`));
        return;
    }
    const cats = new Map();
    for (const ex of S.examples) {
        if (!cats.has(ex.category)) cats.set(ex.category, []);
        cats.get(ex.category).push(ex);
    }
    const host = $('examples');
    host.replaceChildren();
    for (const [cat, list] of cats) {
        host.append(el('div', { class: 'cat-title' }, cat));
        for (const ex of list) {
            host.append(el('div', { class: 'card' },
                el('h4', {}, ex.title),
                el('p', {}, ex.summary),
                el('details', {}, el('summary', {}, 'How it works'), el('p', {}, ex.explanation), el('pre', {}, ex.command)),
                el('div', { class: 'actions' }, el('button', { type: 'button', class: 'small primary', onclick: async () => {
                    if (!confirmDiscard()) return;
                    await loadDoc(clone(ex.graph), { name: ex.title, description: `${ex.summary}\n\n${ex.explanation}`, tags: [ex.category.toLowerCase()] }, { dirty: true });
                } }, icon('fa-folder-open'), ' Open'))));
        }
    }
}

// ------------------------------------------------------------------ save / import

function openSaveDialog(asCopy) {
    $('saveTitle').textContent = asCopy ? 'Save a copy' : 'Save to library';
    $('saveName').value = asCopy && S.meta.id ? `${S.meta.name} (copy)` : S.meta.name;
    $('saveDesc').value = S.meta.description;
    $('saveTags').value = S.meta.tags.join(', ');
    $('saveMsg').textContent = '';
    $('saveDialog').dataset.copy = asCopy ? '1' : '';
    $('saveDialog').showModal();
    $('saveName').select();
}

async function persist({ asNew, name, description, tags }) {
    const body = { name, description, tags, graph: S.doc, revision: asNew ? null : S.meta.revision };
    const g = asNew
        ? await api(`${API}/graphs`, { method: 'POST', body })
        : await api(`${API}/graphs/${encodeURIComponent(S.meta.id)}`, { method: 'PUT', body });
    S.meta = { id: g.id, name: g.name, description: g.description, tags: g.tags, revision: g.revision };
    $('graphName').value = g.name;
    setDirty(false);
    saveDraft();
    history.replaceState(null, '', `/studio?graph=${encodeURIComponent(g.id)}`);
    toast(`Saved "${g.name}"`);
    await loadLibrary();
}

async function save() {
    if (!S.meta.id) { openSaveDialog(false); return; }
    try {
        await persist({ asNew: false, name: $('graphName').value.trim() || S.meta.name, description: S.meta.description, tags: S.meta.tags });
    } catch (e) {
        toast(e.message, true);
    }
}

$('saveForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const tags = $('saveTags').value.split(',').map(t => t.trim()).filter(Boolean);
    try {
        await persist({ asNew: true, name: $('saveName').value.trim(), description: $('saveDesc').value, tags });
        $('saveDialog').close();
    } catch (e) {
        $('saveMsg').className = 'msg error';
        $('saveMsg').textContent = e.message;
    }
});

$('importForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const text = $('importText').value.trim();
    if (!text) return;
    try {
        const r = await api(`${API}/import`, { method: 'POST', body: { text } });
        const errors = r.issues.filter(i => i.level === 'error');
        $('importIssues').replaceChildren(...r.issues.map(i => el('li', { class: i.level }, icon(i.level === 'error' ? 'fa-circle-xmark' : 'fa-triangle-exclamation'), el('span', {}, i.message))));
        if (errors.length && !r.graph.nodes.length) return;
        if (!confirmDiscard()) return;
        await loadDoc(r.graph, { name: 'Imported graph', description: `Imported from:\n${text}` }, { dirty: true });
        if (!r.issues.length) $('importDialog').close();
        else toast('Imported with warnings: see the import dialog.');
    } catch (e) {
        $('importIssues').replaceChildren(el('li', { class: 'error' }, icon('fa-circle-xmark'), el('span', {}, e.message)));
    }
});

// ------------------------------------------------------------------ file browser

const FB = { opts: null, listing: null, selected: new Set() };

function fmtSize(n) {
    if (n < 1024) return `${n} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let v = n, u = -1;
    do { v /= 1024; u++; } while (v >= 1024 && u < units.length - 1);
    return `${v.toFixed(v < 10 ? 1 : 0)} ${units[u]}`;
}

function openFileDialog(opts) {
    FB.opts = opts;
    FB.selected = new Set(opts.selected || []);
    $('fileTitle').textContent = opts.title;
    $('fileAllVideos').hidden = !opts.multi;
    $('fileNewFolder').hidden = !opts.folder;
    $('fileFilter').value = '';
    $('fileDialog').showModal();
    browse(opts.start || '.').catch(() => browse('.'));
}

async function browse(path) {
    const listing = await api(`${API}/media?path=${encodeURIComponent(path || '.')}`);
    FB.listing = listing;
    renderFiles();
}

function renderFiles() {
    const L = FB.listing;
    if (!L) return;
    const parts = L.path === '.' ? [] : L.path.split('/');
    $('fileCrumbs').replaceChildren(el('a', { onclick: () => browse('.') }, icon('fa-house'), ' gallery'),
        ...parts.map((p, i) => [' / ', el('a', { onclick: () => browse(parts.slice(0, i + 1).join('/')) }, p)]).flat());
    const q = $('fileFilter').value.trim().toLowerCase();
    const rows = [];
    if (L.parent != null) rows.push(el('div', { class: 'file-row dir', onclick: () => browse(L.parent) }, el('span', { class: 'ico' }, icon('fa-arrow-up')), el('span', { class: 'nm' }, '..')));
    for (const d of L.dirs) {
        if (q && !d.toLowerCase().includes(q)) continue;
        rows.push(el('div', { class: 'file-row dir', onclick: () => browse(L.path === '.' ? d : `${L.path}/${d}`) },
            el('span', { class: 'ico' }, icon('fa-folder')), el('span', { class: 'nm' }, d)));
    }
    for (const f of L.files) {
        if (FB.opts.folder) break;
        if (q && !f.name.toLowerCase().includes(q)) continue;
        const checked = FB.selected.has(f.path);
        rows.push(el('div', { class: 'file-row', onclick: () => {
            if (FB.opts.multi) { if (checked) FB.selected.delete(f.path); else FB.selected.add(f.path); }
            else FB.selected = new Set([f.path]);
            renderFiles();
        }, ondblclick: () => { FB.selected = new Set([f.path]); chooseFiles(); } },
            el('input', { type: FB.opts.multi ? 'checkbox' : 'radio', checked, tabindex: '-1' }),
            el('span', { class: 'ico' }, icon(f.kind === 'video' ? 'fa-film' : f.kind === 'audio' ? 'fa-music' : 'fa-image')),
            el('span', { class: 'nm' }, f.name), el('span', { class: 'sz' }, fmtSize(f.size))));
    }
    if (!L.dirs.length && !L.files.length) rows.push(el('div', { class: 'file-row' }, el('span', { class: 'hint' }, 'No media files here.')));
    if (L.truncated) rows.push(el('div', { class: 'file-row' }, el('span', { class: 'hint' }, 'Too many entries: only the first ones are shown. Use the filter.')));
    $('fileList').replaceChildren(...rows);
    if (FB.opts.folder) {
        $('fileCount').textContent = `Folder: ${L.path}`;
        $('fileChoose').disabled = false;
        $('fileChoose').textContent = 'Choose this folder';
        return;
    }
    $('fileChoose').textContent = 'Choose';
    $('fileCount').textContent = FB.selected.size ? `${FB.selected.size} selected` : '';
    $('fileChoose').disabled = !FB.selected.size;
}

function chooseFiles() {
    const cb = FB.opts.onChoose;
    const files = FB.opts.folder ? [FB.listing.path] : [...FB.selected];
    $('fileDialog').close();
    cb(files);
}

$('fileNewFolder').addEventListener('click', () => {
    const name = prompt('Name of the new folder (created when the job runs):');
    if (!name) return;
    const parts = name.split('/').map(p => p.trim()).filter(Boolean);
    if (!parts.length || parts.some(p => p === '.' || p === '..')) { toast('Use a plain folder name.', true); return; }
    const cb = FB.opts.onChoose;
    const base = FB.listing.path === '.' ? '' : `${FB.listing.path}/`;
    $('fileDialog').close();
    cb([`${base}${parts.join('/')}`]);
});

$('fileFilter').addEventListener('input', renderFiles);
$('fileChoose').addEventListener('click', chooseFiles);
$('fileAllVideos').addEventListener('click', () => {
    for (const f of FB.listing?.files || []) if (f.kind === 'video') FB.selected.add(f.path);
    renderFiles();
});

// ------------------------------------------------------------------ run dialog

const RUN = { inputs: {}, outputs: {}, params: {} };

function slug(s) {
    return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'graph';
}
const dirOf = (p) => (p.includes('/') ? p.split('/').slice(0, -1).join('/') : '.');
const joinPath = (dir, name) => (!dir || dir === '.' ? name : `${dir.replace(/\/+$/, '')}/${name}`);

function openRun() {
    const c = S.compiled;
    if (!c || !c.ok) {
        toast('Fix the problems first (see the Problems tab).', true);
        showBottomTab('problems');
        return;
    }
    if (!c.outputs.length) { toast('Add an output node first.', true); return; }
    for (const inp of c.inputs) {
        if (!RUN.inputs[inp.node]?.length) {
            const sample = nodeById(inp.node)?.sample_path;
            RUN.inputs[inp.node] = sample ? [sample] : [];
        }
    }
    for (const out of c.outputs) {
        const node = nodeById(out.node);
        const r = RUN.outputs[out.node] || (RUN.outputs[out.node] = { dir: 'studio', name: node.filename });
        if (!r.touched) r.name = node.filename;
    }
    $('runGraphName').textContent = `"${S.meta.name}"`;
    for (const name of Object.keys(RUN.params)) if (!paramOf(name)) delete RUN.params[name];
    $('runMsg').textContent = '';
    renderRunDialog();
    $('runDialog').showModal();
}

function runItems() {
    const c = S.compiled;
    const multi = c.inputs.filter(i => (RUN.inputs[i.node] || []).length > 1);
    if (multi.length > 1) return { error: 'Only one input can have several files (that input is processed as a batch).' };
    for (const i of c.inputs) if (!(RUN.inputs[i.node] || []).length) return { error: `Choose a file for input "${i.name}".` };
    const batch = multi[0];
    const primary = batch || c.inputs[0];
    const files = batch ? RUN.inputs[batch.node] : [null];
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const width = String(files.length).length;
    const items = files.map((file, idx) => {
        const inputs = {};
        for (const i of c.inputs) inputs[i.node] = batch && i.node === batch.node ? file : RUN.inputs[i.node][0];
        const src = primary ? inputs[primary.node] : '';
        const base = src ? src.split('/').pop() : 'output';
        const dot = base.lastIndexOf('.');
        const vars = {
            stem: dot > 0 ? base.slice(0, dot) : base, name: base, ext: dot > 0 ? base.slice(dot + 1) : '',
            graph: slug(S.meta.name), n: String(idx + 1).padStart(width, '0'), date,
        };
        const outputs = {};
        for (const o of c.outputs) {
            const r = RUN.outputs[o.node];
            const name = r.name.replace(/\{(\w+)\}/g, (m, k) => (k === 'output' ? o.name : k in vars ? vars[k] : m));
            outputs[o.node] = joinPath(r.dir.trim(), name);
        }
        return { inputs, outputs };
    });
    const seen = new Set();
    for (const it of items) for (const p of Object.values(it.outputs)) {
        if (seen.has(p)) return { items, error: `Two runs would write ${p}: add {stem} or {n} to the file name.` };
        seen.add(p);
    }
    return { items };
}

function renderRunDialog() {
    const c = S.compiled;
    // Until the user picks a folder, outputs go next to the (first) input file.
    const primary = c.inputs.find(i => (RUN.inputs[i.node] || []).length > 1) || c.inputs[0];
    const first = primary ? (RUN.inputs[primary.node] || [])[0] : null;
    for (const o of c.outputs) {
        const r = RUN.outputs[o.node];
        if (!r.dirTouched) r.dir = first && !first.startsWith('/') ? dirOf(first) : 'studio';
    }
    $('runInputs').replaceChildren(...c.inputs.map(i => {
        const files = RUN.inputs[i.node] || [];
        const browseBtn = el('button', { type: 'button', class: 'small', onclick: () => openFileDialog({
            title: `Files for input "${i.name}"`, multi: true, selected: files,
            start: files[0] && !files[0].startsWith('/') ? dirOf(files[0]) : '.',
            onChoose: (paths) => { RUN.inputs[i.node] = paths; renderRunDialog(); },
        }) }, icon('fa-folder-open'), ' Browse…');
        let fields;
        if (files.length > 1) {
            fields = [el('div', { class: 'line' }, el('span', { class: 'hint' }, `${files.length} files: one run each`), browseBtn,
                el('button', { type: 'button', class: 'small btn-ghost', onclick: () => { RUN.inputs[i.node] = []; renderRunDialog(); } }, 'Clear')),
                el('div', { class: 'files' }, files.slice(0, 30).map(f => el('span', { class: 'chip mono' }, f.split('/').pop())), files.length > 30 ? el('span', { class: 'hint' }, `+${files.length - 30} more`) : null)];
        } else {
            fields = [el('div', { class: 'line' }, el('input', { type: 'text', value: files[0] || '', placeholder: 'path in the gallery, e.g. trips/clip.mp4', spellcheck: 'false',
                onchange: (ev) => { RUN.inputs[i.node] = ev.target.value.trim() ? [ev.target.value.trim()] : []; renderRunDialog(); } }), browseBtn)];
        }
        return el('div', { class: 'run-row' }, el('div', { class: 'slot' }, el('span', { class: 'chip input' }, 'in'), ' ', i.name), el('div', { class: 'fields' }, fields));
    }));
    $('runOutputs').replaceChildren(...c.outputs.map(o => {
        const r = RUN.outputs[o.node];
        return el('div', { class: 'run-row' }, el('div', { class: 'slot' }, el('span', { class: 'chip output' }, 'out'), ' ', o.name),
            el('div', { class: 'fields' },
                el('div', { class: 'line' },
                    el('input', { type: 'text', value: r.dir, title: 'Folder, relative to the gallery root', spellcheck: 'false',
                        onchange: (ev) => { r.dir = ev.target.value.trim() || '.'; r.dirTouched = true; renderRunDialog(); } }),
                    el('button', { type: 'button', class: 'small', onclick: () => openFileDialog({
                        title: `Folder for output "${o.name}"`, folder: true, start: r.dir,
                        onChoose: ([dir]) => { r.dir = dir || '.'; r.dirTouched = true; renderRunDialog(); },
                    }) }, icon('fa-folder'), ' Folder…')),
                el('div', { class: 'line' }, el('input', { type: 'text', value: r.name, title: 'File name template', spellcheck: 'false',
                    onchange: (ev) => { r.name = ev.target.value.trim(); r.touched = true; renderRunDialog(); } }))));
    }));
    $('runParamsBox').hidden = !S.doc.params.length;
    $('runParams').replaceChildren(...S.doc.params.map(p => {
        const changed = p.name in RUN.params;
        return el('div', { class: 'run-row' }, el('div', { class: 'slot' }, icon('fa-sliders'), ' ', p.name),
            el('div', { class: 'fields' },
                el('div', { class: 'line' },
                    el('input', { type: 'text', value: changed ? RUN.params[p.name] : p.default, spellcheck: 'false',
                        placeholder: 'empty: leave the options unset', title: p.description || p.name,
                        onchange: (ev) => { if (ev.target.value === p.default) delete RUN.params[p.name]; else RUN.params[p.name] = ev.target.value; renderRunDialog(); } }),
                    changed ? el('button', { type: 'button', class: 'small btn-ghost', title: `Back to the default (${p.default || 'unset'})`,
                        onclick: () => { delete RUN.params[p.name]; renderRunDialog(); } }, 'Default') : null),
                p.description ? el('div', { class: 'hint' }, p.description) : null));
    }));
    const { items, error } = runItems();
    $('runPreview').replaceChildren(...(items || []).slice(0, 200).map((it, i) => el('tr', {},
        el('td', {}, `${i + 1}`),
        el('td', {}, Object.values(it.inputs).join(' + ')),
        el('td', {}, '→'),
        el('td', {}, Object.values(it.outputs).join(', ')))));
    $('runSummary').textContent = items ? `${items.length} job(s)` : '';
    $('runSubmit').textContent = '';
    $('runSubmit').append(icon('fa-play'), items && items.length > 1 ? ` Queue ${items.length} jobs` : ' Queue job');
    $('runSubmit').disabled = Boolean(error);
    $('runMsg').className = `msg${error ? ' error' : ''}`;
    $('runMsg').textContent = error || '';
}

$('runForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const { items, error } = runItems();
    if (error) return;
    $('runSubmit').disabled = true;
    try {
        const r = await api(`${API}/run`, { method: 'POST', body: {
            graph: S.doc, graph_id: S.meta.id, graph_name: S.meta.name, items, params: RUN.params, overwrite: $('runOverwrite').checked,
        } });
        $('runDialog').close();
        toast(`Queued ${r.jobs.length} job(s)`);
        showBottomTab('runs');
        refreshRuns();
    } catch (e) {
        $('runMsg').className = 'msg error';
        $('runMsg').textContent = e.message;
        $('runSubmit').disabled = false;
    }
});

// ------------------------------------------------------------------ runs panel

const RUNS = { expanded: new Set(), logs: new Map(), timer: null };
const ACTIVE = new Set(['queued', 'running']);

function fmtDuration(job) {
    if (!job.started_at) return '';
    const end = job.finished_at ? new Date(job.finished_at) : new Date();
    let s = Math.max(0, Math.round((end - new Date(job.started_at)) / 1000));
    const h = Math.floor(s / 3600); s -= h * 3600;
    const m = Math.floor(s / 60); s -= m * 60;
    return h ? `${h}h ${m}m` : m ? `${m}m ${s}s` : `${s}s`;
}

const VIDEO_EXT = /\.(mp4|m4v|mov|webm|mkv)$/i;

async function loadJobLog(id) {
    try {
        const page = await api(`/v1/jobs/${encodeURIComponent(id)}/logs?limit=1000`);
        RUNS.logs.set(id, page.lines.map(l => `${new Date(l.ts).toLocaleTimeString()}  ${l.message}`).join('\n') || 'No log lines yet.');
    } catch (e) {
        RUNS.logs.set(id, `Could not load the log: ${e.message}`);
    }
}

async function openJobGraph(item) {
    if (!confirmDiscard()) return;
    try {
        const doc = await api(`${API}/jobs/${encodeURIComponent(item.job.id)}/graph`);
        await loadDoc(doc, { name: `${item.params.graph_name} (from run)`, description: `Graph used by run ${item.job.id.slice(0, 8)}` }, { dirty: true });
    } catch (e) {
        toast(e.message, true);
    }
}

async function refreshRuns() {
    clearTimeout(RUNS.timer);
    let delay = 15000;
    try {
        const params = new URLSearchParams({ limit: '50' });
        if ($('runFilter').value) params.set('status', $('runFilter').value);
        const page = await api(`${API}/jobs?${params}`);
        const active = page.items.filter(i => ACTIVE.has(i.job.status));
        for (const it of page.items) if (RUNS.expanded.has(it.job.id) && (ACTIVE.has(it.job.status) || !RUNS.logs.has(it.job.id))) await loadJobLog(it.job.id);
        renderRuns(page);
        $('runCount').textContent = active.length || '';
        if (active.length) delay = 2500;
    } catch (e) {
        $('runRows').replaceChildren(el('tr', {}, el('td', { colspan: '6', class: 'err' }, `Could not load runs: ${e.message}`)));
    }
    RUNS.timer = setTimeout(refreshRuns, delay);
}

function renderRuns(page) {
    const rows = [];
    for (const it of page.items) {
        const job = it.job, p = it.params, r = it.result;
        const outs = Object.values(p.outputs || {});
        const progress = job.status === 'running'
            ? el('td', {}, el('div', { class: 'bar' }, Object.assign(el('div'), { style: `width:${job.progress_percent ?? 0}%` })),
                el('div', { class: 'stage' }, `${job.progress_percent ?? 0}% · ${job.progress_stage || 'starting'}`))
            : el('td', {}, job.status === 'failed' ? el('div', { class: 'err' }, job.error_message || 'failed')
                : job.status === 'succeeded' && r ? el('div', { class: 'stage' }, `done in ${fmtDuration(job)}`)
                : el('div', { class: 'stage' }, job.progress_stage || (job.status === 'queued' && job.attempt_count && job.error_message ? `retrying: ${job.error_message}` : '')));
        const actions = el('td', { class: 'actions' },
            el('button', { type: 'button', class: 'small', onclick: async () => {
                if (RUNS.expanded.has(job.id)) RUNS.expanded.delete(job.id); else { RUNS.expanded.add(job.id); await loadJobLog(job.id); }
                renderRuns(page);
            } }, RUNS.expanded.has(job.id) ? 'Hide log' : 'Log'),
            ACTIVE.has(job.status) && !job.cancel_requested ? el('button', { type: 'button', class: 'small', onclick: async () => {
                try { await api(`/v1/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' }); } catch (e) { toast(e.message, true); }
                refreshRuns();
            } }, 'Cancel') : null,
            el('button', { type: 'button', class: 'small btn-ghost', title: 'Open the graph this run used', onclick: () => openJobGraph(it) }, icon('fa-diagram-project')),
            job.status === 'succeeded' ? outs.map(o => el('a', { class: 'btn btn-sm btn-ghost', href: VIDEO_EXT.test(o) ? `/video/${o.split('/').map(encodeURIComponent).join('/')}` : `/file/${o.split('/').map(encodeURIComponent).join('/')}`,
                target: '_blank', rel: 'noopener', title: `Open ${o}` }, icon('fa-up-right-from-square'))) : null,
            job.status === 'succeeded' && outs[0] ? el('a', { class: 'btn btn-sm btn-ghost', href: `/page/${dirOf(outs[0]) === '.' ? '' : dirOf(outs[0]).split('/').map(encodeURIComponent).join('/')}`, title: 'Show the folder in the gallery' }, icon('fa-images')) : null);
        rows.push(el('tr', {},
            el('td', {}, p.graph_name, p.items > 1 ? el('div', { class: 'hint' }, `${p.item} of ${p.items}`) : null),
            el('td', { class: 'paths' }, Object.values(p.inputs || {}).join(' + '), ' → ', outs.join(', ')),
            el('td', {}, el('span', { class: `badge ${job.status}` }, job.cancel_requested && job.status === 'running' ? 'canceling' : job.status)),
            progress,
            el('td', {}, job.created_at ? new Date(job.created_at).toLocaleString() : ''),
            actions));
        if (RUNS.expanded.has(job.id)) {
            rows.push(el('tr', {}, el('td', { colspan: '6' },
                p.command ? el('pre', { class: 'log' }, p.command) : null,
                el('pre', { class: 'log' }, RUNS.logs.get(job.id) || 'Loading…'))));
        }
    }
    if (!rows.length) rows.push(el('tr', {}, el('td', { colspan: '6', class: 'hint' }, 'No runs yet. Press Run to process files with this graph.')));
    $('runRows').replaceChildren(...rows);
}

$('runFilter').addEventListener('change', refreshRuns);

// ------------------------------------------------------------------ panels and toolbar

function showBottomTab(name) {
    document.querySelectorAll('[data-btab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.btab === name)));
    document.querySelectorAll('[data-bpanel]').forEach(p => { p.hidden = p.dataset.bpanel !== name; });
    $('bottom').classList.remove('collapsed');
    if (name === 'runs') refreshRuns();
}

function showSideTab(name) {
    document.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    document.querySelectorAll('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== name; });
}

document.querySelectorAll('[data-btab]').forEach(b => b.addEventListener('click', () => showBottomTab(b.dataset.btab)));
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => showSideTab(b.dataset.tab)));
document.querySelectorAll('[data-open-tab]').forEach(a => a.addEventListener('click', (ev) => { ev.preventDefault(); showSideTab(a.dataset.openTab); }));
$('btnBottomToggle').addEventListener('click', () => $('bottom').classList.toggle('collapsed'));
document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {
    const text = $(b.dataset.copy).textContent;
    try { await navigator.clipboard.writeText(text); toast('Copied'); } catch (e) {
        const range = document.createRange();
        range.selectNodeContents($(b.dataset.copy));
        getSelection().removeAllRanges();
        getSelection().addRange(range);
        toast('Press Ctrl+C to copy');
    }
}));
document.querySelectorAll('dialog [data-close]').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));

$('paletteSearch').addEventListener('input', renderPalette);
$('librarySearch').addEventListener('input', renderLibrary);
$('graphName').addEventListener('change', () => {
    S.meta.name = $('graphName').value.trim() || 'Untitled graph';
    $('graphName').value = S.meta.name;
    setDirty(true);
    saveDraft();
});
$('btnNew').addEventListener('click', newGraph);
$('btnSave').addEventListener('click', save);
$('btnSaveAs').addEventListener('click', () => openSaveDialog(true));
$('btnImport').addEventListener('click', () => { $('importIssues').replaceChildren(); $('importDialog').showModal(); $('importText').focus(); });
$('emptyImport').addEventListener('click', (ev) => { ev.preventDefault(); $('btnImport').click(); });
$('btnUndo').addEventListener('click', undo);
$('btnRedo').addEventListener('click', redo);
$('btnLayout').addEventListener('click', () => { autoLayout(true); fitView(); });
$('btnFit').addEventListener('click', fitView);
$('btnAdd').addEventListener('click', () => {
    const r = canvas.getBoundingClientRect();
    showQuickAdd(r.left + r.width / 2 - 190, r.top + 60, S.sel.edge != null ? { insertEdge: S.sel.edge } : {});
});
$('btnGuide').addEventListener('click', () => $('guideDialog').showModal());
$('btnRun').addEventListener('click', openRun);
$('showLabels').addEventListener('change', (ev) => { S.showLabels = ev.target.checked; renderEdges(); });

document.addEventListener('keydown', (ev) => {
    const mod = ev.ctrlKey || ev.metaKey;
    if (mod && ev.key.toLowerCase() === 's') { ev.preventDefault(); save(); return; }
    if (document.querySelector('dialog[open]') || !$('quickAdd').hidden) return;
    const typing = ev.target.closest?.('input, textarea, select, [contenteditable]');
    if (typing) return;
    if (mod && ev.key.toLowerCase() === 'z') { ev.preventDefault(); if (ev.shiftKey) redo(); else undo(); return; }
    if (mod && ev.key.toLowerCase() === 'y') { ev.preventDefault(); redo(); return; }
    if (mod && ev.key.toLowerCase() === 'd') { ev.preventDefault(); duplicateSelection(); return; }
    if (mod) return;
    if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); deleteSelection(); }
    else if (ev.key === 'Tab' && (document.activeElement === canvas || document.activeElement === document.body)) {
        ev.preventDefault();
        const p = S.lastPointer;
        const r = canvas.getBoundingClientRect();
        const inside = p && p.x > r.left && p.x < r.right && p.y > r.top && p.y < r.bottom;
        showQuickAdd(inside ? p.x : r.left + r.width / 2 - 190, inside ? p.y : r.top + 60, S.sel.edge != null ? { insertEdge: S.sel.edge } : {});
    } else if (ev.key === 'f' || ev.key === 'F') fitView();
    else if (ev.key === 'Escape') { S.sel = { nodes: new Set(), edge: null }; renderAll(); }
});

window.addEventListener('resize', applyView);

// ------------------------------------------------------------------ start

async function init() {
    applyView();
    try {
        const [catalog, io] = await Promise.all([api(`${API}/filters`), api(`${API}/io-options`)]);
        S.catalog = catalog.filters;
        S.catalogByName = new Map(catalog.filters.map(f => [f.name, f]));
        S.io = io;
    } catch (e) {
        toast(`Could not read the ffmpeg filter list: ${e.message}`, true);
    }
    await loadLibrary();
    loadExamples();
    api('/api/job-config').then(cfg => {
        if (!cfg.worker_enabled) $('workerNote').textContent = 'This server runs no job worker; runs wait for a separate worker process.';
    }).catch(() => {});

    const wanted = new URLSearchParams(location.search).get('graph');
    let draft = null;
    try { draft = JSON.parse(localStorage.getItem('studio.draft') || 'null'); } catch (e) { draft = null; }
    if (draft?.doc && (!wanted || (draft.meta?.id === wanted && draft.dirty))) {
        await loadDoc(draft.doc, draft.meta || {}, { dirty: Boolean(draft.dirty) });
    } else if (wanted) {
        try {
            const g = await api(`${API}/graphs/${encodeURIComponent(wanted)}`);
            await loadDoc(g.graph, { id: g.id, name: g.name, description: g.description, tags: g.tags, revision: g.revision });
        } catch (e) {
            toast(e.message, true);
            await loadDoc(starterDoc(), {});
        }
    } else {
        await loadDoc(starterDoc(), {});
        if (!localStorage.getItem('studio.seenGuide')) {
            localStorage.setItem('studio.seenGuide', '1');
            showSideTab('examples');
        }
    }
    refreshRuns();
}

init();
})();
