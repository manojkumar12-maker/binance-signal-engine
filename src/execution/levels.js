export function getLevels(entry, direction) {
  let sl, tp1, tp2, tp3;

  if (direction === "LONG") {
    sl = entry * 0.985;   // -1.5% SL
    tp1 = entry * 1.015;  // +1.5% TP1 (1R)
    tp2 = entry * 1.03;   // +3% TP2 (2R)
    tp3 = entry * 1.045;  // +4.5% TP3 (3R)
  } else {
    sl = entry * 1.015;   // +1.5% SL
    tp1 = entry * 0.985;  // -1.5% TP1 (1R)
    tp2 = entry * 0.97;   // -3% TP2 (2R)
    tp3 = entry * 0.955;  // -4.5% TP3 (3R)
  }

  return { sl, tp1, tp2, tp3 };
}
