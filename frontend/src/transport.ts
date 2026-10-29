import { readDwg } from "./dwg";
import { SceneResponse } from "./scene-wire";
/** The server UI and static Pages UI share controls; static mode never uploads files. */
export const browserMode = import.meta.env.VITE_CAD_MODE === "browser";
let worker: Worker | undefined;
let nextId = 0;
const pending = new Map<
  number,
  { resolve: (r: Response) => void; reject: (e: Error) => void }
>();
function getWorker() {
  if (!worker) {
    const base = new URL(import.meta.env.BASE_URL, document.baseURI);
    const workerURL = new URL("cad-worker.js", base);
    workerURL.searchParams.set(
      "v",
      import.meta.env.VITE_CAD_REVISION ?? "dwg-fallback-1",
    );
    worker = new Worker(workerURL);
    worker.onmessage = ({ data }) => {
      const job = pending.get(data.id);
      if (!job) return;
      pending.delete(data.id);
      job.resolve(
        data.bytes
          ? new Response(data.bytes, { status: data.status })
          : new SceneResponse(data.jsonBytes ?? JSON.stringify(data.data), {
              status: data.status,
              headers: { "Content-Type": "application/json" },
            }),
      );
    };
    worker.onerror = () => {
      for (const p of pending.values())
        p.reject(
          new Error(
            "브라우저 도면 엔진을 시작하지 못했습니다. 새로고침해 주세요.",
          ),
        );
      pending.clear();
      worker?.terminate();
      worker = undefined;
    };
    // Preparation runs while the isolated DWG decoder is busy in its own worker.
    worker.postMessage({ warmup: true });
  }
  return worker;
}
export async function cadFetch(
  input: string,
  options: RequestInit = {},
): Promise<Response> {
  if (!browserMode) return fetch(input, options);
  const url = new URL(input, location.href);
  if (url.pathname === "/api/status")
    return Response.json({ oda_installed: false, mode: "browser" });
  const id = ++nextId;
  const file =
    options.body instanceof FormData ? options.body.get("file") : null;
  if (file instanceof File && file.size > 40 * 1024 * 1024)
    return Response.json(
      { detail: "파일 크기는 40MB 이하만 지원합니다." },
      { status: 413 },
    );
  if (file instanceof File && !/\.(dxf|dwg)$/i.test(file.name))
    return Response.json(
      {
        detail: "DWG 또는 DXF 파일을 선택하세요.",
      },
      { status: 422 },
    );
  let bytes = file instanceof File ? await file.arrayBuffer() : undefined;
  const isDwg =
    file instanceof File && file.name.toLowerCase().endsWith(".dwg");
  let database: Uint8Array | undefined;
  if (
    !isDwg ||
    (bytes &&
      bytes.byteLength >= 128 &&
      /^AC\d{4}$/.test(new TextDecoder("ascii").decode(bytes.slice(0, 6))))
  )
    getWorker();
  if (isDwg) {
    try {
      const decoded = await readDwg(bytes!);
      bytes = decoded.file;
      database = decoded.database;
    } catch (error) {
      return Response.json(
        {
          detail:
            ((error as Error).message.startsWith("DWG 열기 실패")
              ? (error as Error).message
              : "DWG 열기 실패: " + (error as Error).message) +
            `\n파일: ${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MiB · 헤더 ${new TextDecoder("ascii").decode(await file.slice(0, 6).arrayBuffer())}`,
        },
        { status: 422 },
      );
    }
  }
  const job = {
    id,
    path: database
      ? "/api/open-dwg-database"
      : isDwg
        ? "/api/open-dwg"
        : url.pathname,
    documentId: url.searchParams.get("document_id"),
    filename: file instanceof File ? file.name : undefined,
    file: bytes,
    databaseBytes: database,
    body: typeof options.body === "string" ? JSON.parse(options.body) : {},
  };
  const w = getWorker();
  return new Promise<Response>((resolve, reject) => {
    pending.set(id, { resolve, reject });
    w.postMessage(job, bytes ? [bytes] : database ? [database.buffer] : []);
  });
}
