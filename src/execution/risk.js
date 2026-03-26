export function calculatePositionSize({ balance, riskPercent, entry, stopLoss }) {
  if (entry === stopLoss || !entry || !stopLoss) return 0;
  
  const riskAmount = balance * (riskPercent / 100);
  const stopDistance = Math.abs(entry - stopLoss);
  
  const size = riskAmount / stopDistance;
  return size;
}
