/**
 * Signal Engine — Main Entry
 *
 * Architecture:
 *   WebSocket ticker/trade streams → Pump Analyzer → Unified Pipeline
 *                                                  ↘ SMC Engine (async, per-symbol)
 *
 * Signal priority: CONFLUENCE > SMC > PUMP
 */

import { wsManager }        from './websocket/binanceWS.js';
import { pumpAnalyzer }     from './analyzer/pumpAnalyzer.js';
import { orderBookAnalyzer }from './engine/orderBookAnalyzer.js';
import { marketDataTracker }from './engine/marketDataTracker.js';
import { orderflowTracker } from './engine/orderflowTracker.js';
import { oiTracker }        from './engine/oiTracker.js';
import { setOITracker, updateBTCPrice } from './engine/signalPipeline.js';
import { processUnified, batchSMCScan } from './engine/unifiedPipeline.js';
import { sendTelegram, sendSignal, sendStartup, sendDailySummary } from './utils/telegram.js';
import { initDatabase }     from './database/db.js';
import { addSignal, addToActive } from './state.js';

const stats = { confluence: 0, smc: 0, pump: 0, topSymbols: [] };
const signalSymbolCount = new Map();

function trackSignal(type, symbol) {
  const key = type.toLowerCase();
  stats[key] = (stats[key] || 0) + 1;
  signalSymbolCount.set(symbol, (signalSymbolCount.get(symbol) || 0) + 1);
  stats.topSymbols = [...signalSymbolCount.entries()]
    .sort((a, b) => b[1] - a[1]).slice(0, 5).map(([s]) => s);
}

async function onSignal(signalEvent) {
  const { type, symbol, message } = signalEvent;
  const icon = type === 'CONFLUENCE' ? '🏆' : type === 'SMC' ? '📐' : '⚡';
  console.log(`\n${'═'.repeat(52)}`);
  console.log(`${icon} ${type}: ${symbol}`);
  console.log(message);
  console.log('═'.repeat(52));

  trackSignal(type, symbol);
  addToActive(symbol);
  if (signalEvent.smc?.tpsl) {
    addSignal({ type, symbol, ...signalEvent.smc.tpsl, confidence: signalEvent.smc?.confidence });
  }
  await sendSignal(signalEvent).catch(() => {});
}

async function processTicker(ticker) {
  if (!ticker?.symbol) return;
  const { symbol } = ticker;

  const analysis = pumpAnalyzer.analyze(ticker);
  if (!analysis?.symbol) return;

  const marketData = {
    symbol,
    priceChange:       analysis.priceChange       || 0,
    volume:            analysis.volumeSpike        || 1,
    orderFlow:         analysis.orderflow?.ratio   || 1,
    oiChange:          analysis.openInterest?.change || 0,
    fakeOI:            analysis.fakeOI             || 0,
    priceAcceleration: analysis.acceleration       || 0,
    momentum:          analysis.momentum           || 0,
    price:             ticker.price,
    atr:               analysis.atr                || 0
  };

  await processUnified(symbol, marketData, onSignal).catch(() => {});
}

let smcScanRunning = false;

async function runSMCScan() {
  if (smcScanRunning) return;
  smcScanRunning = true;
  try {
    const symbols = wsManager.symbols?.slice(0, 50) || [];
    if (!symbols.length) return;
    console.log(`\n🔍 SMC scan — ${symbols.length} symbols...`);
    const hits = await batchSMCScan(symbols, onSignal, 5);
    console.log(hits.length
      ? `✅ SMC scan: ${hits.length} setup(s) — ${hits.map(h => h.symbol).join(', ')}`
      : '🔍 SMC scan: no qualifying setups');
  } catch (err) {
    console.error('❌ SMC scan error:', err.message);
  } finally {
    smcScanRunning = false;
  }
}

export async function start() {
  console.log('🚀 Starting Unified Signal Engine (SMC + Pump)...');

  wsManager.onTicker((ticker) => {
    if (ticker.symbol === 'BTCUSDT') updateBTCPrice(ticker.priceChange || 0);
    processTicker(ticker).catch(() => {});
  });

  wsManager.onTrade((trade) => {
    marketDataTracker.handleTrade(trade);
    orderflowTracker.handleTrade(trade);
    oiTracker.handleTrade(trade);
  });

  await wsManager.initialize();
  console.log(`✅ WebSocket: ${wsManager.symbols?.length} symbols`);

  pumpAnalyzer.initialize(wsManager.symbols);
  marketDataTracker.initialize(wsManager.symbols);
  orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
  await oiTracker.init(wsManager.symbols);
  setOITracker(oiTracker);

  initDatabase().catch(() => {});

  setInterval(() => orderflowTracker.reset(),                    60_000);
  setInterval(() => oiTracker.runCycle().catch(() => {}),         5_000);
  setInterval(runSMCScan,                                     5 * 60_000);
  setInterval(() => sendDailySummary(stats).catch(() => {}), 24 * 60 * 60_000);

  setTimeout(runSMCScan, 30_000);

  await sendStartup(wsManager.symbols?.length || 0).catch(() => {});
  console.log('✅ Engine running — SMC + Pump active');
}
