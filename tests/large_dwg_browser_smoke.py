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
 if(message.databaseBytes instanceof Uint8Array){
   const db=JSON.parse(new TextDecoder().decode(message.databaseBytes));
   const line=db.entities.find(e=>e.type==='LINE'&&e.startPoint.y===e.endPoint.y);
   db.entities=Array.from({length:120001},()=>line);
   db.entities[120000]={...line,startPoint:{x:50000,y:10000,z:0},endPoint:{x:50100,y:10000,z:0}};
   db.tables.BLOCK_RECORD={entries:[]};
   message.databaseBytes=new TextEncoder().encode(JSON.stringify(db));
   transfer=[message.databaseBytes.buffer];
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
        assert page.locator('.preview-banner').count()==0
        aside=page.locator('aside').inner_text()
        assert '120001개 객체' in aside and '표시 120001개' in aside,aside
        canvas=page.get_by_label('CAD 도면 작업 영역')
        assert int(canvas.get_attribute('data-scene-elements'))==120001
        import json,math
        scene=json.loads(canvas.get_attribute('data-scene-bounds'))
        assert scene[2]==50100 and scene[3]==10000,scene
        for name in ('선 추가','원 추가','객체 복사'):
            assert page.get_by_role('button',name=name,exact=True).is_enabled()
        # Zoom on the final object, proving that full-fit/tiles retain the tail.
        box=canvas.bounding_box()
        scale=min((box['width']-80)/(scene[2]-scene[0]),(box['height']-80)/(scene[3]-scene[1]))
        vx=box['width']/2-(scene[0]+scene[2])/2*scale;vy=box['height']/2+(scene[1]+scene[3])/2*scale
        anchor=(box['x']+vx+50050*scale,box['y']+vy-10000*scale)
        page.mouse.move(*anchor);page.mouse.down(button='middle')
        center=(box['x']+box['width']/2,box['y']+box['height']/2)
        page.mouse.move(*center,steps=4);page.mouse.up(button='middle')
        page.wait_for_timeout(150)
        remaining=-math.log(4/scale)/.0015
        while abs(remaining)>0.01:
            delta=max(-900,min(900,remaining))
            page.mouse.wheel(0,delta);page.wait_for_timeout(120)
            remaining-=delta
        page.wait_for_timeout(300)
        assert 0<int(canvas.get_attribute('data-visible-tiles'))<int(canvas.get_attribute('data-scene-tiles'))
        page.get_by_role('button',name='두 점 거리',exact=True).click()
        page.mouse.click(center[0]-200,center[1]);page.mouse.click(center[0]+200,center[1])
        assert page.get_by_test_id('measurement').inner_text()=='100.000 mm', (page.get_by_test_id('measurement').inner_text(),box,scene,scale,center)
        page.get_by_role('button',name='인쇄 / PDF').click()
        frame=page.frame_locator('iframe[data-minicad-print]')
        assert '부분 미리보기' not in frame.locator('body').inner_text()
        counts=frame.locator('svg').evaluate("s=>({moves:[...s.querySelectorAll('path')].reduce((n,p)=>n+(p.getAttribute('d').match(/M /g)||[]).length,0),nodes:s.querySelectorAll('*').length})")
        assert counts['moves']==120001 and counts['nodes']<100,counts
        assert not errors,errors
        origin=urlsplit(URL).netloc
        assert all(method=='GET' and '/api/' not in url and urlsplit(url).netloc==origin for method,url in requests)
        page.screenshot(path=str(ROOT/'test-results/large-preview.png'))
        browser.close()
        print('PASS: synthetic 120001-object DWG retained in full; final faraway object included in fit, zoom/culling, 100 mm snap measurement, complete batched vector print; no uploads/API/external requests.')
if __name__=='__main__':main()
