/**
 * Unified Signal Pipeline
 *
 * Combines two independent signal sources:
 *   1. SMC Engine  — D1+H4+M15 structure-based entries (patient, high R:R)
 *   2. Pump Engine — Real-time OI/volume/orderflow momentum (fast, reactive)
 *
 * A CONFLUENCE signal fires when BOTH engines agree on the same direction.
 * Each engine also fires its own signals independently.
 *
 * Priority: CONFLUENCE > SMC > PUMP
 */

import { analyzeSMC } from './smcEngine.js';
import {
  processSymbol as pumpProcess,
  calculateAdaptiveScore
} from './signalPipeline.js';

// Per-symbol cooldowns to avoid spam (ms)
const COOLDOWN = {
  CONFLUENCE: 5  * 60_000,
  SMC:        3  * 60_000,
  PUMP:       2  * 60_000,
};

const lastFired    = new Map();
const smcRunning   = new Set();

function canFire(symbol, type) {
  const key   = `${symbol}:${type}`;
  const last  = lastFired.get(key) || 0;
  return Date.now() - last > (COOLDOWN[type] || 120_000);
}

function markFired(symbol, type) {
  lastFired.set(`${symbol}:${type}`, Date.now());
}

// ── Format TP/SL block ───────────────────────────────────────

function formatTPSL(tpsl, precision = 6) {
  if (!tpsl) return '';
  const p = (v) => v?.toFixed(precision) ?? 'N/A';
  return [
    `💰 Entry : ${p(tpsl.entry)}`,
    `🛑 SL    : ${p(tpsl.sl)} (-${tpsl.slPercent}%)`,
    ``,
    `🎯 TP1   : ${p(tpsl.tp1)}  [${tpsl.rr1?.toFixed(1)}R] → ${tpsl.partialExit.tp1}`,
    `🎯 TP2   : ${p(tpsl.tp2)}  [${tpsl.rr2?.toFixed(1)}R] → ${tpsl.partialExit.tp2}`,
    `🎯 TP3   : ${p(tpsl.tp3)}  [${tpsl.rr3?.toFixed(1)}R] → ${tpsl.partialExit.tp3}`,
    `🎯 TP4   : ${p(tpsl.tp4)}  [4.0R] → ${tpsl.partialExit.tp4}`,
    `🎯 TP5   : ${p(tpsl.tp5)}  [5.0R] → ${tpsl.partialExit.tp5}`,
  ].join('\n');
}

// ── Telegram message builders ────────────────────────────────

export function buildSMCMessage(symbol, smc) {
  const { signal, confidence, confluence, d1, h4, m15, tpsl } = smc;
  const dir  = signal === 'BUY' ? '🟢 LONG' : '🔴 SHORT';
  const sess = m15.session?.session || 'UNKNOWN';

  return `
━━━━━━━━━━━━━━━━━━━━━━━
📐 SMC SIGNAL — ${dir}
━━━━━━━━━━━━━━━━━━━━━━━
📊 ${symbol}
🕐 Session : ${sess} ${m15.session?.isActive ? '✅' : '⚠️ Off-session'}
🎯 Confluence: ${'⭐'.repeat(confluence)} (${confluence}/5)
💪 Confidence: ${confidence}%

🔍 TIMEFRAME ANALYSIS:
  D1 Bias  : ${d1.bias}  (bullScore ${d1.bullScore}/6)
  H4 Zone  : ${h4.zone}  (rsi ${h4.rsi?.toFixed(0)})
  M15 BOS  : ${m15.bos?.bull || m15.bos?.bear ? '✅' : '❌'}
  M15 CHoCH: ${m15.choch?.bull || m15.choch?.bear ? '✅' : '❌'}
  MACD     : ${m15.macd?.bull ? 'Bullish' : 'Bearish'}
  RSI      : ${m15.rsi?.toFixed(1)}
  Sweep    : ${m15.sweep?.swept ? '✅ Liquidity swept' : '—'}

📐 LEVELS:
${formatTPSL(tpsl, getPrecision(tpsl?.entry))}

💡 ${m15.reason}
━━━━━━━━━━━━━━━━━━━━━━━`;
}

export function buildPumpMessage(symbol, pump) {
  const dir = pump.direction === 'LONG' ? '🟢 LONG' : '🔴 SHORT';
  const d   = pump.data || {};

  return `
━━━━━━━━━━━━━━━━━━━━━━━
⚡ PUMP SIGNAL — ${dir}
━━━━━━━━━━━━━━━━━━━━━━━
📊 ${symbol}  [${pump.type}]
💪 Score: ${pump.confidence}/100

📈 METRICS:
  Volume   : ${d.volume?.toFixed(1)}x
  OrderFlow: ${d.orderFlow?.toFixed(2)}
  OI Change: ${d.oiChange?.toFixed(2)}%
  Momentum : ${d.momentum?.toFixed(4)}

📐 LEVELS:
💰 Entry : ${pump.entry?.toFixed(getPrecision(pump.entry))}
🛑 SL    : ${pump.stopLoss?.toFixed(getPrecision(pump.entry))}
🎯 TP1   : ${pump.tp1?.toFixed(getPrecision(pump.entry))}
🎯 TP2   : ${pump.tp2?.toFixed(getPrecision(pump.entry))}
🎯 TP3   : ${pump.tp3?.toFixed(getPrecision(pump.entry))}
━━━━━━━━━━━━━━━━━━━━━━━`;
}

export function buildConfluenceMessage(symbol, smc, pump) {
  const dir   = smc.signal === 'BUY' ? '🟢 LONG' : '🔴 SHORT';
  const tpsl  = smc.tpsl;
  const prec  = getPrecision(tpsl?.entry);

  return `
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
🏆 CONFLUENCE SIGNAL — ${dir}
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
📊 ${symbol}
🎯 SMC Confluence : ${'⭐'.repeat(smc.confluence)} (${smc.confluence}/5)
💪 SMC Confidence : ${smc.confidence}%
⚡ Pump Score     : ${pump.confidence}/100

🔍 D1 → H4 → M15 ALIGNED:
  D1 Bias  : ${smc.d1.bias}
  H4 Zone  : ${smc.h4.zone}
  M15 BOS  : ${smc.m15.bos?.bull || smc.m15.bos?.bear ? '✅' : '❌'}
  M15 CHoCH: ${smc.m15.choch?.bull || smc.m15.choch?.bear ? '✅' : '❌'}
  Session  : ${smc.m15.session?.session} ${smc.m15.session?.isActive ? '✅' : '⚠️'}
  Vol Spike: ${pump.data?.volume?.toFixed(1)}x
  OI Change: ${pump.data?.oiChange?.toFixed(2)}%

📐 LEVELS (SMC-calibrated):
${formatTPSL(tpsl, prec)}
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥`;
}

// ── Decimal precision based on price ────────────────────────

function getPrecision(price) {
  if (!price || price === 0) return 6;
  if (price >= 10000) return 2;
  if (price >= 1000)  return 3;
  if (price >= 100)   return 4;
  if (price >= 1)     return 5;
  return 6;
}

// ── Main unified processor ───────────────────────────────────

export async function processUnified(symbol, pumpMarketData, onSignal) {
  // ── 1. Pump engine (synchronous, already computed by caller)
  const pumpResult = pumpMarketData
    ? pumpProcess(symbol, pumpMarketData)
    : null;

  const isPumpSignal = pumpResult && ['SNIPER', 'HIGH_PUMP'].includes(pumpResult.type);

  // ── 2. SMC engine (async, throttled — skip if already running)
  if (smcRunning.has(symbol)) return null;

  smcRunning.add(symbol);
  let smcResult = null;

  try {
    smcResult = await analyzeSMC(symbol);
  } catch {
    // Non-fatal — SMC analysis failure doesn't block pump signals
  } finally {
    smcRunning.delete(symbol);
  }

  const isSMCSignal = smcResult?.signal && smcResult.confluence >= 3 && smcResult.confidence >= 65;

  // ── 3. Determine output ─────────────────────────────────────

  // CONFLUENCE: both agree on direction
  if (isPumpSignal && isSMCSignal) {
    const pumpDir = pumpResult.direction;
    const smcDir  = smcResult.signal;
    const aligned =
      (pumpDir === 'LONG' && smcDir === 'BUY') ||
      (pumpDir === 'SHORT' && smcDir === 'SELL');

    if (aligned && canFire(symbol, 'CONFLUENCE')) {
      markFired(symbol, 'CONFLUENCE');
      markFired(symbol, 'SMC');
      markFired(symbol, 'PUMP');
      const msg = buildConfluenceMessage(symbol, smcResult, pumpResult);
      onSignal?.({ type: 'CONFLUENCE', symbol, smc: smcResult, pump: pumpResult, message: msg });
      return { type: 'CONFLUENCE', symbol, smc: smcResult, pump: pumpResult };
    }
  }

  // SMC-only
  if (isSMCSignal && canFire(symbol, 'SMC')) {
    markFired(symbol, 'SMC');
    const msg = buildSMCMessage(symbol, smcResult);
    onSignal?.({ type: 'SMC', symbol, smc: smcResult, message: msg });
    return { type: 'SMC', symbol, smc: smcResult };
  }

  // Pump-only
  if (isPumpSignal && canFire(symbol, 'PUMP')) {
    markFired(symbol, 'PUMP');
    const msg = buildPumpMessage(symbol, pumpResult);
    onSignal?.({ type: 'PUMP', symbol, pump: pumpResult, message: msg });
    return { type: 'PUMP', symbol, pump: pumpResult };
  }

  return null;
}

// ── Batch SMC scan (top symbols) ────────────────────────────

export async function batchSMCScan(symbols, onSignal, maxConcurrent = 5) {
  const results = [];

  for (let i = 0; i < symbols.length; i += maxConcurrent) {
    const batch  = symbols.slice(i, i + maxConcurrent);
    const settled = await Promise.allSettled(
      batch.map(sym => analyzeSMC(sym).then(smc => {
        if (smc?.signal && smc.confluence >= 3 && smc.confidence >= 65) {
          const msg = buildSMCMessage(sym, smc);
          onSignal?.({ type: 'SMC', symbol: sym, smc, message: msg });
          results.push({ symbol: sym, smc });
        }
      }))
    );
    // Small pause between batches to avoid rate limiting
    if (i + maxConcurrent < symbols.length) {
      await new Promise(r => setTimeout(r, 300));
    }
  }

  return results;
}
