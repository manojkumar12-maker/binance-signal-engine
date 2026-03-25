import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

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

const wss = new WebSocketServer({ server });
server.listen(PORT, '0.0.0.0', () => console.log('OK', PORT));

console.log('Loading engine...');

const STAGES = { IDLE: 'IDLE', PRESSURE: 'PRESSURE', SNIPER: 'SNIPER' };
const stateMap = new Map();
const cooldowns = new Map();

function canTrade(sym) {
  const last = cooldowns.get(sym) || 0;
  return Date.now() - last > 120000;
}

function isNoise(d) {
  return Math.abs(d.oiChange || 0) < 0.02 && (d.fakeOI || 0) < 0.1 && (d.volume || 1) < 1.5;
}

function detectPressure(d) {
  return d.volume > 2 && d.orderFlow > 1.4 && (d.fakeOI > 0.2 || Math.abs(d.oiChange || 0) > 0.08);
}

function detectSniper(d) {
  return d.volume > 2.5 && d.orderFlow > 1.5 && (d.fakeOI > 0.3 || Math.abs(d.oiChange || 0) > 0.12) && (d.priceAcceleration || 0) > 0.15;
}

function score(d) {
  let s = 0;
  if (d.volume > 3) s += 15;
  if (d.volume > 2) s += 10;
  if (d.orderFlow > 1.6) s += 15;
  if (d.orderFlow > 1.4) s += 10;
  if ((d.fakeOI || 0) > 0.4) s += 20;
  if ((d.fakeOI || 0) > 0.25) s += 15;
  if (Math.abs(d.oiChange || 0) > 0.2) s += 20;
  if (Math.abs(d.oiChange || 0) > 0.1) s += 10;
  return s;
}

async function start() {
  try {
    const { wsManager } = await import('./websocket/binanceWS.js');
    const { pumpAnalyzer } = await import('./analyzer/pumpAnalyzer.js');
    const { oiTracker } = await import('./engine/oiTracker.js');
    
    console.log('Modules loaded');

    wsManager.onTicker(ticker => {
      const a = pumpAnalyzer.analyze(ticker);
      if (!a?.symbol) return;
      
      const d = {
        symbol: ticker.symbol,
        priceChange: a.priceChange || 0,
        volume: a.volumeSpike || 1,
        orderFlow: a.orderflow?.ratio || 1,
        oiChange: a.openInterest?.change || 0,
        fakeOI: a.fakeOI || 0,
        priceAcceleration: a.acceleration || 0,
        price: ticker.price
      };
      
      if (isNoise(d)) return;
      if (!canTrade(d.symbol)) return;
      
      const state = stateMap.get(d.symbol) || { stage: STAGES.IDLE };
      
      if (state.stage === STAGES.IDLE && detectPressure(d)) {
        const s = score(d);
        state.stage = STAGES.PRESSURE;
        state.score = s;
        stateMap.set(d.symbol, state);
        console.log('🟣', d.symbol, 'V=' + d.volume.toFixed(1), 'OF=' + d.orderFlow.toFixed(1), 'F=' + (d.fakeOI||0).toFixed(2), 'S=' + s);
        wss.clients.forEach(c => c.send(JSON.stringify({ type: 'pressure', data: { symbol: d.symbol, score: s } })));
      }
      
      if (state.stage === STAGES.PRESSURE && detectSniper(d)) {
        const s = score(d);
        if (s < 45) return;
        
        const risk = d.price * 0.02;
        cooldowns.set(d.symbol, Date.now());
        
        console.log('🔴 SNIPER:', d.symbol, 'V=' + d.volume.toFixed(1), 'S=' + s);
        
        const signal = {
          type: 'SNIPER',
          symbol: d.symbol,
          entry: d.price,
          stopLoss: d.price - risk,
          tp1: d.price + risk,
          tp2: d.price + risk * 2,
          tp3: d.price + risk * 3,
          confidence: s
        };
        
        wss.clients.forEach(c => c.send(JSON.stringify({ type: 'sniper', data: signal })));
        stateMap.set(d.symbol, { stage: STAGES.IDLE });
      }
    });

    await wsManager.initialize();
    console.log('Connected:', wsManager.symbols.length);
    pumpAnalyzer.initialize(wsManager.symbols);
    await oiTracker.init(wsManager.symbols);
    console.log('Engine running');
  } catch (e) {
    console.error('Error:', e.message, e.stack);
  }
}

start();
