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

console.log('Starting...');

const STAGES = { IDLE: 'IDLE', PRESSURE: 'PRESSURE', SNIPER: 'SNIPER' };
const stateMap = new Map();
const cooldowns = new Map();
const flowData = new Map();

function canTrade(sym) {
  const last = cooldowns.get(sym) || 0;
  return Date.now() - last > 60000;
}

function processTrade(symbol, qty, isBuyerMaker) {
  if (!flowData.has(symbol)) {
    flowData.set(symbol, { buy: 0, sell: 0 });
  }
  const f = flowData.get(symbol);
  if (isBuyerMaker) f.sell += qty;
  else f.buy += qty;
}

function getFlow(symbol) {
  const f = flowData.get(symbol);
  if (!f || (f.buy + f.sell) < 1) return 1;
  const total = f.buy + f.sell;
  const ratio = f.buy / (f.sell || 1);
  return Math.max(0.5, Math.min(3, ratio));
}

function resetFlow() {
  for (const [, f] of flowData) { f.buy = 0; f.sell = 0; }
}

function detectPressure(d) {
  return d.volume > 1.5 && d.flow > 1.2;
}

function detectSniper(d) {
  return d.volume > 1.8 && d.flow > 1.3 && (d.accel || 0) > 0.05;
}

function calcScore(d) {
  let s = 20;
  if (d.volume > 2.5) s += 20;
  else if (d.volume > 1.8) s += 15;
  else if (d.volume > 1.5) s += 10;
  if (d.flow > 1.5) s += 20;
  else if (d.flow > 1.3) s += 15;
  else if (d.flow > 1.1) s += 5;
  if (Math.abs(d.oiChange || 0) > 0.1) s += 15;
  if ((d.fakeOI || 0) > 0.2) s += 15;
  if ((d.accel || 0) > 0.15) s += 10;
  return s;
}

async function start() {
  try {
    const { wsManager } = await import('./websocket/binanceWS.js');
    const { pumpAnalyzer } = await import('./analyzer/pumpAnalyzer.js');
    const { oiTracker } = await import('./engine/oiTracker.js');
    
    console.log('Modules loaded');

    wsManager.onTrade((trade) => {
      processTrade(trade.symbol, trade.quantity || trade.q || 0, trade.isBuyerMaker || trade.m);
    });

    let tradeCount = 0;
    setInterval(() => {
      console.log('📊 Trades:', tradeCount, 'Flows:', flowData.size);
      tradeCount = 0;
      resetFlow();
    }, 15000);

    wsManager.onTicker(ticker => {
      tradeCount++;
      
      const flow = getFlow(ticker.symbol);
      const oi = oiTracker.getChange(ticker.symbol) || 0;
      const fake = oiTracker.getFakeOI(ticker.symbol) || 0;
      
      const d = {
        symbol: ticker.symbol,
        priceChange: ticker.priceChange || 0,
        volume: ticker.volume || 1,
        flow: flow,
        oiChange: oi,
        fakeOI: fake,
        accel: ticker.acceleration || 0,
        price: ticker.price
      };
      
      if (!canTrade(d.symbol)) return;
      
      const state = stateMap.get(d.symbol) || { stage: STAGES.IDLE };
      
      if (state.stage === STAGES.IDLE && detectPressure(d)) {
        const s = calcScore(d);
        state.stage = STAGES.PRESSURE;
        state.score = s;
        stateMap.set(d.symbol, state);
        
        console.log('🟣', d.symbol, 'PC=' + d.priceChange.toFixed(1) + '%', 'V=' + d.volume.toFixed(1), 'F=' + flow.toFixed(1), 'Fak=' + fake.toFixed(2), 'S=' + s);
        wss.clients.forEach(c => c.send(JSON.stringify({ type: 'pressure', data: { symbol: d.symbol, score: s } })));
      }
      
      if (state.stage === STAGES.PRESSURE && detectSniper(d)) {
        const s = calcScore(d);
        if (s < 30) return;
        
        const risk = d.price * 0.015;
        cooldowns.set(d.symbol, Date.now());
        
        console.log('🔴 SNIPER:', d.symbol, 'V=' + d.volume.toFixed(1), 'F=' + flow.toFixed(1), 'S=' + s);
        
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
    console.log('Running');
  } catch (e) {
    console.error('Error:', e.message, e.stack);
  }
}

start();
