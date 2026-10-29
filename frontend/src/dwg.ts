import {
  decodeWithFallback,
  DwgReadError,
  type DwgMode,
  type DwgResult,
} from "./dwg-retry";
/** Keep every attempt in its own worker; a trapped WASM module is never reused. */
function attempt(file: ArrayBuffer, mode: DwgMode): Promise<DwgResult> {
  return new Promise((resolve, reject) => {
    const w = new Worker(new URL("./dwg-reader.worker.ts", import.meta.url), {
      type: "module",
    });
    const finish = (error?: Error, result?: DwgResult) => {
      clearTimeout(timeout);
      w.terminate();
      error ? reject(error) : resolve(result!);
    };
    const timeout = setTimeout(
      () =>
        finish(new DwgReadError("DWG 해석 시간이 초과되었습니다.", "TIMEOUT")),
      120000,
    );
    w.onmessage = ({ data }) => {
      if (data.error) finish(new DwgReadError(data.error, data.code));
      else if (data.bytes instanceof Uint8Array)
        finish(undefined, { file: data.bytes.buffer as ArrayBuffer });
      else if (data.databaseBytes instanceof Uint8Array) {
        // Transfer the encoded database intact until Python consumes it.
        finish(undefined, { database: data.databaseBytes });
      } else finish(new DwgReadError("DWG 해석 결과를 읽지 못했습니다."));
    };
    w.onerror = () =>
      finish(
        new DwgReadError(
          "DWG 해석기를 실행하지 못했습니다. 최신 64비트 Chrome/Edge에서 다시 시도하세요.",
          "WORKER_ERROR",
        ),
      );
    w.postMessage({ file, mode }, [file]);
  });
}
export function readDwg(file: ArrayBuffer): Promise<DwgResult> {
  return decodeWithFallback(file, attempt);
}
