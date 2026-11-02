"""Test the actual patched Windows frontend in Chromium with a controlled API fixture."""
import contextlib
import functools
import http.server
import json
from pathlib import Path
import threading
import sys
from playwright.sync_api import sync_playwright

root = Path(sys.argv[1]).resolve()
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(root)))
threading.Thread(target=server.serve_forever, daemon=True).start()
entities = [
    dict(id='first', type='TEXT', layer='0', c=[10,20], height=3, text='회의실 OFFICE'),
    dict(id='block', type='INSERT', layer='0', segments=[dict(id='child', type='MTEXT', layer='0', c=[900,800], height=5, text='회의실 2')]),
    dict(id='hidden', type='TEXT', layer='숨김', c=[2000,2000], height=3, text='회의실 숨김'),
    dict(id='line', type='LINE', layer='0', a=[0,0], b=[100,0]),
]
drawing = dict(document_id='test', filename='search-fixture.dxf', entities=entities,
               layers=[dict(name='0', visible=True, locked=False),dict(name='숨김',visible=False,locked=False)],
               units=4,total=len(entities),unsupported={},warnings=[],revision=0,can_undo=False,can_redo=False,edit_ready=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport=dict(width=1440,height=1000))
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    def api(route):
        url=route.request.url
        if '/api/open-progress/' in url: payload=dict(percent=90,stage='fixture')
        elif '/api/open' in url: payload=drawing
        elif '/api/status' in url: payload=dict(dwg_installed=True)
        elif '/api/cache' in url: payload=dict(entries=0,bytes=0)
        else: payload={}
        route.fulfill(status=200,content_type='application/json',body=json.dumps(payload))
    page.route('**/api/**', api)
    page.goto(f'http://127.0.0.1:{server.server_port}/')
    page.locator('input[type=file]').set_input_files(dict(name='search-fixture.dxf',mimeType='application/dxf',buffer=b'fixture'))
    page.get_by_text('search-fixture.dxf', exact=True).wait_for()
    canvas=page.get_by_label('CAD 도면 작업 영역')
    page.wait_for_function("document.querySelector('canvas').dataset.view !== undefined")
    before=json.loads(canvas.get_attribute('data-view'))
    page.keyboard.press('Control+f')
    field=page.get_by_role('searchbox',name='검색할 단어')
    field.wait_for(state='visible')
    assert field.evaluate('(e)=>document.activeElement===e')
    field.fill('회의실')
    panel=page.get_by_role('search',name='도면 문자 검색')
    page.wait_for_function("document.querySelector('.minicad-text-search [role=status]').textContent==='1 / 2'")
    page.wait_for_timeout(150)
    first=json.loads(canvas.get_attribute('data-view'))
    assert first != before
    field.press('Enter'); page.wait_for_timeout(150)
    assert panel.get_by_role('status').inner_text()=='2 / 2'
    second=json.loads(canvas.get_attribute('data-view'))
    assert first != second
    field.press('Enter'); page.wait_for_timeout(100)
    assert panel.get_by_role('status').inner_text()=='1 / 2'
    field.press('Shift+Enter')
    assert panel.get_by_role('status').inner_text()=='2 / 2'
    field.fill('office')
    assert panel.get_by_role('status').inner_text()=='1 / 1'
    field.fill('없는단어')
    assert panel.get_by_role('status').inner_text()=='검색 결과 없음'
    assert panel.get_by_role('button',name='다음 검색 결과').is_disabled()
    field.fill('  ')
    assert panel.get_by_role('status').inner_text()=='단어를 입력하세요'
    field.fill('회의실')
    field.press('Escape')
    assert not panel.is_visible()
    page.keyboard.press('Control+f')
    assert field.evaluate('(e)=>document.activeElement===e && e.selectionEnd===e.value.length')
    panel.get_by_role('button',name='검색 닫기').click()
    assert not panel.is_visible()
    # Original Windows-specific features remain present in the actual baseline UI.
    for text in ['평행 복사 (OFFSET)', '성능 우선', '미세 문자 모두 표시', '인쇄 설정']:
        assert page.get_by_text(text,exact=True).count() > 0, text
    page.get_by_role('button',name='평행 복사 (OFFSET)',exact=True).click()
    page.keyboard.press('Escape')
    # Pure search behavior: Unicode normalization, CAD escapes, hidden objects.
    result=page.evaluate('''async () => {
      const {findDrawingText}=await import('/assets/drawing-search-v0313.js');
      const e=[{id:'a',c:[0,0],text:'\\\\U+AC00'}, {id:'b',c:[0,0],text:'가',visible:false}];
      return findDrawingText(e,'가').map(x=>x.ownerId);
    }''')
    assert result==['a'],result
    assert not errors, errors
    page.screenshot(path='/workspace/releases/MiniCAD-v0.3.13-validation.png')
    browser.close()
server.shutdown()
print('PASS: actual v0.3.13 frontend, Ctrl+F focus, Korean/English, nested blocks, hidden layers, camera movement, next/previous/wrap, empty/no match, close/reopen, Unicode, existing Windows controls; no JS errors.')
