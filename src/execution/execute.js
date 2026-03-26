import { calculatePositionSize } from "./risk.js";
import { getLevels } from "./levels.js";
import { placeOrder } from "./binance.js";

export async function executeTrade(symbol, signalType, price, balance = 1000) {
  const direction = "LONG"; // Default for pump sniper

  const { sl, tp1, tp2, tp3 } = getLevels(price, direction);

  const size = calculatePositionSize({
    balance,
    riskPercent: 1, // 1% risk per trade
    entry: price,
    stopLoss: sl
  });

  const trade = {
    symbol,
    direction,
    entry: price,
    sl,
    tp1,
    tp2,
    tp3,
    size
  };

  console.log(`🚀 SIMULATED EXECUTION TRADE: ${signalType} for ${symbol} | Entry: ${trade.entry} | SL: ${trade.sl} | Size: ${trade.size.toFixed(4)}`);
  
  // Optionally route to live Binance execution logic if configured:
  // await placeOrder(trade);

  return trade;
}
