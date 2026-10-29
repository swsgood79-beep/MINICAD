/** Keep the DWG interpreter in a separate short-lived worker, without network uploads. */
export function readDwg(file: ArrayBuffer): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const w = new Worker(new URL("./dwg-reader.worker.ts", import.meta.url), {
      type: "module",
    });
    // Bound a stalled/corrupt file instead of leaving controls disabled indefinitely.
    const timeout = setTimeout(
      () =>
        finish(
          new Error(
            "DWG 해석 시간이 초과되었습니다. 더 작은 파일이나 DXF를 사용해 주세요.",
          ),
        ),
      120000,
    );
    const finish = (error?: Error, bytes?: ArrayBuffer) => {
      clearTimeout(timeout);
      w.terminate();
      error ? reject(error) : resolve(bytes!);
    };
    w.onmessage = ({ data }) => {
      if (data.error) finish(new Error(data.error));
      else if (data.bytes instanceof Uint8Array)
        finish(undefined, data.bytes.buffer as ArrayBuffer);
      else finish(new Error("DWG 해석 결과를 읽지 못했습니다."));
    };
    w.onerror = () =>
      finish(
        new Error(
          "DWG 해석기를 실행하지 못했습니다. 최신 64비트 Chrome/Edge에서 다시 시도하세요.",
        ),
      );
    w.postMessage({ file }, [file]);
  });
}
