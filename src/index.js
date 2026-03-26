import { createServer } from 'http';
import { Server } from 'socket.io';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

import { wsManager } from './websocket/binanceWS.js';
import { pumpAnalyzer } from './analyzer/pumpAnalyzer.js';
import { processSymbol, setOITracker, updateBTCPrice } from './engine/signalPipeline.js';
import { orderflowTracker } from './engine/orderflowTracker.js';
import { orderBookAnalyzer } from './engine/orderBookAnalyzer.js';
import { marketDataTracker } from './engine/marketDataTracker.js';
import { oiTracker } from './engine/oiTracker.js';
import { topPumpSelector } from './engine/topPumpSelector.js';
import { signalGenerator } from './signals/signalGenerator.js';
import { addSignal } from './state.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 8080;

const server = createServer((req, res) => {
  if (req.url === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{"status":"ok"}');
    return;
  }

  if (req.url === '/' || req.url === '/dashboard') {
    try {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(readFileSync(join(__dirname, '../frontend/dashboard.html')));
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

function broadcast(type, data) {
  io.emit(type, data);
}

function handleHighPumpCandidates(ranked) {
  ranked.forEach((snap) => {
    if (snap.oiSpike) {
      console.log(`⚡ OI SPIKE: ${snap.symbol} ΔOI=${(snap.oiChange || 0).toFixed(2)}%`);
    }
    if (!snap.isCandidate) return;

    const pump = topPumpSelector.pumpTrigger(snap);
    if (!pump.triggered) return;
    if (!topPumpSelector.canEmit(snap.symbol, 90_000)) return;

    const payload = {
      type: 'HIGH_PUMP',
      symbol: snap.symbol,
      strength: Number(pump.signalStrength?.toFixed?.(2) ?? pump.signalStrength),
      rankScore: Number(snap.rankScore?.toFixed?.(2) ?? snap.rankScore),
      price: snap.price,
      context: pump.context
    };

    console.log(`🚀 HIGH_PUMP ${payload.symbol} | rank=${payload.rankScore} | strength=${payload.strength}`);
    broadcast('high_pump', payload);
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

  const now = Date.now();
    if (now - lastRankRun > 1000) {
      const ranked = topPumpSelector.evaluateTop(5);
      topSymbols = new Set(ranked.map(r => r.symbol));
      ranked.forEach((s, i) => {
        console.log(`🏆 TOP ${i + 1}: ${s.symbol} score=${s.rankScore?.toFixed?.(2)} oi=${(s.oiChange || 0).toFixed(2)} vol=${(s.volumeRatio || s.volume || 0).toFixed(2)} mom=${(s.momentum || 0).toFixed(3)} imb=${(s.imbalance || 0).toFixed(2)}`);
      });
      handleHighPumpCandidates(ranked);
      lastRankRun = now;
    }

  if (!topSymbols.has(ticker.symbol)) return;

  const pipelineInput = toPipelineInput(snapshot);
  const result = processSymbol(ticker.symbol, pipelineInput);

  if (result?.type === 'SNIPER') {
    signalGenerator.generateSignal(ticker.symbol, result).then(signal => {
      if (!signal) return;
      addSignal(signal);
      broadcast('sniper', signal);
      broadcast('signal', signal);
      console.log(`🎯 SNIPER ${signal.symbol} | entry=${signal.entryPrice?.toFixed?.(6)} | conf=${signal.confidence}`);
    }).catch(() => {});
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

    pumpAnalyzer.initialize(wsManager.symbols);
    marketDataTracker.initialize(wsManager.symbols);
    orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
    setOITracker(oiTracker);
    await oiTracker.init(wsManager.symbols);

    setInterval(() => orderflowTracker.reset(), 60000);
    setInterval(() => oiTracker.runCycle().catch(() => {}), 5000);
    console.log('Running');
  } catch (e) {
    console.error('Error:', e.message, e.stack);
  }
}

start();
