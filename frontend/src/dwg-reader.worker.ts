// SPDX-License-Identifier: GPL-3.0-or-later
// Isolated DWG interpreter. Corresponding library source and license: /third-party/.
import {
  LibreDwg,
  Dwg_Error,
  Dwg_Object_Type,
  type DwgEntity,
  type DwgDatabase,
} from "@mlightcad/libredwg-web";
const fields = [
  "type",
  "handle",
  "layer",
  "isVisible",
  "isInPaperSpace",
  "colorIndex",
  "color",
  "startPoint",
  "endPoint",
  "center",
  "radius",
  "startAngle",
  "endAngle",
  "position",
  "vertices",
  "flag",
  "elevation",
  "extrusionDirection",
  "text",
  "textHeight",
  "rotation",
  "insertionPoint",
  "xScale",
  "yScale",
  "zScale",
  "rowCount",
  "columnCount",
  "name",
  "definitionPoint",
  "dimensionType",
  "textPoint",
  "direction",
  "controlPoints",
  "fitPoints",
  "knots",
  "weights",
  "degree",
  "majorAxisEndPoint",
  "axisRatio",
  "corner1",
  "corner2",
  "corner3",
  "corner4",
  "isSpline",
];
function compact(e: DwgEntity) {
  const source = e as unknown as Record<string, unknown>,
    result: Record<string, unknown> = {};
  for (const key of fields) if (key in source) result[key] = source[key];
  return result;
}
function referencedBlocks(db: DwgDatabase) {
  const blocks = new Map(
    db.tables.BLOCK_RECORD.entries
      .filter((b) => !/^\*(MODEL_SPACE|PAPER_SPACE)/i.test(b.name))
      .map((b) => [b.name.toLowerCase(), b]),
  );
  const names = (entities: DwgEntity[]) =>
    entities.flatMap((e) => {
      const name = (e as unknown as { name?: string }).name;
      return (e.type === "INSERT" || e.type === "DIMENSION") &&
        typeof name === "string"
        ? [name.toLowerCase()]
        : [];
    });
  const pending = names(db.entities),
    seen = new Set<string>();
  while (pending.length) {
    const name = pending.pop()!;
    if (seen.has(name) || !blocks.has(name)) continue;
    seen.add(name);
    for (const child of names(blocks.get(name)!.entities))
      if (!seen.has(child)) pending.push(child);
  }
  return [...seen].map((name) => blocks.get(name)!);
}
self.onmessage = async ({
  data,
}: {
  data: { file: ArrayBuffer; mode?: "dxf" | "database" };
}) => {
  let stage = "signature";
  try {
    const signature = new TextDecoder("ascii").decode(data.file.slice(0, 6));
    if (!/^AC\d{4}$/.test(signature) || data.file.byteLength < 128) {
      (self as unknown as Worker).postMessage({
        code: "INVALID_FILE",
        error: "DWG 파일 형식이 아니거나 파일이 손상되었습니다.",
      });
      return;
    }
    stage = "initialize";
    const reader = await LibreDwg.create();
    if (data.mode === "database") {
      stage = "decode";
      reader.FS.writeFile("input.dwg", new Uint8Array(data.file));
      const parsed = reader.dwg_read_file("input.dwg");
      const fatal =
        Dwg_Error.INVALIDDWG |
        Dwg_Error.OUTOFMEM |
        Dwg_Error.IOERROR |
        Dwg_Error.INTERNALERROR |
        Dwg_Error.SECTIONNOTFOUND |
        Dwg_Error.PAGENOTFOUND |
        Dwg_Error.CLASSESNOTFOUND;
      if (!parsed.data || parsed.error & fatal)
        throw Error(
          "해석기가 이 DWG를 지원하지 않습니다. 코드 " + parsed.error,
        );
      stage = "database";
      const { database: db, stats } = reader.convertEx(parsed.data);
      // Upstream 0.8.2 asks for the misspelled 'plotflockedlag' and reports every layer locked.
      // Read the actual 'locked' bit, matched by handle; never guess an unknown state is unlocked.
      const layers = new Map(
        db.tables.LAYER.entries.map((layer) => [
          layer.handle.toUpperCase(),
          layer,
        ]),
      );
      for (const ptr of reader.dwg_getall_LAYER(parsed.data)) {
        const object = reader.dwg_obj_generic_to_object(ptr);
        const handle = reader
          .dwg_obj_get_handle_value(object)
          ?.toString(16)
          .toUpperCase();
        const layer = handle ? layers.get(handle) : undefined;
        const locked = reader.dwg_dynapi_entity_data(ptr, "locked");
        if (
          layer &&
          (locked === 0 || locked === 1 || typeof locked === "boolean")
        )
          layer.locked = Boolean(locked);
      }
      // convertEx 0.8.2 copies clone_ins_pt only for aligned dimensions. All
      // dimension variants use it to translate their anonymous picture block.
      // Losing it displaces dimensions inside copied/nested blocks a second time.
      const clonePoints = new Map<string, unknown>();
      for (const [name, type] of Object.entries(Dwg_Object_Type)) {
        if (!name.startsWith("DWG_TYPE_DIMENSION_") || typeof type !== "number")
          continue;
        for (const ptr of reader.dwg_getall_entity_by_type(parsed.data, type)) {
          const object = reader.dwg_obj_generic_to_object(ptr);
          const handle = reader
            .dwg_obj_get_handle_value(object)
            ?.toString(16)
            .toUpperCase();
          const point = reader.dwg_dynapi_entity_data(ptr, "clone_ins_pt") as
            | { x?: number; y?: number }
            | undefined;
          if (
            handle &&
            point &&
            Number.isFinite(point.x) &&
            Number.isFinite(point.y)
          )
            clonePoints.set(handle, point);
        }
      }
      const restoreDimensions = (entities: DwgEntity[]) => {
        for (const entity of entities) {
          const point = clonePoints.get(entity.handle.toUpperCase());
          if (entity.type === "DIMENSION" && point)
            (entity as unknown as Record<string, unknown>).insertionPoint =
              point;
        }
      };
      restoreDimensions(db.entities);
      for (const block of db.tables.BLOCK_RECORD.entries)
        restoreDimensions(block.entities);
      const databaseJSON = JSON.stringify(
        {
          header: { INSUNITS: db.header.INSUNITS },
          entities: db.entities.map(compact),
          tables: {
            LAYER: db.tables.LAYER,
            BLOCK_RECORD: {
              entries: referencedBlocks(db).map((b) => ({
                name: b.name,
                basePoint: b.basePoint,
                entities: b.entities.map(compact),
              })),
            },
          },
          decoderErrors: parsed.error,
          unknownEntityCount: stats.unknownEntityCount,
        },
        (_key, value) => (typeof value === "bigint" ? value.toString() : value),
      );
      // Do not reuse or free an uncertain decoder heap: the owner terminates this worker.
      (self as unknown as Worker).postMessage({ databaseJSON });
    } else {
      stage = "dxf";
      const bytes = reader.dwg_write_dxf(data.file);
      if (!bytes?.length) throw Error("DWG 내부 변환에 실패했습니다.");
      (self as unknown as Worker).postMessage({ bytes }, [
        bytes.buffer as ArrayBuffer,
      ]);
    }
  } catch (error) {
    (self as unknown as Worker).postMessage({
      code:
        error instanceof WebAssembly.RuntimeError
          ? "WASM_TRAP"
          : "DECODE_FAILED",
      stage,
      error: String(error instanceof Error ? error.message : error),
    });
  }
};
