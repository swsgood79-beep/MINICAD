// SPDX-License-Identifier: GPL-3.0-or-later
// Isolated DWG interpreter. Corresponding library source and license: /third-party/.
import { LibreDwg } from "@mlightcad/libredwg-web";
self.onmessage = async ({ data }: { data: { file: ArrayBuffer } }) => {
  try {
    const signature = new TextDecoder("ascii").decode(data.file.slice(0, 6));
    if (!/^AC\d{4}$/.test(signature) || data.file.byteLength < 128)
      throw new Error("DWG 파일 형식이 아니거나 파일이 손상되었습니다.");
    const reader = await LibreDwg.create();
    const bytes = reader.dwg_write_dxf(data.file);
    if (!bytes?.length)
      throw new Error(
        "이 DWG의 버전 또는 객체를 해석하지 못했습니다. DXF로 내보낸 파일을 사용해 주세요.",
      );
    (self as unknown as Worker).postMessage({ bytes }, [
      bytes.buffer as ArrayBuffer,
    ]);
  } catch (error) {
    (self as unknown as Worker).postMessage({
      error:
        "DWG 열기 실패: " +
        String(error instanceof Error ? error.message : error),
    });
  }
};
