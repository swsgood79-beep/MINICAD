import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  visibleEntities,
  type Entity,
  type Point,
  type View,
  type Snap,
  toScreen,
  toWorld,
  zoom,
  fit,
  paths,
  pick,
  snap,
  distance,
  length,
  angle,
} from "./geometry";
import "./style.css";
import { printDrawing } from "./printing";
import { browserMode, cadFetch } from "./transport";
type Drawing = {
  document_id?: string;
  preview?: boolean;
  history_limit?: number;
  source_format?: string;
  entities: Entity[];
  filename: string;
  layers: { name: string; visible: boolean; locked: boolean }[];
  units: number;
  total: number;
  unsupported: Record<string, number>;
  warnings: string[];
  revision: number;
  can_undo: boolean;
  can_redo: boolean;
};
const unitNames: Record<number, string> = {
  0: "미지정",
  1: "inch",
  2: "ft",
  3: "mile",
  4: "mm",
  5: "cm",
  6: "m",
  7: "km",
  8: "µinch",
  9: "mil",
  10: "yd",
  11: "Å",
  12: "nm",
  13: "µm",
  14: "dm",
  15: "dam",
  16: "hm",
  17: "Gm",
  18: "AU",
  19: "광년",
  20: "pc",
  21: "US ft",
  22: "US inch",
  23: "US yd",
  24: "US mile",
};
const modes = [
  ["select", "선택"],
  ["measure", "두 점 거리"],
  ["horizontal", "수평 거리"],
  ["vertical", "수직 거리"],
  ["radius", "반지름·직경"],
  ["angle", "두 선 각도"],
  ["length", "폴리라인 길이"],
  ["line", "선 추가"],
  ["circle", "원 추가"],
  ["move", "객체 이동"],
  ["copy", "객체 복사"],
] as const;
function App() {
  const [openError, setOpenError] = useState<string | null>(null);
  const [drawing, setDrawing] = useState<Drawing | null>(null),
    [docId, setDocId] = useState(""),
    [mode, setMode] = useState("select"),
    [selected, setSelected] = useState<string[]>([]),
    [pending, setPending] = useState<Point | null>(null),
    [angleLine, setAngleLine] = useState<Entity | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set()),
    [view, setView] = useState<View>({ x: 200, y: 300, scale: 2 }),
    [size, setSize] = useState([800, 600]),
    [cursor, setCursor] = useState<Point>([0, 0]),
    [snapped, setSnapped] = useState<Snap | undefined>(),
    [snapOn, setSnapOn] = useState(true),
    [digits, setDigits] = useState(3),
    [message, setMessage] = useState(
      browserMode
        ? "DWG 또는 DXF를 여세요. 첫 실행 시 도면 엔진을 준비합니다."
        : "DWG 또는 DXF 파일을 열어 시작하세요.",
    ),
    [result, setResult] = useState("—"),
    [busy, setBusy] = useState(false),
    [oda, setOda] = useState(false),
    [dirty, setDirty] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null),
    stage = useRef<HTMLDivElement>(null),
    drag = useRef<{ point: Point; view: View } | null>(null),
    busyRef = useRef(false);
  const visible = useMemo(
    () => visibleEntities(drawing?.entities ?? [], hidden),
    [drawing, hidden],
  );
  const fmt = (n: number) => n.toFixed(digits),
    unit = unitNames[drawing?.units ?? 0] ?? `단위 코드 ${drawing?.units}`;
  const point = (e: { clientX: number; clientY: number }): Point => {
    const r = canvas.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  useEffect(() => {
    const obs = new ResizeObserver(([entry]) =>
      setSize([entry.contentRect.width, entry.contentRect.height]),
    );
    obs.observe(stage.current!);
    cadFetch("/api/status")
      .then((r) => r.json())
      .then((v) => setOda(v.oda_installed))
      .catch(() => setMessage("서버 연결을 확인하세요."));
    return () => obs.disconnect();
  }, []);
  useEffect(() => {
    const c = canvas.current!,
      ctx = c.getContext("2d")!,
      dpr = window.devicePixelRatio || 1;
    const [w, h] = size;
    c.width = w * dpr;
    c.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#0c141e";
    ctx.fillRect(0, 0, w, h);
    const step = 10 ** Math.ceil(Math.log10(50 / view.scale));
    ctx.lineWidth = 0.5;
    ctx.strokeStyle = "#233043";
    const lo = toWorld([0, h], view),
      hi = toWorld([w, 0], view);
    for (let i = Math.floor(lo[0] / step); i <= Math.ceil(hi[0] / step); i++) {
      const x = toScreen([i * step, 0], view)[0];
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let i = Math.floor(lo[1] / step); i <= Math.ceil(hi[1] / step); i++) {
      const y = toScreen([0, i * step], view)[1];
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
    const paint = (e: Entity, highlight: boolean) => {
      if (e.segments) {
        e.segments.forEach((part) => paint(part, highlight));
        return;
      }
      ctx.strokeStyle = highlight ? "#ffcb6b" : "#74dbe8";
      ctx.fillStyle = ctx.strokeStyle;
      ctx.lineWidth = highlight ? 2.5 : 1.2;
      if (e.type === "TEXT" || e.type === "MTEXT") {
        const p = toScreen(e.c!, view);
        ctx.save();
        ctx.translate(...p);
        ctx.rotate((-(e.rotation ?? 0) * Math.PI) / 180);
        ctx.font = `${Math.max(1, (e.height ?? 1) * view.scale)}px sans-serif`;
        for (const [i, line] of (e.text ?? "").split("\n").entries())
          ctx.fillText(line, 0, i * (e.height ?? 1) * view.scale * 1.3);
        ctx.restore();
        return;
      }
      for (const path of paths(e)) {
        if (!path.length) continue;
        ctx.beginPath();
        const first = toScreen(path[0], view);
        ctx.moveTo(...first);
        if (path.length === 1) {
          ctx.arc(...first, 3, 0, Math.PI * 2);
          ctx.fill();
        } else {
          for (let i = 1; i < path.length; i++)
            ctx.lineTo(...toScreen(path[i], view));
          ctx.stroke();
        }
      }
    };
    visible.forEach((e) => paint(e, selected.includes(e.id)));
    if (pending) {
      ctx.strokeStyle = "#facc15";
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(...toScreen(pending, view));
      ctx.lineTo(...toScreen(snapped?.point ?? cursor, view));
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (snapped) {
      const [x, y] = toScreen(snapped.point, view);
      ctx.strokeStyle = "#6bff99";
      ctx.strokeRect(x - 5, y - 5, 10, 10);
      ctx.font = "12px sans-serif";
      ctx.fillStyle = "#6bff99";
      ctx.fillText(snapped.kind, x + 9, y - 9);
    }
  }, [drawing, hidden, selected, view, size, pending, cursor, snapped]);
  async function response(r: Response) {
    if (!r.ok) {
      const j = await r.json();
      throw new Error(
        typeof j.detail === "string" ? j.detail : "입력값을 확인하세요.",
      );
    }
    return r;
  }
  async function run(task: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      await task();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  const endpoint = (path: string) =>
    `${path}?document_id=${encodeURIComponent(docId)}`;
  function requestPrint() {
    if (!drawing || busy) return;
    if (
      drawing.preview &&
      !window.confirm(
        "현재 도면은 일부만 표시된 미리보기입니다. 전체 도면 인쇄가 아닙니다. 표시 중인 부분만 인쇄할까요?",
      )
    )
      return;
    printDrawing(visible, drawing.filename, result, unit, drawing.warnings);
  }
  async function edit(payload: object) {
    await run(async () => {
      const r = await response(
        await cadFetch(endpoint("/api/edit"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload, revision: drawing?.revision }),
        }),
      );
      setDrawing(await r.json());
      setDirty(true);
      setPending(null);
      setSelected([]);
      setMessage("수정 완료 · 원본 파일은 변경되지 않았습니다.");
    });
  }
  async function history(action: string) {
    await run(async () => {
      const r = await response(
        await cadFetch(endpoint("/api/history/" + action), { method: "POST" }),
      );
      setDrawing(await r.json());
      setSelected([]);
      setPending(null);
      setDirty(true);
      setMessage(action === "undo" ? "실행 취소 완료" : "다시 실행 완료");
    });
  }
  function changeMode(m: string) {
    setMode(m);
    setPending(null);
    setAngleLine(null);
    setSnapped(undefined);
    setMessage(
      m === "move" || m === "copy"
        ? "객체 선택 후 기준점과 목적점을 클릭하세요."
        : "도구: " + modes.find((x) => x[0] === m)?.[1],
    );
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p" && drawing) {
        e.preventDefault();
        if (!busy) requestPrint();
        return;
      }
      if ((e.target as HTMLElement).matches("input,textarea,select")) return;
      if (e.key === "Escape") {
        setPending(null);
        setAngleLine(null);
        setSelected([]);
        changeMode("select");
      }
      if (e.key === "Delete" && selected.length) {
        e.preventDefault();
        void edit({ op: "delete", handles: selected });
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        void history(e.shiftKey ? "redo" : "undo");
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        void history("redo");
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  useEffect(() => {
    const unload = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", unload);
    return () => window.removeEventListener("beforeunload", unload);
  }, [dirty]);
  useEffect(() => {
    const c = canvas.current!;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      setView((v) =>
        zoom(
          v,
          point(e),
          Math.exp(-Math.max(-1000, Math.min(1000, e.deltaY)) * 0.0015),
        ),
      );
    };
    c.addEventListener("wheel", wheel, { passive: false });
    return () => c.removeEventListener("wheel", wheel);
  }, []);
  async function open(file: File) {
    if (
      dirty &&
      !window.confirm(
        "현재 탭의 수정 내용이 사라집니다. 필요한 경우 저장 또는 인쇄한 뒤 새 도면을 여세요. 계속할까요?",
      )
    )
      return;
    await run(async () => {
      const data = new FormData();
      data.append("file", file);
      setOpenError(null);
      let r: Response;
      try {
        r = await response(
          await cadFetch("/api/open", { method: "POST", body: data }),
        );
      } catch (error) {
        setOpenError((error as Error).message);
        throw error;
      }
      const d: Drawing = await r.json();
      if (docId)
        await cadFetch(endpoint("/api/document"), { method: "DELETE" });
      setDrawing(d);
      setDocId(d.document_id!);
      changeMode("select");
      const hidden = new Set(
        d.layers.filter((l) => !l.visible).map((l) => l.name),
      );
      setHidden(hidden);
      setView(
        fit(
          d.entities.filter((e) => !hidden.has(e.layer)),
          size[0],
          size[1],
        ),
      );
      setSelected([]);
      setPending(null);
      setResult("—");
      setDirty(false);
      setMessage(`${file.name} · 불러오기 완료`);
    });
  }
  async function save(format: string) {
    if (
      format === "dwg" &&
      !window.confirm(
        "DWG 변환 과정에서 객체·폰트·버전 정보가 달라질 수 있습니다. 별도 파일로 저장할까요?",
      )
    )
      return;
    await run(async () => {
      const r = await response(
        await cadFetch(endpoint("/api/export/" + format)),
      );
      const url = URL.createObjectURL(await r.blob()),
        a = document.createElement("a");
      a.href = url;
      a.download =
        drawing!.filename.replace(/\.(dwg|dxf)$/i, "") + "_edited." + format;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      setDirty(false);
      setMessage("별도 이름으로 다운로드했습니다. 원본과 비교 검증하세요.");
    });
  }
  function click(e: React.PointerEvent<HTMLCanvasElement>) {
    if (e.button !== 0 || !drawing || busy) return;
    const raw = toWorld(point(e), view),
      p =
        (snapOn ? snap(raw, visible, 10 / view.scale)?.point : undefined) ??
        raw,
      hit = pick(raw, visible, 10 / view.scale);
    if (mode === "select") {
      setSelected(
        hit
          ? e.shiftKey
            ? selected.includes(hit.id)
              ? selected.filter((id) => id !== hit.id)
              : [...selected, hit.id]
            : [hit.id]
          : [],
      );
      return;
    }
    if (mode === "radius") {
      if (hit?.type === "CIRCLE" || hit?.type === "ARC")
        setResult(`R ${fmt(hit.r!)} · Ø ${fmt(hit.r! * 2)} ${unit}`);
      else setMessage("원 또는 호를 클릭하세요.");
      return;
    }
    if (mode === "length") {
      if (hit?.partial) {
        setResult("전체 길이 측정 불가");
        setMessage("이 객체는 일부만 표시되어 전체 길이를 측정할 수 없습니다.");
        return;
      }
      if (
        hit &&
        (hit.type === "LWPOLYLINE" ||
          hit.type === "POLYLINE" ||
          hit.type === "LINE" ||
          hit.type === "ARC" ||
          hit.type === "CIRCLE")
      )
        setResult(`길이 ${fmt(length(hit))} ${unit}`);
      return;
    }
    if (mode === "angle") {
      if (hit?.type === "LINE" && distance(hit.a!, hit.b!) === 0) {
        setMessage("길이가 0인 선의 각도는 측정할 수 없습니다.");
        return;
      }
      if (hit?.type !== "LINE") {
        setMessage("직선을 클릭하세요.");
        return;
      }
      if (!angleLine) {
        setAngleLine(hit);
        setMessage("두 번째 직선을 클릭하세요.");
      } else {
        setResult(`각도 ${fmt(angle(angleLine, hit))}° (방향 벡터 0–180°)`);
        setAngleLine(null);
      }
      return;
    }
    if (mode === "move" || mode === "copy") {
      if (!selected.length) {
        if (hit) setSelected([hit.id]);
        setMessage("기준점을 클릭하세요.");
        return;
      }
      if (!pending) {
        setPending(p);
        setMessage("목적점을 클릭하세요.");
      } else
        void edit({
          op: mode,
          handles: selected,
          dx: p[0] - pending[0],
          dy: p[1] - pending[1],
        });
      return;
    }
    if (!pending) {
      setPending(p);
      return;
    }
    if (mode === "line")
      void edit({
        op: "add_line",
        x1: pending[0],
        y1: pending[1],
        x2: p[0],
        y2: p[1],
      });
    else if (mode === "circle")
      void edit({
        op: "add_circle",
        x1: pending[0],
        y1: pending[1],
        radius: distance(pending, p),
      });
    else {
      const n =
        mode === "horizontal"
          ? Math.abs(p[0] - pending[0])
          : mode === "vertical"
            ? Math.abs(p[1] - pending[1])
            : distance(pending, p);
      setResult(`${fmt(n)} ${unit}`);
      setPending(null);
    }
  }
  const selectedEntity =
    selected.length === 1
      ? drawing?.entities.find((e) => e.id === selected[0])
      : undefined;
  return (
    <div className="app">
      <header>
        <h1>
          MiniCAD <span>Web</span>
        </h1>
        {browserMode && (
          <button
            disabled={busy}
            onClick={() => {
              void fetch(
                new URL(
                  "sample.dxf",
                  new URL(import.meta.env.BASE_URL, document.baseURI),
                ),
              )
                .then((r) => {
                  if (!r.ok) throw Error("샘플 도면을 불러오지 못했습니다.");
                  return r.blob();
                })
                .then((blob) => open(new File([blob], "MiniCAD_예제.dxf")))
                .catch((e) => setMessage(e.message));
            }}
          >
            예제 도면
          </button>
        )}
        <label className="file">
          도면 열기
          <input
            disabled={busy}
            type="file"
            accept=".dwg,.dxf"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void open(f);
              e.target.value = "";
            }}
          />
        </label>
        <button
          disabled={!drawing || drawing.source_format === "dwg" || busy}
          onClick={() => void save("dxf")}
        >
          DXF 별도 저장
        </button>
        {!browserMode && (
          <button
            disabled={!drawing || !oda || busy}
            onClick={() => void save("dwg")}
          >
            DWG 별도 저장
          </button>
        )}
        <button
          disabled={!drawing || !visible.length || busy}
          onClick={() => requestPrint()}
        >
          인쇄 / PDF
        </button>
        <button
          disabled={!drawing?.can_undo || busy}
          onClick={() => void history("undo")}
        >
          실행 취소
        </button>
        <button
          disabled={!drawing?.can_redo || busy}
          onClick={() => void history("redo")}
        >
          다시 실행
        </button>
        <button onClick={() => setView(fit(visible, size[0], size[1]))}>
          전체 맞춤
        </button>
        <button
          disabled={!drawing || busy}
          onClick={() => {
            if (
              dirty &&
              !window.confirm(
                "현재 탭의 수정 내용을 버리고 닫을까요? 필요한 내용은 저장 또는 인쇄해 주세요.",
              )
            )
              return;
            void run(async () => {
              await response(
                await cadFetch(endpoint("/api/document"), { method: "DELETE" }),
              );
              setDrawing(null);
              setDocId("");
              setSelected([]);
              setPending(null);
              setDirty(false);
              setMessage("도면을 닫았습니다.");
            });
          }}
        >
          도면 닫기
        </button>
        <span className="filename">
          {drawing?.filename ?? "열린 도면 없음"}
          {dirty ? " *" : ""}
        </span>
      </header>
      <main>
        <nav aria-label="CAD 도구">
          {modes.map(([id, title]) => (
            <button
              key={id}
              className={mode === id ? "active" : ""}
              disabled={
                busy ||
                Boolean(
                  drawing?.preview && ["line", "circle", "copy"].includes(id),
                )
              }
              onClick={() => changeMode(id)}
            >
              {title}
            </button>
          ))}
          <button
            disabled={!selected.length || busy}
            onClick={() => void edit({ op: "delete", handles: selected })}
          >
            객체 삭제
          </button>
          <small>
            휠: 확대·축소
            <br />
            가운데/오른쪽 드래그: 이동
            <br />
            Shift+클릭: 다중 선택
            <br />
            Esc: 취소
            <br />
            Ctrl+Z / Ctrl+Y
          </small>
        </nav>
        <div className="stage" ref={stage}>
          {drawing?.preview && (
            <div className="preview-banner">
              부분 미리보기 · 도면 일부만 표시합니다. 표시된 범위만 측정할 수
              있으며 전체 도면 인쇄가 아닙니다.
            </div>
          )}
          {openError && (
            <div className="open-error" role="alert">
              <strong>도면을 열지 못했습니다</strong>
              <p>{openError}</p>
              <p>
                열려 있던 도면은 그대로 유지됩니다. 다른 파일로 시험하거나, 문제
                파일을 지원 담당자에게 별도로 전달해 주세요.
              </p>
              <button onClick={() => setOpenError(null)}>닫기</button>
            </div>
          )}
          <canvas
            aria-label="CAD 도면 작업 영역"
            ref={canvas}
            onContextMenu={(e) => e.preventDefault()}
            onPointerDown={(e) => {
              if (e.button === 1 || e.button === 2) {
                e.preventDefault();
                drag.current = { point: point(e), view };
                e.currentTarget.setPointerCapture(e.pointerId);
              } else click(e);
            }}
            onPointerMove={(e) => {
              const p = point(e);
              if (drag.current) {
                const d = drag.current;
                setView({
                  ...d.view,
                  x: d.view.x + p[0] - d.point[0],
                  y: d.view.y + p[1] - d.point[1],
                });
              } else {
                const w = toWorld(p, view);
                setCursor(w);
                setSnapped(
                  snapOn ? snap(w, visible, 10 / view.scale) : undefined,
                );
              }
            }}
            onPointerUp={(e) => {
              drag.current = null;
              if (e.currentTarget.hasPointerCapture(e.pointerId))
                e.currentTarget.releasePointerCapture(e.pointerId);
            }}
            onPointerCancel={() => (drag.current = null)}
            onPointerLeave={() => setSnapped(undefined)}
          />
          {!drawing && (
            <div className="empty">
              <strong>도면에서 시작하세요</strong>
              <p>
                {browserMode
                  ? "DWG·DXF를 브라우저 안에서 처리합니다. DWG 수정은 현재 탭에만 적용됩니다."
                  : "DXF를 바로 열거나 ODA 변환기로 DWG를 불러오세요."}
              </p>
              <p>실제 좌표 기반 측정 · 원본을 유지하는 별도 저장</p>
            </div>
          )}
        </div>
        <aside>
          <h2>도면 정보</h2>
          {drawing?.preview && (
            <p className="warning">
              부분 미리보기 · 전체 도면이 아닙니다. 실행 취소 최대{" "}
              {drawing.history_limit ?? 30}회.
            </p>
          )}
          <p>
            {drawing
              ? `${drawing.total}개 객체 · 표시 ${visible.length}개`
              : "도면을 열어주세요"}
          </p>
          <p>단위: {unit}</p>
          <p>
            DWG:{" "}
            {browserMode
              ? "브라우저 시험 읽기 · 저장 제외"
              : oda
                ? "ODA 설치 확인"
                : "ODA 설치 필요"}
          </p>
          <h2>측정</h2>
          <output data-testid="measurement">{result}</output>
          <label>
            소수점{" "}
            <select
              aria-label="소수점 자릿수"
              value={digits}
              onChange={(e) => setDigits(Number(e.target.value))}
            >
              {[0, 1, 2, 3, 4, 5, 6].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <h2>레이어</h2>
          {drawing?.layers.map((l) => (
            <label className="layer" key={l.name}>
              <input
                type="checkbox"
                checked={!hidden.has(l.name)}
                onChange={() => {
                  setHidden((old) => {
                    const n = new Set(old);
                    if (n.has(l.name)) n.delete(l.name);
                    else n.add(l.name);
                    return n;
                  });
                  setSelected([]);
                  setPending(null);
                  setSnapped(undefined);
                }}
              />
              {l.name}
              {l.locked ? " 🔒" : ""}
            </label>
          ))}
          <h2>객체 속성</h2>
          {drawing?.source_format === "dwg" && (
            <p className="note">
              DWG 수정은 현재 화면에만 적용됩니다. 인쇄/PDF로 보관하세요. 원본
              DWG 파일은 변경되지 않습니다.
            </p>
          )}
          <p>{selected.length}개 선택</p>
          {selectedEntity && (
            <>
              <p>
                {selectedEntity.type} · {selectedEntity.id}
                <br />
                레이어 {selectedEntity.layer}
              </p>
              <Properties
                key={selectedEntity.id + ":" + drawing?.revision}
                entity={selectedEntity}
                busy={busy}
                submit={edit}
              />
            </>
          )}
          {drawing?.warnings.map((w, i) => (
            <p className="warning" key={i}>
              {w}
            </p>
          ))}
          {drawing && Object.keys(drawing.unsupported).length > 0 && (
            <p className="warning">
              미표시:{" "}
              {Object.entries(drawing.unsupported)
                .map(([k, v]) => `${k} ${v}`)
                .join(", ")}
            </p>
          )}
          <p className="note">
            {browserMode
              ? "DWG·DXF 브라우저 버전 · 파일 외부 전송 없음"
              : "시험 버전 · 로컬 사용 전용"}
            <br />
            문자 배치는 근사 표시입니다. 원본 도면을 보관하고 저장 결과를
            대조하세요.
          </p>
        </aside>
      </main>
      <footer>
        <span>
          X {fmt(cursor[0])} · Y {fmt(cursor[1])}
        </span>
        <label>
          <input
            type="checkbox"
            checked={snapOn}
            onChange={(e) => {
              setSnapOn(e.target.checked);
              setSnapped(undefined);
            }}
          />
          끝점·중간점·중심점 스냅
        </label>
        <span>{unit}</span>
        <a
          className="licenses"
          href={
            new URL(
              "third-party/",
              new URL(import.meta.env.BASE_URL, document.baseURI),
            ).href
          }
          target="_blank"
          rel="noreferrer"
        >
          오픈소스
        </a>
        <span role="status">{busy ? "처리 중…" : message}</span>
      </footer>
    </div>
  );
}
function Properties({
  entity: e,
  busy,
  submit,
}: {
  entity: Entity;
  busy: boolean;
  submit: (p: object) => Promise<void>;
}) {
  const initial: Record<string, number> | null =
    e.type === "LINE"
      ? { x1: e.a![0], y1: e.a![1], x2: e.b![0], y2: e.b![1] }
      : e.type === "CIRCLE"
        ? { x1: e.c![0], y1: e.c![1], radius: e.r! }
        : null;
  const [values, setValues] = useState<Record<string, number>>(initial ?? {});
  const [targetLength, setTargetLength] = useState(
    e.type === "LINE" ? distance(e.a!, e.b!) : 0,
  );
  if (!initial) return <p>좌표 편집은 선·원부터 지원합니다.</p>;
  return (
    <form
      onSubmit={(ev) => {
        ev.preventDefault();
        void submit({
          op: e.type === "LINE" ? "set_line" : "set_circle",
          handle: e.id,
          ...values,
        });
      }}
    >
      {Object.entries(values).map(([key, v]) => (
        <label key={key}>
          {key}
          <input
            aria-label={key}
            required
            type="number"
            step="any"
            min={key === "radius" ? "0.000000001" : undefined}
            value={Number.isNaN(v) ? "" : v}
            onChange={(ev) =>
              setValues({ ...values, [key]: ev.target.valueAsNumber })
            }
          />
        </label>
      ))}
      <button disabled={busy}>좌표·크기 적용</button>
      {e.type === "LINE" && (
        <>
          <label>
            선 길이
            <input
              aria-label="선 길이"
              type="number"
              min="0.000000001"
              step="any"
              value={targetLength}
              onChange={(ev) => setTargetLength(ev.target.valueAsNumber)}
            />
          </label>
          <button
            type="button"
            disabled={
              busy ||
              !Number.isFinite(targetLength) ||
              targetLength <= 0 ||
              distance(e.a!, e.b!) === 0
            }
            onClick={() => {
              const ratio = targetLength / distance(e.a!, e.b!);
              void submit({
                op: "set_line",
                handle: e.id,
                x1: e.a![0],
                y1: e.a![1],
                x2: e.a![0] + (e.b![0] - e.a![0]) * ratio,
                y2: e.a![1] + (e.b![1] - e.a![1]) * ratio,
              });
            }}
          >
            방향 유지 길이 적용
          </button>
        </>
      )}
    </form>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
