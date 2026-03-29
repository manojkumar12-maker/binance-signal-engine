import { createServer } from 'http';
import { Server } from 'socket.io';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

import { wsManager } from './websocket/binanceWS.js';
import { pumpAnalyzer } from './analyzer/pumpAnalyzer.js';
import { updateSniperState, runSniper, getTopWatching } from './engine/sniperEngine.js';
import { executeTrade } from './execution/execute.js';
import { processSymbol, setOITracker, updateBTCPrice, getAllScores } from './engine/signalPipeline.js';
import { orderflowTracker } from './engine/orderflowTracker.js';
import { orderBookAnalyzer } from './engine/orderBookAnalyzer.js';
import { marketDataTracker } from './engine/marketDataTracker.js';
import { oiTracker } from './engine/oiTracker.js';
import { topPumpSelector } from './engine/topPumpSelector.js';
import { signalGenerator } from './signals/signalGenerator.js';
import { addSignal, getRecentSignals, getActiveSignals } from './state.js';
import { sendTelegram } from './utils/telegram.js';
import { shouldEmit, selectTopSignals, isHighQuality, isExecutionReady, formatSignalForTelegram, formatTopWatch, getCooldownForType } from './signals/signalFilters.js';
import { initDatabase, createSignal, closeDatabase } from './database/db.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 8080;

console.log('Starting server on port:', PORT);

const server = createServer((req, res) => {
  const pathOnly = req.url.split('?')[0];

  if (pathOnly === '/api/health' || pathOnly === '/health' || pathOnly === '/') {
    console.log('Health check hit');
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('OK');
    return;
  }

  // Basic CORS for API endpoints
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET', 'OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

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
      const topWatch = getTopWatching();
      const allScores = getAllScores();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ top, topWatch, allScores, signals: grouped }));
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

const io = new Server(server, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  }
});
server.listen(PORT, '0.0.0.0', () => console.log('OK', PORT)).on('error', (err) => {
  console.error('Server error:', err);
});

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
    // Telegram verbose output removed
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
  const allowedTypes = ['SNIPER', 'HIGH_PUMP'];
  const filtered = signals.filter(s => allowedTypes.includes(s.type));
  const topSignals = selectTopSignals(filtered, 5);
  
  if (topSignals.length === 0) return;
  
  for (const s of topSignals) {
    const { allowed, cooldown } = shouldEmit(s.symbol, s.type);
    if (!allowed) continue;
    
    const sigKey = `${s.type}-${s.symbol}`;
    if (notifiedSignals.has(sigKey)) continue;
    notifiedSignals.add(sigKey);
    
    const signalDirection = s.direction || "LONG";
    const trade = await executeTrade(s.symbol, s.type, s.price, 1000, signalDirection);
    const side = signalDirection === "LONG" ? "🟢 LONG" : "🔴 SHORT";
    const formattedSymbol = s.symbol.replace("USDT", "/USDT");
    const fmt = n => Number(n).toFixed(6).replace(/0+$/, '').replace(/\.$/, '') || '0';

    const msg = formatSignalForTelegram({
      ...s,
      entry: trade.entry,
      stopLoss: trade.sl,
      tp1: trade.tp1,
      tp2: trade.tp2,
      tp3: trade.tp3,
      direction: side,
      rawDirection: signalDirection
    });

    if (isExecutionReady(s)) {
      sendTelegram(msg).catch(() => {});
    }

    broadcast('sniper', {
      symbol: s.symbol,
      type: s.type,
      level: s.level,
      confidence: s.finalScore.toFixed(1),
      entry: trade.entry,
      stopLoss: trade.sl,
      tp1: trade.tp1,
      tp2: trade.tp2,
      oiChange: s.oiChange,
      volumeRatio: s.volumeRatio,
      orderFlow: s.imbalance
    });
  }
}

async function start() {
  try {
    console.log('Initializing database...');
    initDatabase().then(() => console.log('Database ready')).catch(e => console.log('DB init error:', e.message));
    
    wsManager.onTrade((trade) => {
      marketDataTracker.handleTrade(trade);
      orderflowTracker.handleTrade(trade);
      oiTracker.handleTrade(trade);
    });

    wsManager.onTicker(handleTicker);

    await wsManager.initialize();
    console.log('Connected:', wsManager.symbols.length);
    const now = new Date();
    const istTime = now.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' });
    sendTelegram(`🚀 SIGNAL ENGINE STARTED\n\n📊 Monitoring ${wsManager.symbols.length} USDT Perpetuals\n🕐 Started at: ${istTime} IST\n\n✅ Ready to detect signals`).catch(() => {});

    pumpAnalyzer.initialize(wsManager.symbols);
    marketDataTracker.initialize(wsManager.symbols);
    orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
    setOITracker(oiTracker);
    await oiTracker.init(wsManager.symbols);

    setInterval(() => orderflowTracker.reset(), 60000);
    setInterval(() => oiTracker.runCycle().catch(() => {}), 5000);

    setInterval(() => {
      const topSignals = runSniper();
      const topWatch = getTopWatching();
      
      broadcast('top_watch', topWatch);
      
      if (topSignals.length > 0) {
        const executionReady = topSignals.filter(s => isExecutionReady(s));
        if (executionReady.length > 0) {
          notifySniperSignals(executionReady);
        } else {
          notifySniperSignals(topSignals.slice(0, 2));
        }
      }
    }, 3000);

    console.log('Running');
  } catch (e) {
    console.error('Error:', e.message, e.stack);
  }
}

process.on('SIGTERM', async () => {
  console.log('Shutting down...');
  await closeDatabase();
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('Shutting down...');
  await closeDatabase();
  process.exit(0);
});

start().catch(e => console.error('Startup error:', e));
