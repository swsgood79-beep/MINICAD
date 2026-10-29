import type { Entity, Point } from "./geometry";

type Matrix = [number, number, number, number, number, number];
type Instance = { $block: string; matrix: Matrix };
type WireEntity = Omit<Entity, "segments"> & {
  segments?: (WireEntity | Instance)[];
};
type WireDrawing = {
  entities: WireEntity[];
  blockPictures: Record<string, Entity[]>;
};

/** Expand reusable block pictures in native JS, retaining Float64 coordinates. */
export function expandBlocks<T>(value: T): T {
  if (!value || typeof value !== "object" || !("blockPictures" in value))
    return value;
  const data = value as unknown as WireDrawing;
  if (
    !Array.isArray(data.entities) ||
    !data.blockPictures ||
    typeof data.blockPictures !== "object"
  )
    throw new Error("도면 블록 데이터를 읽지 못했습니다.");
  let count = 0;
  const consume = () => {
    if (++count > 2000000)
      throw new Error("도면 표시 요소 한도를 초과했습니다.");
  };
  const multiply = (p: Matrix, q: Matrix): Matrix => [
    p[0] * q[0] + p[2] * q[1],
    p[1] * q[0] + p[3] * q[1],
    p[0] * q[2] + p[2] * q[3],
    p[1] * q[2] + p[3] * q[3],
    p[0] * q[4] + p[2] * q[5] + p[4],
    p[1] * q[4] + p[3] * q[5] + p[5],
  ];
  const transform = (
    item: WireEntity,
    m: Matrix,
    active: Set<string>,
    depth: number,
  ): Entity => {
    consume();
    const [a, b, c, d, tx, ty] = m;
    const xy = (p: Point): Point => {
      const q: Point = [a * p[0] + c * p[1] + tx, b * p[0] + d * p[1] + ty];
      if (!q.every((n) => Number.isFinite(n) && Math.abs(n) < 1e12))
        throw new Error("도면 좌표 범위를 초과했습니다.");
      return q;
    };
    const angle = (degrees: number) => {
      const r = (degrees * Math.PI) / 180,
        x = Math.cos(r),
        y = Math.sin(r);
      return (
        ((Math.atan2(b * x + d * y, a * x + c * y) * 180) / Math.PI + 360) % 360
      );
    };
    // Virtual children have no editable handle; selection retains the root ID.
    const result = { ...item, id: null as unknown as string } as Entity;
    if (item.a) result.a = xy(item.a);
    if (item.b) result.b = xy(item.b);
    if (item.c) result.c = xy(item.c);
    const scale = Math.hypot(a, b);
    if (item.r !== undefined) result.r = item.r * scale;
    if (item.type === "ARC") {
      const start = angle(item.start!),
        end = angle(item.end!);
      [result.start, result.end] =
        a * d - b * c < 0 ? [end, start] : [start, end];
    }
    if (item.type === "TEXT" || item.type === "MTEXT") {
      result.rotation = angle(item.rotation ?? 0);
      result.height = (item.height ?? 1) * scale;
    }
    if (item.pts) result.pts = item.pts.map(xy);
    if (item.segments)
      result.segments = expand(item.segments, m, active, depth + 1);
    return result;
  };
  const expand = (
    items: (WireEntity | Instance)[],
    parent?: Matrix,
    active = new Set<string>(),
    depth = 0,
  ): Entity[] => {
    if (depth > 64) throw new Error("도면 블록 중첩 한도를 초과했습니다.");
    return items.flatMap((item) => {
      if ("$block" in item) {
        if (
          !Object.hasOwn(data.blockPictures, item.$block) ||
          !Array.isArray(data.blockPictures[item.$block]) ||
          !Array.isArray(item.matrix) ||
          item.matrix.length !== 6 ||
          !item.matrix.every(Number.isFinite) ||
          active.has(item.$block)
        )
          throw new Error("도면 블록 참조가 올바르지 않습니다.");
        return expand(
          data.blockPictures[item.$block],
          parent ? multiply(parent, item.matrix) : item.matrix,
          new Set([...active, item.$block]),
          depth + 1,
        );
      }
      if (parent) return [transform(item, parent, active, depth)];
      consume();
      return [
        {
          ...item,
          ...(item.segments
            ? { segments: expand(item.segments, undefined, active, depth + 1) }
            : {}),
        } as Entity,
      ];
    });
  };
  const { blockPictures: _pictures, ...rest } = data;
  return { ...rest, entities: expand(data.entities) } as T;
}

/** The browser transport keeps its Response interface; only JSON scene decoding differs. */
export class SceneResponse extends Response {
  override async json() {
    return expandBlocks(await super.json());
  }
  override clone(): SceneResponse {
    const copy = super.clone();
    return new SceneResponse(copy.body, {
      status: copy.status,
      statusText: copy.statusText,
      headers: copy.headers,
    });
  }
}
