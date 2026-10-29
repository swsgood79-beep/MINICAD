"""DXF operations run exclusively inside a browser Web Worker (Pyodide)."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import math
import ezdxf
from cad_core import Drawing, CADProblem, serialize, edit_document
from dwg_database import import_database

session = None
session_id = None

def payload(data):
    values=dict(op='',handle=None,handles=[],dx=0,dy=0,x1=0,y1=0,x2=0,y2=0,radius=1,layer='0',revision=None)
    if set(data)-set(values):raise CADProblem(422,'알 수 없는 편집 필드입니다.')
    values.update(data)
    if values['op'] not in ('add_line','add_circle','move','copy','delete','set_line','set_circle'):
        raise CADProblem(422,'지원하지 않는 편집입니다.')
    for key in ('dx','dy','x1','y1','x2','y2','radius'):
        value=values[key]
        if not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>1e11:
            raise CADProblem(422,'유효한 좌표와 크기를 입력하세요.')
    if values['radius']<=0:raise CADProblem(422,'반지름은 0보다 커야 합니다.')
    return SimpleNamespace(**values)

def dispatch(path, data, key=None, filename='drawing.dxf'):
    global session, session_id
    if path=='/api/open-dwg-database':
        candidate=import_database(data,filename)
        result=serialize(candidate)
        if not result['entities']:raise CADProblem(422,'DWG 대체 읽기에서 표시 가능한 2D 객체를 찾지 못했습니다.')
        session,session_id=candidate,uuid4().hex
        return dict(result,document_id=session_id)
    if path in ('/api/open','/api/open-dwg'):
        if path=='/api/open' and not filename.lower().endswith('.dxf'):
            raise CADProblem(422,'무료 브라우저 버전은 DXF를 지원합니다. DWG는 CAD에서 DXF로 내보낸 뒤 열어주세요.')
        source=Path('/tmp/minicad-input.dxf')
        if source.stat().st_size>40*1024*1024:
            raise CADProblem(413,'파일 크기는 40MB 이하만 지원합니다.')
        try:
            doc=ezdxf.readfile(source)
            candidate=Drawing(doc,filename)
            if path=='/api/open-dwg':
                candidate.source_format='dwg'
                candidate.warnings.append('DWG 시험 읽기: 일부 객체·폰트·배치가 누락되거나 달라질 수 있습니다. 치수는 원본 CAD와 대조하세요. 수정은 현재 탭에서만 유지되며, DWG/DXF 저장은 제공하지 않습니다.')
            result=serialize(candidate)
        except Exception:
            raise CADProblem(422,'DXF를 읽지 못했습니다. 파일 형식과 손상 여부를 확인하세요.')
        finally:
            source.unlink(missing_ok=True)
        session,session_id=candidate,uuid4().hex
        return dict(result,document_id=session_id)
    if path=='/api/document':
        if key==session_id:
            session=session_id=None
        return {'closed':True}
    if not session or key!=session_id:
        raise CADProblem(404,'열린 도면이 없습니다. DXF 파일을 열어주세요.')
    if path=='/api/edit':return edit_document(session,payload(data))
    if path.startswith('/api/history/'):
        action=path.rsplit('/',1)[-1]
        if action not in ('undo','redo'):raise CADProblem(400,'지원하지 않는 이력 작업입니다.')
        source,target=(session.undo,session.redo) if action=='undo' else (session.redo,session.undo)
        if not source:raise CADProblem(400,'실행할 이력이 없습니다.')
        target.append(session.doc)
        session.doc=source.pop()
        session.revision+=1
        return serialize(session)
    if path.startswith('/api/export/') and session.source_format=='dwg':
        raise CADProblem(400,'DWG는 화면 수정·측정·인쇄만 지원하며 파일 저장은 제공하지 않습니다.')
    if path=='/api/export/dxf':
        session.doc.saveas('/tmp/minicad-output.dxf')
        return {'export':True}
    raise CADProblem(400,'무료 브라우저 버전에서는 DXF 기능만 지원합니다.')

def dispatch_json(path, data_json, key, filename):
    try:
        return json.dumps({'status':200,'data':dispatch(path,json.loads(data_json),key,filename)},ensure_ascii=False,allow_nan=False)
    except CADProblem as exc:
        return json.dumps({'status':exc.status_code,'data':{'detail':exc.detail}},ensure_ascii=False)
    except Exception:
        return json.dumps({'status':422,'data':{'detail':'도면 처리에 실패했습니다. 파일과 입력값을 확인하세요.'}},ensure_ascii=False)
