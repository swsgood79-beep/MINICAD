"""Synthetic 120,001-object decoded scene in the real static app, not a customer DWG test."""
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL=os.getenv('MINICAD_TEST_URL','http://127.0.0.1:8081/MINICAD/')

def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':960})
        page.set_default_timeout(180000)
        errors=[];requests=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:requests.append((request.method,request.url)))
        def decoded_scene(route):
            response=route.fetch()
            shim="""
const send=globalThis.postMessage.bind(globalThis);
globalThis.postMessage=(message,transfer)=>{
 if(typeof message.databaseJSON==='string'){
   const db=JSON.parse(message.databaseJSON);
   const line=db.entities.find(e=>e.type==='LINE'&&e.startPoint.y===e.endPoint.y);
   db.entities=Array.from({length:120001},()=>line);
   db.tables.BLOCK_RECORD={entries:[]};
   message.databaseJSON=JSON.stringify(db);
 }
 send(message,transfer);
};
Object.defineProperty(globalThis,'onmessage',{configurable:true,set(handler){globalThis.addEventListener('message',event=>{if(event.data.mode==='dxf')send({code:'WASM_TRAP',error:'memory access out of bounds'});else handler(event);});}});
"""
            route.fulfill(response=response,body=shim+response.text())
        page.route('**/assets/dwg-reader.worker-*.js',decoded_scene)
        page.goto(URL)
        page.locator('input[type=file]').set_input_files({'name':'large-synthetic.dwg','mimeType':'application/octet-stream','buffer':(ROOT/'tests/fixtures/sample_2018.dwg').read_bytes()})
        page.get_by_role('status').filter(has_text='불러오기 완료').wait_for()
        assert page.locator('.preview-banner').is_visible()
        aside=page.locator('aside').inner_text()
        assert '120001개 객체' in aside and '표시 30000개' in aside,aside
        for name in ('선 추가','원 추가','객체 복사'):
            assert page.get_by_role('button',name=name,exact=True).is_disabled()
        # The known 100 mm line is still measured analytically within the partial view.
        box=page.get_by_label('CAD 도면 작업 영역').bounding_box()
        x0=99.6812627452187;y=94.69575912391304
        scale=min((box['width']-80)/100,box['height']-80)
        vx=box['width']/2-(x0+50)*scale;vy=box['height']/2+y*scale
        page.get_by_role('button',name='두 점 거리',exact=True).click()
        page.mouse.click(box['x']+vx+x0*scale,box['y']+vy-y*scale)
        page.mouse.click(box['x']+vx+(x0+100)*scale,box['y']+vy-y*scale)
        assert page.get_by_test_id('measurement').inner_text()=='100.000 mm'
        dialogs=[]
        page.once('dialog',lambda dialog:(dialogs.append(dialog.message),dialog.dismiss()))
        page.get_by_role('button',name='인쇄 / PDF').click()
        assert dialogs and '전체 도면 인쇄가 아닙니다' in dialogs[-1]
        assert page.locator('iframe[data-minicad-print]').count()==0
        page.once('dialog',lambda dialog:dialog.accept())
        page.get_by_role('button',name='인쇄 / PDF').click()
        frame=page.frame_locator('iframe[data-minicad-print]')
        assert '부분 미리보기' in frame.locator('body').inner_text()
        assert frame.locator('polyline').count()==30000
        assert not errors,errors
        origin=urlsplit(URL).netloc
        assert all(method=='GET' and '/api/' not in url and urlsplit(url).netloc==origin for method,url in requests)
        page.screenshot(path=str(ROOT/'test-results/large-preview.png'))
        browser.close()
        print('PASS: synthetic 120001-object DWG scene opens 30000-element preview instead of failing; 100 mm measurement, persistent partial notice, blocked creation/copy, print confirmation and partial print warnings; no uploads/API/external requests.')
if __name__=='__main__':main()
