export function getLevels(entry, direction) {
  let sl, tp1, tp2, tp3;

  if (direction === "LONG") {
    sl = entry * 0.995;   // -0.5%
    tp1 = entry * 1.01;    // +1%
    tp2 = entry * 1.02;    // +2%
    tp3 = entry * 1.03;    // +3%
  } else {
    sl = entry * 1.005;
    tp1 = entry * 0.99;
    tp2 = entry * 0.98;
    tp3 = entry * 0.97;
  }

  return { sl, tp1, tp2, tp3 };
}
