import { config } from '../core/config.js';

let balance = 10000;

export function setBalance(amount) {
  balance = amount;
}

export function getBalance() {
  return balance;
}

export function calculatePositionSize(riskPercent = config.RISK_PERCENT, stopLossPercent = config.STOP_LOSS_PERCENT) {
  const riskAmount = balance * (riskPercent / 100);
  return riskAmount / stopLossPercent;
}

export function calculateRisk(entry, stopLoss) {
  if (!entry || !stopLoss) return 0;
  return Math.abs(entry - stopLoss) / entry * 100;
}

export function checkRisk(symbol, entry, stopLoss, size) {
  const risk = calculateRisk(entry, stopLoss);
  const positionValue = entry * size;
  const riskAmount = positionValue * (risk / 100);
  const riskOfBalance = (riskAmount / balance) * 100;
  
  return {
    risk,
    riskAmount,
    riskOfBalance,
    withinLimits: riskOfBalance <= config.RISK_PERCENT * 2
  };
}
