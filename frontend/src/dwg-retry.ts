export type DwgResult = { file?: ArrayBuffer; database?: Uint8Array };
export type DwgMode = "dxf" | "database";
export class DwgReadError extends Error {
  constructor(
    message: string,
    public readonly code: string = "DECODE_FAILED",
  ) {
    super(message);
  }
}
/** Retry once with a different API. Each attempt must own a fresh, disposable WASM heap. */
export async function decodeWithFallback(
  file: ArrayBuffer,
  attempt: (file: ArrayBuffer, mode: DwgMode) => Promise<DwgResult>,
): Promise<DwgResult> {
  const backup = file.slice(0);
  try {
    return await attempt(file, "dxf");
  } catch (error) {
    if (error instanceof DwgReadError && error.code === "INVALID_FILE")
      throw error;
    try {
      return await attempt(backup, "database");
    } catch (second) {
      throw new DwgReadError(
        "DWG 열기 실패: 일반 읽기와 대체 읽기에서 모두 해석하지 못했습니다. 해석기 호환성 문제일 수 있으며, 메모리 접근 오류가 파일 손상을 뜻하지는 않습니다.\n상세: " +
          (second instanceof Error ? second.message : String(second)),
        "BOTH_FAILED",
      );
    }
  }
}
