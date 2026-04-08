const J = (r) => r.ok ? r.json() : r.text().then(t => Promise.reject(new Error(t)));

export const api = {
  templates: () => fetch('/api/templates').then(J),
  senders:   () => fetch('/api/senders').then(J),
  drafts:    () => fetch('/api/drafts').then(J),
  draft:     (id) => fetch(`/api/drafts/${id}`).then(J),
  saveDraft: (d) => fetch('/api/drafts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }).then(J),
  deleteDraft: (id) => fetch(`/api/drafts/${id}`, { method: 'DELETE' }).then(J),
  renameDraft: (id, name) => fetch(`/api/drafts/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }).then(J),
  render: (template, data) => fetch('/api/render', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template, data }),
  }).then(r => r.text()),
  exportHtml: (template, data) => fetch('/api/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template, data }),
  }).then(r => r.blob()),
  uploadImage: (file) => {
    const fd = new FormData(); fd.append('file', file);
    return fetch('/api/upload-image', { method: 'POST', body: fd }).then(J);
  },
  parseRecipients: (file) => {
    const fd = new FormData(); fd.append('file', file);
    return fetch('/api/parse-recipients', { method: 'POST', body: fd }).then(J);
  },
  send: (payload) => fetch('/api/send', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(J),
  manual: () => fetch('/api/manual').then(J),
};
