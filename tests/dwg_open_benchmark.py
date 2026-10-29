"""Measure complete static-app opening; never copy, upload or publish the drawing.

Usage: python tests/dwg_open_benchmark.py drawing.dwg --url http://localhost:8081/MINICAD/
The second run retains the initialized engine, but closes the previous document.
No wall-time assertion: CPU speed, browser, downloads and cache affect the result.
"""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:8081/MINICAD/')
    args=parser.parse_args()
    source=args.file.resolve()
    original=hashlib.sha256(source.read_bytes()).digest()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1852,'height':1000})
        page.set_default_timeout(240000)
        errors=[];requests=[];results=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append((r.method,r.url)))
        page.goto(args.url)
        for run in range(2):
            started=time.perf_counter()
            page.locator('input[type=file]').set_input_files(source)
            page.wait_for_function("document.querySelector('footer [role=status]').textContent.includes('불러오기 완료') || !!document.querySelector('[role=alert]')")
            assert page.get_by_role('alert').count()==0,'Drawing failed to open'
            page.wait_for_function("Number(document.querySelector('canvas').dataset.sceneElements)>0")
            result={'run':run+1,'seconds':round(time.perf_counter()-started,3),
                    'elements':int(page.locator('canvas').get_attribute('data-scene-elements')),
                    'partialPreview':page.locator('.preview-banner').count()>0}
            results.append(result)
            print(json.dumps(result),flush=True)
            page.get_by_role('button',name='도면 닫기',exact=True).click()
            page.get_by_role('status').filter(has_text='도면을 닫았습니다').wait_for()
        assert results[0]['elements']==results[1]['elements']
        assert not errors,errors
        origin=urlsplit(args.url).netloc
        assert all(method=='GET' and '/api/' not in url and urlsplit(url).netloc==origin for method,url in requests),'Unexpected upload/API/external request'
        assert hashlib.sha256(source.read_bytes()).digest()==original
        browser.close()
        print('PASS: same scene in both runs; original preserved; zero uploads/API/external requests.')

if __name__=='__main__':main()
