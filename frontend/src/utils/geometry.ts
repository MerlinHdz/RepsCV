type Point = {
  x: number;
  y: number;
};

export function calculateAngle(
  a: Point,
  b: Point,
  c: Point
): number {
  const abX = a.x - b.x;
  const abY = a.y - b.y;

  const cbX = c.x - b.x;
  const cbY = c.y - b.y;

  const dot = abX * cbX + abY * cbY;

  const magAB = Math.hypot(abX, abY);
  const magCB = Math.hypot(cbX, cbY);

  if (magAB === 0 || magCB === 0) {
    return NaN;
  }

  const cosine = Math.max(
    -1,
    Math.min(1, dot / (magAB * magCB))
  );

  return Math.acos(cosine) * (180 / Math.PI);
}