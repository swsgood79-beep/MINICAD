"""Run after starting uvicorn and building frontend. Requires Playwright + Chromium."""
from pathlib import Path
from tempfile import TemporaryDirectory
import math
import os
import shutil
import ezdxf
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

def main():
    with TemporaryDirectory() as tmp, sync_playwright() as p:
        tmp = Path(tmp)
        doc = ezdxf.new('R2018'); doc.units=4
        m = doc.modelspace()
        line = m.add_line((0,0),(100,0))
        circle = m.add_circle((50,40),10)
        # Hidden in the UI but must survive export.
        m.add_spline([(0,0),(50,30),(100,0)])
        source = tmp/'smoke.dxf'; doc.saveas(source)
        original = source.read_bytes()
        browser = p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1440,'height':960},device_scale_factor=1)
        errors=[]
        edits=[]
        page.on('request',lambda request: edits.append(request.post_data_json) if '/api/edit?' in request.url else None)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_default_timeout(180000)
        static_mode=os.getenv('MINICAD_TEST_BROWSER')=='1'
        requests=[]
        page.on('request',lambda request:requests.append((request.method,request.url)))
        page.goto(os.getenv('MINICAD_TEST_URL','http://127.0.0.1:8000'))
        page.get_by_label('CAD 도면 작업 영역').evaluate("c=>c.addEventListener('pointerdown',e=>window.__lastPointer=[e.clientX,e.clientY])")
        page.locator('input[type=file]').set_input_files(source)
        page.get_by_role('status').filter(has_text='불러오기 완료').wait_for()
        canvas = page.get_by_label('CAD 도면 작업 영역')
        box = canvas.bounding_box(); w,h=box['width'],box['height']
        scale=min((w-80)/100,(h-80)/50)
        vx=w/2-50*scale; vy=h/2+25*scale
        def screen(x,y): return (box['x']+vx+x*scale,box['y']+vy-y*scale)
        def click(x,y): page.mouse.click(*screen(x,y))
        page.get_by_role('button',name='두 점 거리',exact=True).click()
        # A small pixel offset verifies endpoint and center snapping in the actual UI.
        x,y=screen(0,0); page.mouse.click(x+2,y+2)
        x,y=screen(50,40); page.mouse.click(x+2,y+2)
        assert page.get_by_test_id('measurement').inner_text()=='64.031 mm'
        # Zoom about cursor, then pan using middle button.
        anchor=screen(50,25); page.mouse.move(*anchor); page.mouse.wheel(0,240)
        f=math.exp(-240*.0015); local=(anchor[0]-box['x'],anchor[1]-box['y'])
        wx=(local[0]-vx)/scale; wy=(vy-local[1])/scale
        scale*=f; vx=local[0]-wx*scale; vy=local[1]+wy*scale
        page.wait_for_timeout(100)
        page.mouse.down(button='middle');page.mouse.move(anchor[0]+35,anchor[1]+20,steps=4);page.mouse.up(button='middle');vx+=35;vy+=20
        page.wait_for_timeout(100)
        click(0,0);click(100,0)
        assert page.get_by_test_id('measurement').inner_text()=='100.000 mm', page.get_by_test_id('measurement').inner_text()
        page.get_by_role('button',name='선택',exact=True).click();click(20,0)
        page.keyboard.down('Shift');click(60,40);page.keyboard.up('Shift')
        assert '2개 선택' in page.locator('aside').inner_text()
        page.get_by_role('button',name='객체 이동',exact=True).click();click(0,0);click(10,5)
        pointer=page.evaluate('window.__lastPointer')
        expected_dx=(pointer[0]-box['x']-vx)/scale
        expected_dy=(vy-pointer[1]+box['y'])/scale
        page.get_by_role('status').filter(has_text='수정 완료').wait_for()
        page.get_by_role('button',name='실행 취소',exact=True).click()
        page.get_by_role('status').filter(has_text='실행 취소 완료').wait_for()
        page.get_by_role('button',name='다시 실행',exact=True).click()
        page.get_by_role('status').filter(has_text='다시 실행 완료').wait_for()
        page.get_by_role('button',name='선택',exact=True).click();click(30,5)
        page.get_by_role('button',name='객체 삭제',exact=True).click()
        page.get_by_role('status').filter(has_text='수정 완료').wait_for()
        page.get_by_role('button',name='실행 취소',exact=True).click()
        page.get_by_role('status').filter(has_text='실행 취소 완료').wait_for()
        with page.expect_download() as event:
            page.get_by_role('button',name='DXF 별도 저장',exact=True).click()
        download=event.value
        assert download.suggested_filename=='smoke_edited.dxf'
        out=tmp/'export.dxf';download.save_as(out)
        saved=ezdxf.readfile(out)
        move={'dx':expected_dx,'dy':expected_dy} if static_mode else next(edit for edit in edits if edit['op']=='move')
        # Pointer coordinates have CSS-pixel resolution; export must preserve the exact submitted displacement.
        assert abs(move['dx']-10)<=1/scale and abs(move['dy']-5)<=1/scale
        assert saved.entitydb[line.dxf.handle].dxf.start.isclose((move['dx'],move['dy'],0),abs_tol=1e-9)
        assert saved.entitydb[circle.dxf.handle].dxf.center.isclose((50+move['dx'],40+move['dy'],0),abs_tol=1e-9)
        assert len(saved.modelspace().query('SPLINE'))==1
        assert source.read_bytes()==original
        page.locator('.layer input').first.uncheck()
        page.locator('.layer input').first.check()
        page.get_by_role('button',name='전체 맞춤',exact=True).click()
        assert not errors,errors
        if static_mode:
            assert all(method=='GET' and '/api/' not in url for method,url in requests),requests
            from urllib.parse import urlsplit
            expected_origin=urlsplit(os.environ['MINICAD_TEST_URL']).netloc
            assert all(urlsplit(url).netloc==expected_origin for _,url in requests),requests
            print('PASS: browser-only DXF flow made zero API calls, zero uploads, and zero third-party requests.')
        artifacts=ROOT/'test-results';artifacts.mkdir(exist_ok=True)
        page.screenshot(path=str(artifacts/'cad-smoke.png'))
        browser.close()
        print('PASS: browser import, endpoint/center snap, measurement, wheel zoom, middle pan, multi-select, move, undo/redo, delete/undo, layer toggle, DXF download/reopen and source preservation; no page errors')

if __name__=='__main__':
    main()
