/* Shared folder picker dialog.
 *
 *   FolderPicker.open({
 *     scope: 'gallery' | 'source',      // which allowed roots to browse
 *     title: 'Choose a folder',
 *     start: '/abs/path',               // optional starting folder
 *     startRel: 'path/in/gallery',      // optional, relative to the gallery root (scope 'gallery')
 *     display: 'rel' | 'path',          // how the selection is shown (default: rel for gallery, path for source)
 *     note: (listing) => 'extra text',  // optional text appended to the selection line
 *     onChoose: (listing) => {},        // receives the /api/fs/dirs listing of the chosen folder
 *   });
 */
(function () {
    const CSS = `
    .fp-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; font-family: inherit; }
    .fp-hidden { display: none !important; }
    .fp-box { background: #161616; color: #fff; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; width: min(760px, 94vw); height: min(620px, 88vh); display: flex; flex-direction: column; font-size: 14px; }
    .fp-box button, .fp-box select { font: inherit; color: inherit; background: #202020; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 0.4rem 0.7rem; cursor: pointer; }
    .fp-box button:disabled { opacity: 0.4; cursor: default; }
    .fp-box button.fp-primary { background: #6366f1; border-color: #6366f1; }
    .fp-head, .fp-foot { padding: 0.75rem 1rem; display: flex; gap: 0.6rem; align-items: center; }
    .fp-head { border-bottom: 1px solid rgba(255,255,255,0.1); }
    .fp-foot { border-top: 1px solid rgba(255,255,255,0.1); }
    .fp-title { font-weight: 600; flex: 1; }
    .fp-crumbs { padding: 0.5rem 1rem; font-size: 0.85rem; color: #a3a3a3; display: flex; flex-wrap: wrap; gap: 0.2rem; border-bottom: 1px solid rgba(255,255,255,0.1); }
    .fp-crumbs a { color: #fff; text-decoration: none; cursor: pointer; }
    .fp-crumbs a:hover { text-decoration: underline; }
    .fp-list { flex: 1; overflow: auto; }
    .fp-row { display: flex; align-items: center; gap: 0.6rem; padding: 0.35rem 1rem; cursor: pointer; font-size: 0.9rem; }
    .fp-row:nth-child(even) { background: #1b1b1b; }
    .fp-row:hover { background: #2a2a40; }
    .fp-row .fp-ico { color: #5aa9f6; width: 1.1rem; text-align: center; }
    .fp-row .fp-nm { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .fp-row .fp-meta { color: #a3a3a3; font-size: 0.78rem; white-space: nowrap; }
    .fp-row.fp-dot .fp-nm { color: #a3a3a3; }
    .fp-row.fp-locked .fp-ico { color: #f59e0b; }
    .fp-sel { flex: 1; font-size: 0.82rem; color: #a3a3a3; overflow-wrap: anywhere; }
    `;

    const state = { opts: null, listing: null, dom: null };

    const el = (tag, attrs = {}, ...kids) => {
        const n = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs)) {
            if (k === 'class') n.className = v;
            else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
            else n.setAttribute(k, v);
        }
        for (const c of kids) if (c != null) n.append(c instanceof Node ? c : String(c));
        return n;
    };

    function errorText(body, fallback) {
        if (!body || body.detail == null) return fallback;
        return typeof body.detail === 'string' ? body.detail : fallback;
    }

    function build() {
        if (state.dom) return state.dom;
        document.head.append(el('style', {}, CSS));
        const d = {
            title: el('span', { class: 'fp-title' }),
            root: el('select', { onchange: () => go(d.root.value) }),
            crumbs: el('div', { class: 'fp-crumbs' }),
            list: el('div', { class: 'fp-list' }),
            sel: el('span', { class: 'fp-sel' }),
            up: el('button', { type: 'button', onclick: () => state.listing?.parent && go(state.listing.parent) },
                el('i', { class: 'fas fa-arrow-up' }), ' Up'),
            choose: el('button', { type: 'button', class: 'fp-primary', onclick: choose }, 'Choose this folder'),
        };
        d.modal = el('div', { class: 'fp-modal fp-hidden', role: 'dialog', 'aria-modal': 'true', onclick: (e) => { if (e.target === d.modal) close(); } },
            el('div', { class: 'fp-box' },
                el('div', { class: 'fp-head' }, d.title, d.root,
                    el('button', { type: 'button', title: 'Close', onclick: close }, el('i', { class: 'fas fa-xmark' }))),
                d.crumbs, d.list,
                el('div', { class: 'fp-foot' }, d.sel, d.up, el('button', { type: 'button', onclick: close }, 'Cancel'), d.choose)));
        document.body.append(d.modal);
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !d.modal.classList.contains('fp-hidden')) close(); });
        state.dom = d;
        return d;
    }

    function close() { state.dom?.modal.classList.add('fp-hidden'); }

    function choose() {
        if (!state.listing || !state.opts) return;
        const cb = state.opts.onChoose;
        const listing = state.listing;
        close();
        cb?.(listing);
    }

    async function loadRoots() {
        const res = await fetch('/api/fs/roots');
        return res.ok ? await res.json() : [];
    }

    async function go(path) {
        const d = build();
        const params = new URLSearchParams({ scope: state.opts.scope });
        if (path) params.set('path', path);
        const res = await fetch(`/api/fs/dirs?${params}`);
        const data = await res.json().catch(() => null);
        if (!res.ok) {
            d.sel.textContent = errorText(data, `HTTP ${res.status}`);
            return false;
        }
        state.listing = data;
        render();
        return true;
    }

    function dirMeta(x) {
        const files = x.readable ? `${x.num_files.toLocaleString()}${x.more_files ? '+' : ''} files` : 'no access';
        const link = x.is_symlink ? `\u2192 ${x.link_target} \u00b7 ` : '';
        return link + (x.writable ? files : `${files} \u00b7 read-only (owner: ${x.owner})`);
    }

    function render() {
        const d = state.dom, L = state.listing, o = state.opts;
        d.root.value = L.root;
        const crumbs = [el('a', { onclick: () => go(L.root) }, L.root)];
        const rest = L.path.slice(L.root.length).split('/').filter(Boolean);
        rest.forEach((part, i) => {
            const target = L.root.replace(/\/$/, '') + '/' + rest.slice(0, i + 1).join('/');
            crumbs.push(' / ', el('a', { onclick: () => go(target) }, part));
        });
        d.crumbs.replaceChildren(...crumbs);
        const rows = L.dirs.map(x => el('div', {
            class: `fp-row${x.name.startsWith('.') ? ' fp-dot' : ''}${x.writable ? '' : ' fp-locked'}`,
            title: x.path, onclick: () => x.readable && go(x.path),
        }, el('i', { class: `fas ${x.is_symlink ? 'fa-link' : x.writable ? 'fa-folder' : 'fa-folder-closed'} fp-ico` }),
           el('span', { class: 'fp-nm' }, x.name),
           el('span', { class: 'fp-meta' }, dirMeta(x)),
           x.has_subdirs ? el('i', { class: 'fas fa-chevron-right fp-meta' }) : null));
        d.list.replaceChildren(...(rows.length ? rows
            : [el('div', { class: 'fp-row fp-meta' }, `No subfolders \u00b7 ${L.num_files.toLocaleString()} files here`)]));
        d.up.disabled = !L.parent;
        const showPath = (o.display || (o.scope === 'source' ? 'path' : 'rel')) === 'path';
        let note = `Selected: ${showPath ? L.path : (L.rel || '.')}`;
        if (!L.writable) note += o.scope === 'source'
            ? ` \u00b7 \u26a0 the server can't delete files here (owner: ${L.owner}); the move would be refused`
            : ` \u00b7 \u26a0 read-only for the server (owner: ${L.owner})`;
        const extra = o.note?.(L);
        if (extra) note += ` \u00b7 ${extra}`;
        d.sel.textContent = note;
    }

    async function open(opts) {
        state.opts = { scope: 'gallery', title: 'Choose a folder', ...opts };
        const roots = (await loadRoots()).filter(r => r.scope === state.opts.scope).map(r => r.path);
        if (!roots.length) { alert('No folders are available here. For move sources, set SITE_COPY_SOURCE_ROOTS on the server.'); return; }
        const d = build();
        d.title.textContent = state.opts.title;
        d.root.replaceChildren(...roots.map(r => el('option', { value: r }, r)));
        d.root.classList.toggle('fp-hidden', roots.length < 2);
        d.modal.classList.remove('fp-hidden');
        let start = state.opts.start || null;
        if (!start && state.opts.startRel !== undefined && state.opts.scope === 'gallery') {
            const rel = (state.opts.startRel || '').replace(/^\.?\/+/, '');
            start = rel && rel !== '.' ? `${roots[0]}/${rel}` : roots[0];
        }
        if (!(await go(start))) await go(roots[0]);
    }

    window.FolderPicker = { open, close };
})();
