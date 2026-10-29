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
    worker = new Worker(new URL("cad-worker.js", base));
    worker.onmessage = ({ data }) => {
      const job = pending.get(data.id);
      if (!job) return;
      pending.delete(data.id);
      job.resolve(
        data.bytes
          ? new Response(data.bytes, { status: data.status })
          : new Response(JSON.stringify(data.data), {
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
  if (file instanceof File && !file.name.toLowerCase().endsWith(".dxf"))
    return Response.json(
      {
        detail:
          "무료 브라우저 버전은 DXF 전용입니다. DWG는 DXF로 변환한 뒤 열어주세요.",
      },
      { status: 422 },
    );
  const bytes = file instanceof File ? await file.arrayBuffer() : undefined;
  const job = {
    id,
    path: url.pathname,
    documentId: url.searchParams.get("document_id"),
    filename: file instanceof File ? file.name : undefined,
    file: bytes,
    body: typeof options.body === "string" ? JSON.parse(options.body) : {},
  };
  const w = getWorker();
  return new Promise<Response>((resolve, reject) => {
    pending.set(id, { resolve, reject });
    w.postMessage(job, bytes ? [bytes] : []);
  });
}
