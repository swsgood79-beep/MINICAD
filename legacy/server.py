from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
import os, math
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import ezdxf
from ezdxf.addons import odafc

app = FastAPI(title='MiniCAD DWG MVP')
app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')
DOCS = {}

class Edit(BaseModel):
    op: str
    handle: str | None = None
    dx: float = 0
    dy: float = 0
    x1: float = 0
    y1: float = 0
    x2: float = 0
    y2: float = 0

@app.get('/')
def root(): return FileResponse(Path(__file__).parent/'static'/'index.html')

@app.get('/api/status')
def status(): return {'oda_installed': odafc.is_installed()}

def safe_number(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else 0
    except Exception: return 0

def serialize(doc):
    entities=[]; unsupported={}; limits=120000
    for e in doc.modelspace():
        if len(entities)>=limits: break
        kind=e.dxftype(); d=e.dxf; item={'id':d.handle, 'type':kind,'layer':d.get('layer','0')}
        try:
            if kind=='LINE':
                item.update(a=[safe_number(d.start.x),safe_number(d.start.y)],b=[safe_number(d.end.x),safe_number(d.end.y)])
            elif kind=='CIRCLE':
                item.update(c=[safe_number(d.center.x),safe_number(d.center.y)],r=safe_number(d.radius))
            elif kind=='ARC':
                item.update(c=[safe_number(d.center.x),safe_number(d.center.y)],r=safe_number(d.radius),start=safe_number(d.start_angle),end=safe_number(d.end_angle))
            elif kind=='LWPOLYLINE':
                pts=[list(map(float,p[:2])) for p in e.get_points('xy')]
                # Curved bulge segments are not faithfully rendered in MVP.
                item.update(pts=pts,closed=bool(e.closed),bulges=any(abs(p[4])>1e-12 for p in e.get_points('xyseb')))
            elif kind=='POINT': item.update(c=[safe_number(d.location.x),safe_number(d.location.y)])
            else:
                unsupported[kind]=unsupported.get(kind,0)+1
                continue
            entities.append(item)
        except (TypeError,ValueError,AttributeError): unsupported[kind]=unsupported.get(kind,0)+1
    return {'entities':entities,'unsupported':unsupported,'total':len(doc.modelspace()),'units':int(doc.header.get('$INSUNITS',0))}

@app.post('/api/open')
async def open_cad(file: UploadFile=File(...)):
    name=Path(file.filename or '').name
    suffix=Path(name).suffix.lower()
    if suffix not in ('.dwg','.dxf'): raise HTTPException(400,'DWG 또는 DXF 파일만 지원합니다.')
    content=await file.read(40*1024*1024+1)
    if len(content)>40*1024*1024: raise HTTPException(413,'파일 크기는 40MB 이하만 지원합니다.')
    try:
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/('drawing'+suffix);p.write_bytes(content)
            if suffix=='.dwg':
                if not odafc.is_installed(): raise HTTPException(422,'DWG를 열려면 서버 PC에 ODA File Converter를 설치해야 합니다. DXF는 바로 열 수 있습니다.')
                doc=odafc.readfile(p)
            else: doc=ezdxf.readfile(p)
        DOCS['active']=doc
        output=serialize(doc);output['filename']=name
        return output
    except HTTPException: raise
    except Exception as exc: raise HTTPException(422,f'도면을 읽지 못했습니다: {str(exc)[:300]}')

@app.post('/api/edit')
def edit(payload:Edit):
    doc=DOCS.get('active')
    if doc is None: raise HTTPException(400,'먼저 도면을 열어주세요.')
    msp=doc.modelspace()
    if payload.op=='add_line':
        msp.add_line((payload.x1,payload.y1),(payload.x2,payload.y2))
    elif payload.op in ('delete','move'):
        entity=doc.entitydb.get(payload.handle or '')
        if entity is None or entity not in msp: raise HTTPException(404,'객체를 찾지 못했습니다.')
        if payload.op=='delete': msp.delete_entity(entity)
        else:
            if entity.dxftype() not in ('LINE','CIRCLE','ARC','LWPOLYLINE','POINT'):
                raise HTTPException(400,'이동할 수 없는 객체입니다.')
            entity.translate(payload.dx,payload.dy,0)
    else: raise HTTPException(400,'지원하지 않는 작업입니다.')
    return serialize(doc)

@app.get('/api/export/{format}')
def export(format:str):
    doc=DOCS.get('active')
    if doc is None: raise HTTPException(400,'먼저 도면을 열어주세요.')
    if format not in ('dwg','dxf'): raise HTTPException(400,'지원하지 않는 형식입니다.')
    with TemporaryDirectory() as tmp:
        path=Path(tmp)/('edited.'+format)
        try:
            if format=='dwg':
                if not odafc.is_installed(): raise HTTPException(422,'DWG 저장에는 ODA File Converter가 필요합니다.')
                odafc.export_dwg(doc,path,version='R2018')
            else: doc.saveas(path)
            data=path.read_bytes()
        except HTTPException: raise
        except Exception as exc: raise HTTPException(500,f'저장 실패: {str(exc)[:300]}')
    return StreamingResponse(BytesIO(data),media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="edited.{format}"'})
