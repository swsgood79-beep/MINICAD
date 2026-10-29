import { type Entity, fit, toScreen, paths, sweep, arcPoint } from "./geometry";
export const escapeXml = (s: string) =>
  s.replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&apos;",
      })[c]!,
  );
/** Vector-only, white-paper drawing; no UI, grid, hidden layers or selection highlights. */
export function drawingSvg(
  entities: Entity[],
  width = 1100,
  height = 700,
): string {
  const view = fit(entities, width, height);
  const render = (e: Entity): string => {
    if (e.segments) return e.segments.map(render).join("");
    if (e.type === "CIRCLE") {
      const p = toScreen(e.c!, view);
      return `<circle cx="${p[0]}" cy="${p[1]}" r="${e.r! * view.scale}"/>`;
    }
    if (e.type === "ARC") {
      const [a, b] = sweep(e),
        p = toScreen(arcPoint(e, a), view),
        q = toScreen(arcPoint(e, b), view);
      return `<path d="M ${p.join(" ")} A ${e.r! * view.scale} ${e.r! * view.scale} 0 ${b - a > Math.PI ? 1 : 0} 0 ${q.join(" ")}"/>`;
    }
    if (e.type === "TEXT" || e.type === "MTEXT") {
      const p = toScreen(e.c!, view),
        h = Math.max(1, (e.height ?? 1) * view.scale);
      return `<text transform="translate(${p.join(" ")}) rotate(${-(e.rotation ?? 0)})" font-family="sans-serif" font-size="${h}" stroke="none" fill="black">${(
        e.text ?? ""
      )
        .split("\n")
        .map(
          (line, i) =>
            `<tspan x="0" y="${i * h * 1.3}">${escapeXml(line)}</tspan>`,
        )
        .join("")}</text>`;
    }
    return paths(e)
      .map((path) =>
        path.length === 1
          ? `<circle cx="${toScreen(path[0], view)[0]}" cy="${toScreen(path[0], view)[1]}" r="1.5" fill="black"/>`
          : `<polyline points="${path.map((p) => toScreen(p, view).join(",")).join(" ")}"/>`,
      )
      .join("");
  };
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="인쇄 도면"><g fill="none" stroke="black" stroke-width="1">${entities.map(render).join("")}</g></svg>`;
}
export function printDrawing(
  entities: Entity[],
  filename: string,
  measurement: string,
  unit: string,
  warnings: string[],
) {
  document.querySelector("iframe[data-minicad-print]")?.remove();
  const frame = document.createElement("iframe");
  frame.title = "도면 인쇄";
  frame.dataset.minicadPrint = "true";
  Object.assign(frame.style, {
    position: "fixed",
    width: "1px",
    height: "1px",
    opacity: "0",
    pointerEvents: "none",
    border: "0",
  });
  document.body.append(frame);
  const doc = frame.contentDocument!;
  doc.open();
  doc.write(
    `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>${escapeXml(filename)} — 도면 인쇄</title><style>@page{size:A4 landscape;margin:12mm}body{font:12px sans-serif;color:black;margin:0;height:182mm;display:flex;flex-direction:column}h1{font-size:16px;margin:0 0 6px;overflow-wrap:anywhere}main{flex:1;min-height:0}svg{display:block;width:100%;height:100%}header,footer{flex:0 0 auto}p{margin:6px 0}.warning{font-size:10px}header,footer{break-inside:avoid}</style></head><body><header><h1>${escapeXml(filename)}</h1><p>단위: ${escapeXml(unit)} · 최근 측정: ${escapeXml(measurement)}</p></header><main>${drawingSvg(entities)}</main><footer><p>표시 중인 레이어 전체를 용지에 맞춤 · 실제 축척 인쇄가 아닙니다.</p>${warnings.map((w) => `<p class="warning">${escapeXml(w)}</p>`).join("")}</footer></body></html>`,
  );
  doc.close();
  // Keep the frame until the next print so the native print preview retains its contents.
  setTimeout(() => {
    frame.contentWindow!.focus();
    frame.contentWindow!.print();
  }, 100);
}
