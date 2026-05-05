window.attachTerminal = async function(responseText) {
  let body;
  try { body = JSON.parse(responseText); } catch (e) { return; }
  const sessionId = body.session_id;
  if (!sessionId) return;

  const el = document.getElementById('terminal');
  if (!el) return;
  // Safe clear: remove children rather than overwriting innerHTML.
  while (el.firstChild) el.removeChild(el.firstChild);
  const term = new Terminal({
    fontFamily: 'monospace', fontSize: 13, theme: { background: '#000' },
    convertEol: true,
  });
  term.open(el);

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/sessions/ws/${sessionId}`);
  ws.onmessage = (ev) => term.write(ev.data);
  ws.onclose = () => term.write('\r\n[disconnected]\r\n');

  window._activeSession = { ws, term, sessionId };
};

window.sendMsg = function() {
  const ta = document.getElementById('msg-input');
  const sess = window._activeSession;
  if (!ta || !sess || sess.ws.readyState !== 1) return;
  let text = ta.value;
  if (!text.endsWith('\n')) text += '\n';
  sess.ws.send(text);
  ta.value = '';
};

document.addEventListener('paste', async (e) => {
  const sess = window._activeSession;
  if (!sess) return;
  const items = e.clipboardData?.items || [];
  for (const item of items) {
    if (item.type?.startsWith('image/')) {
      e.preventDefault();
      const blob = item.getAsFile();
      if (!blob) continue;
      const fd = new FormData();
      fd.append('file', blob, 'paste.png');
      const r = await fetch(`/sessions/${sess.sessionId}/upload-image`, { method: 'POST', body: fd });
      if (r.ok) {
        const { path } = await r.json();
        const ta = document.getElementById('msg-input');
        if (ta) ta.value += `@${path} `;
      }
      break;
    }
  }
});

document.addEventListener('keydown', (e) => {
  if (e.target?.id === 'msg-input' && e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    window.sendMsg();
  }
});
