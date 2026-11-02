"""Reproducible additive patch of the verified user-supplied Windows package."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

BASE_SHA256 = 'ebc0142672826f4f9e5a7e21f348e07518f20143f4ae320276276555e15ae88a'
BASE_JS = '_internal/frontend/dist/assets/index-DJISSrak.js'
ASSETS = '_internal/frontend/dist/assets/'
ROOT = Path(__file__).resolve().parent

def build(source, destination):
    assert hashlib.sha256(source.read_bytes()).hexdigest() == BASE_SHA256, 'Unexpected baseline ZIP'
    with zipfile.ZipFile(source) as original:
        assert original.testzip() is None
        script = original.read(BASE_JS).decode('utf-8')
        anchor = 'Z.useEffect(()=>{const m=requestAnimationFrame(()=>Ad(yl));'
        assert script.count(anchor) == 1, 'Frontend integration anchor changed'
        # yl is the original visibility-filtered scene. ll commits the view and
        # cancels pending compositor navigation. fs uses original text bounds.
        integration = '''useDrawingSearch(Z,{entities:yl,busy:V,navigate:match=>{
          const fitView=fs([match.entity],W[0]*0.6,W[1]*0.6);
          pl("select");o([match.ownerId]);
          ll({...fitView,x:fitView.x+W[0]*0.2,y:fitView.y+W[1]*0.2});
        }});'''
        script = 'import {useDrawingSearch} from "./drawing-search-v0313.js";\n' + script.replace(anchor, integration + anchor)
        html_path = '_internal/frontend/dist/index.html'
        html = original.read(html_path).decode('utf-8')
        assert html.count('</head>') == 1
        html = html.replace('index-DJISSrak.js', 'index-DJISSrak.js?v=0.3.13')
        html = html.replace('</head>', '<link rel="stylesheet" href="./assets/drawing-search-v0313.css">\n</head>')
        replacements = {BASE_JS: script.encode(), html_path: html.encode()}
        additions = {
            ASSETS+'drawing-search-v0313.js': (ROOT/'drawing-search.js').read_bytes(),
            ASSETS+'drawing-search-v0313.css': (ROOT/'drawing-search.css').read_bytes(),
            'v0.3.13-검색기능.txt': 'MiniCAD Windows x64 v0.3.13\n\nv0.3.12 기반 문자 검색 추가\nCtrl+F: 검색창 열기\n입력: 검색 결과로 확대 이동\nEnter / Shift+Enter: 다음 / 이전 결과\nEsc: 검색 닫기\n현재 표시 중인 레이어의 문자와 블록 내부 문자를 검색합니다.\n\n전체 ZIP을 새 폴더에 압축 해제하고 MiniCAD.exe를 실행하세요.\n실행 파일과 기존 기능은 v0.3.12 그대로이며 화면 검색 기능만 추가했습니다.\n'.encode('utf-8-sig'),
        }
        info = json.loads(original.read('build-info.json'))
        info.update(version='0.3.13', base_version='0.3.12', base_archive_sha256=BASE_SHA256,
                    modification='Additive frontend text search; original EXE and backend unchanged')
        info['frontend_sha256'] = {
            name.removeprefix('_internal/frontend/dist/'): hashlib.sha256(replacements.get(name, original.read(name))).hexdigest()
            for name in original.namelist() if name.startswith('_internal/frontend/dist/') and not name.endswith('/')
        }
        info['frontend_sha256'].update({name.removeprefix('_internal/frontend/dist/'): hashlib.sha256(data).hexdigest()
                                       for name, data in additions.items() if name.startswith(ASSETS)})
        info['search_validation'] = 'See release validation report; original engine_validation is inherited from v0.3.12, not rerun.'
        replacements['build-info.json'] = (json.dumps(info, ensure_ascii=False, indent=2)+'\n').encode()
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for entry in original.infolist():
                output.writestr(copy.copy(entry), replacements.get(entry.filename, original.read(entry)))
            for name, data in additions.items(): output.writestr(name, data)
        with zipfile.ZipFile(destination) as output:
            assert output.testzip() is None
            changed = [name for name in original.namelist() if original.read(name) != output.read(name)]
            assert set(changed) == set(replacements), changed
            assert output.read('MiniCAD.exe') == original.read('MiniCAD.exe')
            print('Changed original entries:', changed)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(digest+'  '+destination.name+'\n')
    print(destination, digest)

if __name__ == '__main__': build(Path(sys.argv[1]), Path(sys.argv[2]))
