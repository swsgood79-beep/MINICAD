import { test } from "node:test";
import assert from "node:assert/strict";
import { decodeWithFallback, DwgReadError } from "./dwg-retry";
test("successful standard read does not retry", async () => {
  const calls: string[] = [];
  const r = await decodeWithFallback(new ArrayBuffer(4), async (file, mode) => {
    calls.push(mode);
    return { file };
  });
  assert.deepEqual(calls, ["dxf"]);
  assert.equal(r.file?.byteLength, 4);
});
test("WASM trap retries once using an intact copy after transfer", async () => {
  const input = new Uint8Array([1, 2, 3, 4]).buffer;
  const calls: string[] = [];
  const r = await decodeWithFallback(input, async (file, mode) => {
    calls.push(mode);
    if (mode === "dxf") {
      structuredClone(file, { transfer: [file] });
      assert.equal(file.byteLength, 0);
      throw new DwgReadError("memory access out of bounds", "WASM_TRAP");
    }
    assert.deepEqual(Array.from(new Uint8Array(file)), [1, 2, 3, 4]);
    return {
      database: new TextEncoder().encode(JSON.stringify({ entities: [] })),
    };
  });
  assert.deepEqual(calls, ["dxf", "database"]);
  assert.ok(r.database);
});
test("wrong file signature fails without a second decoder attempt", async () => {
  let n = 0;
  await assert.rejects(
    () =>
      decodeWithFallback(new ArrayBuffer(4), async () => {
        n++;
        throw new DwgReadError("not DWG", "INVALID_FILE");
      }),
    /not DWG/,
  );
  assert.equal(n, 1);
});
test("both failures are bounded and explain compatibility instead of claiming damaged file", async () => {
  let n = 0;
  await assert.rejects(
    () =>
      decodeWithFallback(new ArrayBuffer(4), async () => {
        n++;
        throw new DwgReadError("memory access out of bounds", "WASM_TRAP");
      }),
    /호환성 문제/,
  );
  assert.equal(n, 2);
});
