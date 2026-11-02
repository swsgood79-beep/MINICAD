// Additive UI extension for the verified Windows v0.3.12 frontend.
// Original rendering, editing, measurements, printing and backend stay intact.
export function findDrawingText(entities, query) {
  const needle = normalize(query.trim());
  if (!needle) return [];
  const matches = [];
  function visit(entity, ownerId) {
    if (entity.visible === false) return;
    if (entity.text && entity.c && normalize(entity.text).includes(needle))
      matches.push({ entity, ownerId });
    for (const child of entity.segments || []) visit(child, ownerId);
  }
  for (const entity of entities) visit(entity, entity.id);
  return matches;
}
function normalize(text) {
  return text.replace(/\\U\+([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
    .normalize('NFC').toLocaleLowerCase();
}

export function useDrawingSearch(React, state) {
  const latest = React.useRef(state);
  latest.current = state;
  const controller = React.useRef(null);
  React.useEffect(() => {
    const panel = document.createElement('section');
    panel.className = 'minicad-text-search';
    panel.setAttribute('role', 'search');
    panel.setAttribute('aria-label', '도면 문자 검색');
    panel.hidden = true;
    panel.innerHTML = '<label>단어 찾기 <input type="search" aria-label="검색할 단어" placeholder="도면에서 단어 찾기" autocomplete="off"></label>' +
      '<span role="status" aria-live="polite"></span>' +
      '<button type="button" aria-label="이전 검색 결과" title="이전 결과 (Shift+Enter)">↑</button>' +
      '<button type="button" aria-label="다음 검색 결과" title="다음 결과 (Enter)">↓</button>' +
      '<button type="button" aria-label="검색 닫기" title="닫기 (Esc)">×</button>' +
      '<small>Enter: 다음 · Shift+Enter: 이전 · Esc: 닫기 · 표시 중인 문자 검색</small>';
    document.body.append(panel);
    const input = panel.querySelector('input');
    const status = panel.querySelector('[role="status"]');
    const [prev, next, closeButton] = panel.querySelectorAll('button');
    let matches = [], index = 0, previousFocus = null;
    function showMatch() {
      const match = matches[index];
      const ready = !!match && !latest.current.busy;
      prev.disabled = next.disabled = !ready;
      status.textContent = !input.value.trim() ? '단어를 입력하세요' :
        !matches.length ? '검색 결과 없음' : `${index + 1} / ${matches.length}`;
      if (ready && !panel.hidden) latest.current.navigate(match);
    }
    function refresh() {
      matches = findDrawingText(latest.current.entities, input.value);
      index = 0;
      showMatch();
    }
    function step(direction) {
      if (!matches.length || latest.current.busy) return;
      index = (index + direction + matches.length) % matches.length;
      showMatch();
    }
    function close() {
      panel.hidden = true;
      if (previousFocus?.isConnected) previousFocus.focus();
    }
    function key(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (panel.hidden) previousFocus = document.activeElement;
        panel.hidden = false;
        input.focus(); input.select();
        refresh();
      } else if (!panel.hidden && event.key === 'Escape') {
        event.preventDefault(); event.stopImmediatePropagation(); close();
      }
    }
    input.addEventListener('input', event => { if (!event.isComposing) refresh(); });
    input.addEventListener('compositionend', refresh);
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault(); event.stopPropagation();
        if (!event.isComposing && event.keyCode !== 229) step(event.shiftKey ? -1 : 1);
      }
    });
    // Keep drawing shortcuts and pointer actions from consuming search controls.
    panel.addEventListener('pointerdown', event => event.stopPropagation());
    prev.addEventListener('click', () => step(-1));
    next.addEventListener('click', () => step(1));
    closeButton.addEventListener('click', close);
    window.addEventListener('keydown', key, true);
    controller.current = { refresh };
    return () => { window.removeEventListener('keydown', key, true); panel.remove(); controller.current = null; };
  }, []);
  React.useEffect(() => { controller.current?.refresh(); }, [state.entities, state.busy]);
}
