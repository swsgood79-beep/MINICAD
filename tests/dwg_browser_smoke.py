"""Actual DWG files in the static browser app. No upload/conversion server."""
from pathlib import Path
import hashlib
import json
import os
import re
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
EXPECTED=json.loads((ROOT/'tests/fixtures/sample_expected.json').read_text())
URL=os.getenv('MINICAD_TEST_URL','http://127.0.0.1:8081/MINICAD/')

def bounds(entities):
    points=[]
    for e in entities:
        if 'segments' in e:points.extend(bounds(e['segments']))
        elif e['type']=='LINE':points.extend((e['a'],e['b']))
        elif e['type'] in ('CIRCLE','ARC'):
            x,y=e['c'];r=e['r'];points.extend(([x-r,y-r],[x+r,y+r]))
        elif 'c' in e:points.append(e['c'])
    return points

def main():
    with sync_playwright() as p:
        import shutil
        browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        for name in ('sample_2000.dwg','sample_2018.dwg'):
            page=browser.new_page(viewport={'width':1600,'height':1000})
            page.set_default_timeout(180000)
            errors=[];requests=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:requests.append((r.method,r.url)))
            if os.getenv('MINICAD_TEST_DWG_FALLBACK')=='1':
                def force_writer_trap(route):
                    response=route.fetch()
                    shim="""Object.defineProperty(globalThis,'onmessage',{configurable:true,set(handler){globalThis.addEventListener('message',event=>{if(event.data.mode==='dxf'){globalThis.postMessage({code:'WASM_TRAP',error:'memory access out of bounds'});}else handler(event);});}});
"""
                    route.fulfill(response=response,body=shim+response.text())
                page.route('**/assets/dwg-reader.worker-*.js',force_writer_trap)
            page.goto(URL)
            source=ROOT/'tests/fixtures'/name
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            page.locator('input[type=file]').set_input_files(source)
            page.get_by_role('status').filter(has_text='불러오기 완료').wait_for()
            print('Opened',name,flush=True)
            page.set_default_timeout(15000)
            assert '6개 객체' in page.locator('aside').inner_text(),page.locator('aside').inner_text()
            assert page.get_by_role('button',name='DXF 별도 저장').is_disabled()
            assert '현재 화면에만 적용' in page.locator('aside').inner_text()
            box=page.get_by_label('CAD 도면 작업 영역').bounding_box()
            ps=bounds(EXPECTED['entities']);xs=[q[0] for q in ps];ys=[q[1] for q in ps]
            scale=min((box['width']-80)/max(1,max(xs)-min(xs)),(box['height']-80)/max(1,max(ys)-min(ys)))
            vx=box['width']/2-(min(xs)+max(xs))/2*scale
            vy=box['height']/2+(min(ys)+max(ys))/2*scale
            def click(x,y):page.mouse.click(box['x']+vx+x*scale,box['y']+vy-y*scale)
            x,y=99.6812627452187,94.69575912391304
            page.get_by_role('button',name='두 점 거리',exact=True).click();click(x,y);click(x+100,y)
            assert page.get_by_test_id('measurement').inner_text()=='100.000 mm',page.get_by_test_id('measurement').inner_text()
            page.get_by_role('button',name='반지름·직경',exact=True).click();click(219.6812627452187,24.69575912391304)
            assert page.get_by_test_id('measurement').inner_text()=='R 20.000 · Ø 40.000 mm'
            print('Measurements passed',name,flush=True)
            page.get_by_role('button',name='선택',exact=True).click();click(x+30,y)
            assert 'LINE' in page.locator('aside').inner_text()
            page.get_by_role('button',name='객체 이동',exact=True).click();click(x,y);click(x+10,y+10)
            page.get_by_role('status').filter(has_text='수정 완료').wait_for()
            print('Moved',name,flush=True)
            page.get_by_role('button',name='실행 취소',exact=True).click()
            page.get_by_role('status').filter(has_text='실행 취소 완료').wait_for()
            page.get_by_role('button',name='다시 실행',exact=True).click()
            page.get_by_role('status').filter(has_text='다시 실행 완료').wait_for()
            print('Printing',name,flush=True)
            page.get_by_role('button',name='인쇄 / PDF').click()
            frame=page.frame_locator('iframe[data-minicad-print]')
            assert frame.locator('svg').get_attribute('viewBox')=='0 0 1100 700'
            assert frame.locator('circle').count()>=1
            assert frame.locator('canvas,button,nav').count()==0
            text=frame.locator('body').inner_text()
            assert name in text and 'R 20.000' in text and '실제 축척' in text
            assert ('DWG 대체 읽기' if os.getenv('MINICAD_TEST_DWG_FALLBACK')=='1' else 'DWG 시험 읽기') in text
            # Verify the exact vector print document also produces a real PDF.
            printable=frame.locator('html').inner_html()
            pdf_page=browser.new_page()
            pdf_page.set_content('<!doctype html><html>'+printable+'</html>')
            output=ROOT/'test-results';output.mkdir(exist_ok=True)
            pdf=pdf_page.pdf(path=str(output/(name+'.pdf')),prefer_css_page_size=True)
            assert pdf.startswith(b'%PDF') and len(pdf)>2000
            assert len(re.findall(rb'/Type /Page\b',pdf))==1, 'Print must fit one A4 landscape page'
            pdf_page.close()
            print('PDF passed',name,flush=True)
            # A second, hidden-layer print must omit the circle on Tavolo 1.
            page.locator('label.layer').filter(has_text='Tavolo 1').locator('input').uncheck()
            print('Printing',name,flush=True)
            page.get_by_role('button',name='인쇄 / PDF').click()
            assert page.frame_locator('iframe[data-minicad-print]').locator('circle').count()==0
            # A failed import must leave the current document usable.
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('input[type=file]').set_input_files({'name':'broken.dwg','mimeType':'application/octet-stream','buffer':b'not a DWG'})
            page.get_by_role('status').filter(has_text='DWG 열기 실패').wait_for()
            assert name in page.locator('.filename').inner_text()
            assert page.get_by_role('alert').is_visible()
            assert 'broken.dwg' in page.get_by_role('alert').inner_text()
            assert hashlib.sha256(source.read_bytes()).hexdigest()==before
            assert not errors,errors
            origin=urlsplit(URL).netloc
            assert all(method=='GET' and '/api/' not in url and urlsplit(url).netloc==origin for method,url in requests),requests
            page.screenshot(path=str(output/(name+'.png')))
            page.close()
            print('PASS:',name,'100 mm distance, R20/diameter40, move/undo/redo, DWG save blocked, vector print/PDF, hidden layers, bad-file recovery, original preserved; no uploads/API/external requests')
        browser.close()

if __name__=='__main__':main()
