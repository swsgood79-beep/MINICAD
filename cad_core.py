"""Shared ezdxf document engine for FastAPI and the browser Python worker."""
from copy import deepcopy
from dataclasses import dataclass, field
import math
import ezdxf

HISTORY = 30
EDITABLE = {'LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'POINT'}

class CADProblem(ValueError):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)

@dataclass
class Drawing:
    doc: object
    name: str
    warnings: list[str] = field(default_factory=list)
    undo: list = field(default_factory=list)
    redo: list = field(default_factory=list)
    revision: int = 0
    source_format: str = 'dxf'
    import_unsupported: dict = field(default_factory=dict)
    unrendered_roots: int = 0

def planar(e):
    if e.dxftype() == 'POLYLINE' and not e.is_2d_polyline:
        return False
    normal = e.dxf.get('extrusion', (0, 0, 1))
    return all(abs(a-b) < 1e-10 for a,b in zip(normal, (0,0,1)))

def primitive(e, depth=0, ancestors=()):
    d = e.dxf
    k = e.dxftype()
    def xy(p):
        result = [float(p[0]), float(p[1])]
        if not all(math.isfinite(v) and abs(v) < 1e12 for v in result):
            raise ValueError('좌표 범위 초과')
        return result
    if not planar(e):
        raise ValueError('2D XY 평면만 지원')
    item = {'id': d.get('handle', ''), 'type': k, 'layer': d.get('layer', '0')}
    if k == 'LINE':
        if abs(d.start.z-d.end.z) > 1e-8:
            raise ValueError('3D 선')
        item.update(a=xy(d.start), b=xy(d.end))
    elif k in ('CIRCLE', 'ARC'):
        if not math.isfinite(d.radius) or d.radius <= 0 or d.radius >= 1e12:
            raise ValueError('반지름 범위 초과')
        item.update(c=xy(d.center), r=float(d.radius))
        if k == 'ARC':
            item.update(start=float(d.start_angle), end=float(d.end_angle))
    elif k in ('LWPOLYLINE', 'POLYLINE'):
        item.update(segments=[primitive(v) for v in e.virtual_entities()], closed=bool(e.is_closed if k == 'POLYLINE' else e.closed))
    elif k in ('INSERT', 'DIMENSION'):
        name=d.get('name', '') if k=='INSERT' else ''
        if depth>=8 or name and name in ancestors:
            raise ValueError('블록 중첩 한도 또는 순환 참조')
        parts=[]
        omitted={}
        for child in e.virtual_entities():
            try:
                parts.append(primitive(child,depth+1,ancestors+((name,) if name else ())))
            except (ValueError,TypeError,AttributeError,ezdxf.DXFError):
                kind=child.dxftype()
                omitted[kind]=omitted.get(kind,0)+1
        if not parts:
            raise ValueError('표시 가능한 블록 또는 치수 객체가 없습니다.')
        item.update(segments=parts,display_only=True,omitted=omitted)
    elif k == 'POINT':
        item.update(c=xy(d.location))
    elif k in ('TEXT', 'MTEXT'):
        item.update(c=xy(d.insert), text=e.plain_text(), height=float(d.get('height', 1) if k == 'TEXT' else d.get('char_height', 1)), rotation=float(d.get('rotation', 0)))
    else:
        raise ValueError('미지원 객체')
    return item

def serialize(s: Drawing):
    entities, unsupported = [], dict(s.import_unsupported)
    truncated = False
    for i, e in enumerate(s.doc.modelspace()):
        if i >= 120000:
            truncated = True
            break
        try:
            item=primitive(e)
            entities.append(item)
            def omissions(value):
                for kind,count in value.get('omitted',{}).items():
                    unsupported[kind]=unsupported.get(kind,0)+count
                for child in value.get('segments',[]):omissions(child)
            omissions(item)
        except (ValueError, TypeError, AttributeError, ezdxf.DXFError):
            k = e.dxftype()
            unsupported[k] = unsupported.get(k, 0)+1
    warnings = list(s.warnings)
    if unsupported:
        warnings.append('DWG 미지원 객체가 화면에서 생략되었습니다. 화면만으로 원본 전체를 판단하지 마세요. 원본 DWG 파일은 변경하지 않습니다.' if s.source_format=='dwg' else '미표시 객체는 원본 DXF 문서에 유지됩니다. 화면만으로 도면 전체를 판단하지 마세요.')
    if truncated:
        warnings.append('화면 표시 한도 120,000개를 초과했습니다. 나머지 객체도 문서에는 보존됩니다.')
    return dict(entities=entities, unsupported=unsupported, total=len(s.doc.modelspace())+s.unrendered_roots, units=int(s.doc.units),
                filename=s.name, source_format=s.source_format, layers=[{'name':l.dxf.name,'visible':not l.is_off() and not l.is_frozen(),'locked':l.is_locked()} for l in s.doc.layers],
                warnings=warnings, truncated=truncated, revision=s.revision, can_undo=bool(s.undo), can_redo=bool(s.redo))

def edit_document(s, payload):
    if payload.revision is not None and payload.revision != s.revision:
        raise CADProblem(409, '도면 버전이 변경되었습니다. 다시 열어주세요.')
    candidate = deepcopy(s.doc)
    msp = candidate.modelspace()
    try:
        if payload.layer not in candidate.layers:
            raise ValueError('없는 레이어입니다.')
        if payload.op in ('add_line', 'add_circle'):
            if candidate.layers.get(payload.layer).is_locked():
                raise ValueError('잠긴 레이어입니다.')
            attrs = {'layer': payload.layer}
            if payload.op == 'add_line':
                if payload.x1 == payload.x2 and payload.y1 == payload.y2:
                    raise ValueError('선의 길이는 0보다 커야 합니다.')
                msp.add_line((payload.x1, payload.y1), (payload.x2, payload.y2), dxfattribs=attrs)
            else:
                msp.add_circle((payload.x1, payload.y1), payload.radius, dxfattribs=attrs)
        else:
            handles = list(dict.fromkeys(payload.handles or ([payload.handle] if payload.handle else [])))
            if not handles:
                raise ValueError('먼저 객체를 선택하세요.')
            for handle in handles:
                e = candidate.entitydb.get(handle)
                if e is None or not e.is_alive or e not in msp:
                    raise ValueError('객체를 찾지 못했습니다.')
                if e.dxftype() not in EDITABLE or not planar(e):
                    raise ValueError('이 단계에서는 이 객체를 편집할 수 없습니다.')
                if candidate.layers.get(e.dxf.layer).is_locked():
                    raise ValueError('잠긴 레이어입니다.')
                if payload.op == 'delete':
                    msp.delete_entity(e)
                elif payload.op in ('move', 'copy'):
                    if payload.op == 'copy':
                        e = e.copy()
                        msp.add_entity(e)
                    e.translate(payload.dx, payload.dy, 0)
                elif payload.op == 'set_line' and e.dxftype() == 'LINE':
                    if (payload.x1, payload.y1) == (payload.x2, payload.y2):
                        raise ValueError('선의 길이는 0보다 커야 합니다.')
                    e.dxf.start = (payload.x1, payload.y1, e.dxf.start.z)
                    e.dxf.end = (payload.x2, payload.y2, e.dxf.end.z)
                elif payload.op == 'set_circle' and e.dxftype() == 'CIRCLE':
                    e.dxf.center = (payload.x1, payload.y1, e.dxf.center.z)
                    e.dxf.radius = payload.radius
                else:
                    raise ValueError('객체 형식과 수정 작업이 맞지 않습니다.')
                if payload.op != 'delete':
                    primitive(e)
    except (ValueError, ezdxf.DXFError) as exc:
        raise CADProblem(400, str(exc))
    s.undo.append(s.doc)
    s.undo = s.undo[-HISTORY:]
    s.redo.clear()
    s.doc = candidate
    s.revision += 1
    return serialize(s)
