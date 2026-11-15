/* Shared helpers for renaming, moving and deleting gallery items (used by the gallery and library pages).
 *
 * A rename is a `move-item` job to the item's own folder under a new name. Paths are relative to the gallery root.
 */
(function () {
    const parentOf = (path) => path.split('/').slice(0, -1).join('/');
    const baseName = (path) => path.split('/').pop();
    const validName = (name) => name !== '' && name !== '.' && name !== '..' && !/[\/\0]/.test(name);
    const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

    async function apiError(response) {
        const body = await response.json().catch(() => null);
        return typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`;
    }

    // Resolves to { jobId } once the job is queued, or { error }.
    async function postJob(endpoint, body) {
        try {
            const response = await fetch(`/api/jobs/${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!response.ok) return { error: await apiError(response) };
            return { jobId: (await response.json()).job_id };
        } catch (err) {
            return { error: err.message };
        }
    }

    const renameBody = ({ path, name }) => ({ path, dest: parentOf(path) || '.', name });

    /* Asks for the new name(s) of `items` ([{ path, isFolder }], in display order).
     * One item: prompts for its new name. Several: prompts for a pattern where {name} is the current name without
     * its extension and {n} a number; file extensions are kept.
     * `siblingNames(parent)` returns the names already used in a folder. Returns [{ path, name }] to rename,
     * or null when cancelled or invalid (after telling the user why). */
    function askRenames(items, siblingNames) {
        if (!items.length) return null;
        if (items.length === 1) {
            const { path } = items[0];
            const old = baseName(path);
            const name = prompt(`Rename "${old}" to:`, old)?.trim();
            if (!name || name === old) return null;
            if (!validName(name)) { alert('Use a single file or folder name without "/".'); return null; }
            if (siblingNames(parentOf(path)).has(name)) { alert(`"${name}" already exists in this folder.`); return null; }
            return [{ path, name }];
        }

        const pattern = prompt(
            `Rename ${plural(items.length, 'item')} using a pattern.\n` +
            '{name} = current name without extension, {n} = number (1, 2, ...). File extensions are kept.\n' +
            'Examples: holiday_{n}   or   2024_{name}',
            '{name}',
        )?.trim();
        if (!pattern || pattern === '{name}') return null;
        if (!pattern.includes('{n}') && !pattern.includes('{name}')) {
            alert('The pattern must contain {n} or {name}, or every item would get the same name.');
            return null;
        }
        const width = String(items.length).length;
        const renames = [];
        const taken = new Map();  // parent -> names in use there
        for (const [i, { path, isFolder }] of items.entries()) {
            const old = baseName(path);
            const dot = isFolder ? -1 : old.lastIndexOf('.');
            const stem = dot > 0 ? old.slice(0, dot) : old;
            const ext = dot > 0 ? old.slice(dot) : '';
            const name = pattern.replaceAll('{name}', stem).replaceAll('{n}', String(i + 1).padStart(width, '0')) + ext;
            if (name === old) continue;
            const parent = parentOf(path);
            if (!taken.has(parent)) taken.set(parent, new Set(siblingNames(parent)));
            if (!validName(name)) { alert(`Nothing was renamed: "${name}" is not a valid name.`); return null; }
            if (taken.get(parent).has(name)) {
                alert(`Nothing was renamed: "${name}" would already exist in ${parent || 'the gallery root'}.`);
                return null;
            }
            taken.get(parent).add(name);
            renames.push({ path, name });
        }
        return renames.length ? renames : null;
    }

    window.ItemOps = { parentOf, baseName, validName, plural, apiError, postJob, renameBody, askRenames };
})();
