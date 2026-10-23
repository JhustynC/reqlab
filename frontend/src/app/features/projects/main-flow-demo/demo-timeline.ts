export const DEMO_STEPS = [
  { name: 'Fuentes', caption: 'Prepara el contexto', dur: 7.5 },
  { name: 'Definición', caption: 'Aclara el alcance', dur: 5.5 },
  { name: 'Generación', caption: 'Construye propuestas', dur: 5 },
  { name: 'Revisión', caption: 'Revisa la evidencia', dur: 7 },
  { name: 'Exportación', caption: 'Comparte resultados', dur: 5 },
] as const;

// Seconds within each step. Actions begin 120 ms after the pointer presses.
export const SOURCE = {
  choose: 1.1,
  picker: 1.22,
  select: 2.4,
  selected: 2.52,
  open: 3.6,
  attached: 3.72,
  click: 5,
  work: 5.12,
  done: 6.3,
};
export const DEFINITION = { click: 1.2, work: 1.32, done: 2.9, confirm: 4.28, saved: 4.4 };
export const GENERATION = { click: 1.3, work: 1.42, done: 3.9 };
export const REVIEW = {
  click: 1.2,
  open: 1.32,
  approve: 3.6,
  dialog: 3.72,
  confirm: 5.2,
  saved: 5.32,
};
export const EXPORT = { select: 1.2, selected: 1.32, click: 3, work: 3.12, done: 3.75 };

export const TOTAL = DEMO_STEPS.reduce((sum, step) => sum + step.dur, 0);
export const clamp = (n: number) => Math.min(1, Math.max(0, n));
export function ease(t: number, from: number, to: number): number {
  const x = clamp((t - from) / (to - from));
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

export function frameAt(elapsed: number) {
  let t = Math.max(0, Math.min(TOTAL, elapsed));
  for (let i = 0; i < DEMO_STEPS.length; i++) {
    if (t < DEMO_STEPS[i].dur || i === DEMO_STEPS.length - 1) return { i, t };
    t -= DEMO_STEPS[i].dur;
  }
  return { i: 0, t: 0 };
}

export interface Point {
  x: number;
  y: number;
}
export interface Move {
  from: number;
  to: number;
  point: Point;
}
export function glide(t: number, moves: Move[], clicks: number[]) {
  let point: Point = { x: 1090, y: 650 };
  for (const move of moves) {
    if (t < move.from) break;
    const progress = ease(t, move.from, move.to);
    point = {
      x: point.x + (move.point.x - point.x) * progress,
      y: point.y + (move.point.y - point.y) * progress,
    };
    if (t < move.to) break;
  }
  return { ...point, press: clicks.some((at) => t >= at && t < at + 0.17) };
}
