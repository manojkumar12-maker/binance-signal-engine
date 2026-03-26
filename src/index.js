import { createServer } from 'http';
import { Server } from 'socket.io';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

import { wsManager } from './websocket/binanceWS.js';
import { pumpAnalyzer } from './analyzer/pumpAnalyzer.js';
import { updateSniperState, runSniper } from './engine/sniperEngine.js';
import { executeTrade } from './execution/execute.js';
import { processSymbol, setOITracker, updateBTCPrice } from './engine/signalPipeline.js';
import { orderflowTracker } from './engine/orderflowTracker.js';
import { orderBookAnalyzer } from './engine/orderBookAnalyzer.js';
import { marketDataTracker } from './engine/marketDataTracker.js';
import { oiTracker } from './engine/oiTracker.js';
import { topPumpSelector } from './engine/topPumpSelector.js';
import { signalGenerator } from './signals/signalGenerator.js';
import { addSignal, getRecentSignals } from './state.js';
import { sendTelegram } from './utils/telegram.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 8080;

const server = createServer((req, res) => {
  // Basic CORS for API endpoints
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const pathOnly = req.url.split('?')[0];

  if (pathOnly === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{"status":"ok"}');
    return;
  }
  if (pathOnly === '/heatmap' || pathOnly === '/api/heatmap') {
    try {
      const signals = getRecentSignals(200);
      const grouped = {};
      signals.forEach(sig => {
        if (!grouped[sig.symbol]) grouped[sig.symbol] = [];
        grouped[sig.symbol].push({
          tier: sig.tier,
          type: sig.type,
          confidence: sig.confidence,
          entryPrice: sig.entryPrice,
          timestamp: sig.timestamp
        });
      });
      const top = topPumpSelector.getTopByOI(5);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ top, signals: grouped }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'heatmap_error', message: e.message }));
    }
    return;
  }

  if (req.url === '/' || req.url === '/dashboard') {
    try {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(readFileSync(join(__dirname, '../frontend/index.html')));
    } catch (e) {
      res.writeHead(500).end('Error');
    }
    return;
  }

  res.writeHead(404).end('Not found');
});

const io = new Server(server);
server.listen(PORT, '0.0.0.0', () => console.log('OK', PORT));

let topSymbols = new Set();
let lastRankRun = 0;
let lastDebugTelegram = 0;

function broadcast(type, data) {
  io.emit(type, data);
}

function handleHighPumpCandidates(ranked) {
  ranked.forEach((snap) => {
    if (snap.oiSpike) {
      console.log(`⚡ OI SPIKE: ${snap.symbol} ΔOI=${(snap.oiChange || 0).toFixed(2)}%`);
    }
    // ranked list is already candidate-filtered; extra guard
    if (!snap.isCandidate) return;

    let level = null;
    const oiAbs = Math.abs(snap.oiChange || 0);
    if (oiAbs > 2) level = '🚀 STRONG PUMP';
    else if (oiAbs > 0.5) level = '⚡ BUILDING';
    else if (oiAbs > 0.1) level = '👀 WATCH';

    const pump = topPumpSelector.pumpTrigger(snap);
    if (!pump.triggered && !level) return;
    if (!topPumpSelector.canEmit(snap.symbol, 90_000)) return;

    const payload = {
      type: 'HIGH_PUMP',
      symbol: snap.symbol,
      strength: Number(pump.signalStrength?.toFixed?.(2) ?? pump.signalStrength),
      rankScore: Number(snap.rankScore?.toFixed?.(2) ?? snap.rankScore),
      price: snap.price,
      fakeOI: snap.fakeOI,
      flow: snap.orderFlow,
      volume: snap.volumeRatio || snap.volume,
      context: pump.context
    };

    console.log(`🚀 HIGH_PUMP ${payload.symbol} | rank=${payload.rankScore} | strength=${payload.strength}`);
    broadcast('high_pump', payload);
    if (level) {
      sendTelegram(`${level}\n${payload.symbol}\nOI: ${(snap.oiChange || 0).toFixed(3)}%\nVol: ${(snap.volumeRatio || snap.volume || 0).toFixed(2)}`).catch(() => {});
    } else {
      sendTelegram(`🚀 HIGH PUMP: ${payload.symbol}\nScore: ${payload.rankScore}\nStrength: ${payload.strength}`).catch(() => {});
    }
  });
}

function toPipelineInput(snapshot) {
  return topPumpSelector.toPipelineInput(snapshot);
}

function handleTicker(ticker) {
  if (!ticker?.price || !ticker.symbol) return;

  if (ticker.symbol === 'BTCUSDT') {
    updateBTCPrice(ticker.priceChange || 0);
  }

  const analysis = pumpAnalyzer.analyze(ticker);
  if (!analysis?.symbol) return;

  const snapshot = topPumpSelector.ingest(analysis, ticker);

  updateSniperState(snapshot.symbol, {
    imbalance: snapshot.imbalance,
    volumeRatio: snapshot.volumeRatio || snapshot.volume,
    price: snapshot.price,
    oiChange: snapshot.oiChange
  });

  const now = Date.now();
    if (now - lastDebugTelegram > 60000) {
      const topWeak = topPumpSelector.getTopByOI(1);
      if (topWeak.length > 0) {
        const t = topWeak[0];
        sendTelegram(`DEBUG ${t.symbol}\nOI: ${t.oi?.toFixed?.(4)}%\nVol: ${t.volume?.toFixed?.(2)}`).catch(() => {});
      }
      lastDebugTelegram = now;
    }
    if (now - lastRankRun > 1000) {
      const ranked = topPumpSelector.evaluateTop(5);
      topSymbols = new Set(ranked.map(r => r.symbol));

      if (ranked.length === 0) {
        // No strong candidates — skip trading this cycle
        return;
      }

      ranked.forEach((s, i) => {
        console.log(`🏆 TOP ${i + 1}: ${s.symbol} score=${s.rankScore?.toFixed?.(2)} oi=${(s.oiChange || 0).toFixed(2)} vol=${(s.volumeRatio || s.volume || 0).toFixed(2)} mom=${(s.momentum || 0).toFixed(3)} imb=${(s.imbalance || 0).toFixed(2)}`);
      });
      handleHighPumpCandidates(ranked);
      lastRankRun = now;
    }
}

const notifiedSignals = new Set();
async function notifySniperSignals(signals) {
  for (const s of signals) {
    const sigKey = `${s.type}-${s.symbol}`;
    if (notifiedSignals.has(sigKey)) continue;
    notifiedSignals.add(sigKey);

    const trade = await executeTrade(s.symbol, s.type, s.price, 1000);
    const side = trade.direction === "LONG" ? "BUY (LONG) 🚀" : "SELL (SHORT) 🩸";
    const formattedSymbol = s.symbol.replace("USDT", "/USDT");
    const fmt = n => Number(n).toFixed(6).replace(/0+$/, '').replace(/\.$/, '') || '0';

    const msg = `💥${s.type} 💥\n\n${formattedSymbol} — ${side}\n\n🟢 Leverage: Cross 5X\n\n⚡️ Entry: ${fmt(trade.entry)}\n\n😵 Take Profits:\n\nTP1: ${fmt(trade.tp1)}\nTP2: ${fmt(trade.tp2)}\nTP3: ${fmt(trade.tp3)}\n\nStop Loss: ${fmt(trade.sl)}\n\n⚠️ Risk Management:\nUse only 3% – 5% of your portfolio.\n(Simulated Risk: $10, Size: ${trade.size.toFixed(2)})`;

    sendTelegram(msg).catch(() => {});

    broadcast('sniper', {
      symbol: s.symbol,
      confidence: s.finalScore.toFixed(1),
      entry: trade.entry,
      stopLoss: trade.sl,
      tp1: trade.tp1,
      tp2: trade.tp2
    });
  }
}

async function start() {
  try {
    wsManager.onTrade((trade) => {
      marketDataTracker.handleTrade(trade);
      orderflowTracker.handleTrade(trade);
      oiTracker.handleTrade(trade);
    });

    wsManager.onTicker(handleTicker);

    await wsManager.initialize();
    console.log('Connected:', wsManager.symbols.length);
    sendTelegram('✅ ENGINE STARTED: index.js').catch(() => {});

    pumpAnalyzer.initialize(wsManager.symbols);
    marketDataTracker.initialize(wsManager.symbols);
    orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
    setOITracker(oiTracker);
    await oiTracker.init(wsManager.symbols);

    setInterval(() => orderflowTracker.reset(), 60000);
    setInterval(() => oiTracker.runCycle().catch(() => {}), 5000);

    setInterval(() => {
      const topSignals = runSniper();
      if (topSignals.length > 0) {
        const toNotify = topSignals.filter(s => s.type === "EARLY ENTRY" || s.type === "CONFIRMED ENTRY");
        notifySniperSignals(toNotify);
      }
    }, 3000);

    console.log('Running');
  } catch (e) {
    console.error('Error:', e.message, e.stack);
  }
}

start();
