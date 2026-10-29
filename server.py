"""Local CAD server. Retains complete ezdxf documents; views never rebuild a DXF."""
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from typing import Literal
from uuid import uuid4
import base64
import binascii
import hmac
import math
import os

import ezdxf
from ezdxf.addons import odafc
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from cad_core import Drawing, CADProblem, HISTORY, serialize, primitive, edit_document

ROOT = Path(__file__).parent
# Use the official converter installed separately by the operator.
if os.getenv('ODA_FILE_CONVERTER'):
    for key in ('win_exec_path', 'linux_exec_path'):
        ezdxf.options.set('odafc-addon', key, os.environ['ODA_FILE_CONVERTER'])
@asynccontextmanager
async def lifespan(app):
    if os.getenv('MINICAD_DEPLOYED') == '1' and not (
        os.getenv('MINICAD_USERNAME') and os.getenv('MINICAD_PASSWORD')
    ):
        raise RuntimeError('Deployed mode requires MINICAD_USERNAME and MINICAD_PASSWORD.')
    yield

app = FastAPI(title='MiniCAD Web', version='0.2.0', lifespan=lifespan)

@app.middleware('http')
async def deployment_access(request: Request, call_next):
    # A private operator deployment. Hosting provides HTTPS; credentials stay server-side.
    username, password = os.getenv('MINICAD_USERNAME'), os.getenv('MINICAD_PASSWORD')
    if request.url.path == '/healthz':
        return await call_next(request)
    if username or password or os.getenv('MINICAD_DEPLOYED') == '1':
        if not username or not password:
            return Response('Deployment credentials are not configured.', status_code=503)
        valid = False
        try:
            scheme, token = request.headers.get('authorization', '').split(' ', 1)
            if scheme.lower() == 'basic':
                user, supplied = base64.b64decode(token, validate=True).decode('utf-8').split(':', 1)
                valid = hmac.compare_digest(user.encode(), username.encode()) & hmac.compare_digest(supplied.encode(), password.encode())
        except (ValueError, UnicodeError, binascii.Error):
            pass
        if not valid:
            return Response('Login required.', status_code=401, headers={'WWW-Authenticate': 'Basic realm="MiniCAD", charset="UTF-8"'})
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

@app.get('/healthz')
def health():
    return {'status': 'ok'}

@app.exception_handler(CADProblem)
async def cad_error(request, exc):
    return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)

lock = RLock()
MAX_DOCS = 8


DOCS: dict[str, Drawing] = {}

class Edit(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    op: Literal['add_line', 'add_circle', 'move', 'copy', 'delete', 'set_line', 'set_circle']
    handle: str | None = None
    handles: list[str] = Field(default_factory=list, max_length=10000)
    dx: float = Field(default=0, ge=-1e11, le=1e11)
    dy: float = Field(default=0, ge=-1e11, le=1e11)
    x1: float = Field(default=0, ge=-1e11, le=1e11)
    y1: float = Field(default=0, ge=-1e11, le=1e11)
    x2: float = Field(default=0, ge=-1e11, le=1e11)
    y2: float = Field(default=0, ge=-1e11, le=1e11)
    radius: float = Field(default=1, gt=0, le=1e11)
    layer: str = '0'
    revision: int | None = None


def drawing(request: Request, document_id: str | None):
    key = document_id or request.cookies.get('minicad_document')
    if key not in DOCS:
        raise HTTPException(404, '도면 세션이 없습니다. 파일을 다시 열어주세요.')
    return DOCS[key]







@app.get('/api/status')
def status():
    return {'oda_installed': odafc.is_installed(), 'mode':'private-hosted' if os.getenv('MINICAD_DEPLOYED') == '1' else 'local-only', 'history_limit': HISTORY}

@app.post('/api/open')
async def open_cad(response: Response, file: UploadFile = File(...)):
    name = Path((file.filename or '').replace('\\', '/')).name
    suffix = Path(name).suffix.lower()
    if suffix not in ('.dxf', '.dwg'):
        raise HTTPException(400, 'DWG 또는 DXF 파일만 지원합니다.')
    content = await file.read(40*1024*1024+1)
    await file.close()
    if len(content) > 40*1024*1024:
        raise HTTPException(413, '파일 크기는 40MB 이하만 지원합니다.')
    with lock:
        if len(DOCS) >= MAX_DOCS:
            raise HTTPException(503, '도면 세션 한도(8개)입니다. 사용하지 않는 도면을 닫아주세요.')
        try:
            with TemporaryDirectory() as tmp:
                p = Path(tmp)/('drawing'+suffix)
                p.write_bytes(content)
                if suffix == '.dwg':
                    if not odafc.is_installed():
                        raise HTTPException(422, 'DWG 입출력에는 서버에 ODA File Converter 설치가 필요합니다. DXF로 먼저 시험하세요.')
                    doc = odafc.readfile(p)
                else:
                    doc = ezdxf.readfile(p)
            s = Drawing(doc, name, ['DWG 변환은 버전·폰트·프록시 객체의 변경 또는 손실 가능성이 있습니다. 원본과 대조하세요.'] if suffix == '.dwg' else [])
            result = serialize(s)
            key = uuid4().hex
            DOCS[key] = s
            response.set_cookie('minicad_document', key, httponly=True, samesite='strict')
            return dict(result, document_id=key)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, '도면을 읽지 못했습니다. 손상 여부와 형식을 확인하세요.')

@app.delete('/api/document')
def close(request: Request, document_id: str | None = None):
    with lock:
        s = drawing(request, document_id)
        for key, value in list(DOCS.items()):
            if value is s:
                del DOCS[key]
        return {'closed': True}

@app.post('/api/edit')
def edit(payload: Edit, request: Request, document_id: str | None = None):
    with lock:
        return edit_document(drawing(request, document_id), payload)


@app.post('/api/history/{action}')
def history(action: Literal['undo','redo'], request: Request, document_id: str | None = None):
    with lock:
        s = drawing(request, document_id)
        source, target = (s.undo,s.redo) if action == 'undo' else (s.redo,s.undo)
        if not source:
            raise HTTPException(400, '실행할 이력이 없습니다.')
        target.append(s.doc)
        s.doc = source.pop()
        s.revision += 1
        return serialize(s)

@app.get('/api/export/{format}')
def export(format: Literal['dxf','dwg'], request: Request, document_id: str | None = None):
    with lock:
        s = drawing(request, document_id)
        try:
            with TemporaryDirectory() as tmp:
                path = Path(tmp)/('edited.'+format)
                if format == 'dwg':
                    if not odafc.is_installed():
                        raise HTTPException(422, 'DWG 저장에는 ODA File Converter가 필요합니다.')
                    odafc.export_dwg(s.doc,path,version='R2018')
                else:
                    s.doc.saveas(path)
                data = path.read_bytes()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(500, '저장에 실패했습니다. 변환기와 도면을 확인하세요.')
        return StreamingResponse(BytesIO(data),media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="drawing_edited.{format}"'})

# Keep the original MVP available as a fallback, using cookie-scoped API sessions.
app.mount('/static', StaticFiles(directory=ROOT/'legacy/static'), name='legacy-static')
@app.get('/legacy')
def legacy():
    return FileResponse(ROOT/'legacy/static/index.html')

@app.get('/')
def root():
    index = ROOT/'frontend/dist/index.html'
    if not index.exists():
        raise HTTPException(503, 'frontend에서 npm ci && npm run build를 먼저 실행하세요. 기존 화면: /legacy')
    return FileResponse(index)

app.mount('/assets', StaticFiles(directory=ROOT/'frontend/dist/assets',check_dir=False), name='assets')
