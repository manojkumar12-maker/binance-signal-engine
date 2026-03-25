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

const STAGES = { IDLE: 'IDLE', PRESSURE: 'PRESSURE', BREAKOUT: 'BREAKOUT', SNIPER: 'SNIPER' };
const stateMap = new Map();
const cooldowns = new Map();
const breakoutTracker = new Map();
const prevData = new Map();

const flowData = new Map();
const flowHistory = new Map();
const priceHistory = new Map();

let signalCount = 0;

function canTrade(sym) {
  const last = cooldowns.get(sym) || 0;
  return Date.now() - last > 120000;
}

function processTrade(symbol, qty, isBuyerMaker) {
  if (!flowData.has(symbol)) {
    flowData.set(symbol, { buy: 0, sell: 0, trades: 0 });
  }
  const f = flowData.get(symbol);
  if (isBuyerMaker) f.sell += qty;
  else f.buy += qty;
  f.trades++;
}

function getFlow(symbol) {
  const f = flowData.get(symbol);
  if (!f || f.trades < 5) return 1;
  const total = f.buy + f.sell;
  if (total < 1) return 1;
  const ratio = f.buy / (f.sell || 1);
  return Math.min(Math.max(ratio, 0.5), 3);
}

function getFakeOI(symbol) {
  const h = flowHistory.get(symbol);
  const f = flowData.get(symbol);
  if (!h || h.length < 5) return 0;
  
  h.push({ buy: f?.buy || 0, sell: f?.sell || 0, time: Date.now() });
  if (h.length > 20) h.shift();
  
  if (h.length < 5) return 0;
  
  const recent = h[h.length - 1];
  const prev = h[0];
  
  const buy = recent.buy || 0;
  const sell = recent.sell || 0;
  const total = buy + sell;
  
  if (total < 1) return 0;
  
  const imbalance = (buy - sell) / total;
  const volChange = prev.buy + prev.sell > 0 ? (total - (prev.buy + prev.sell)) / (prev.buy + prev.sell) : 0;
  
  let fake = imbalance * volChange;
  if (fake > 3) fake = 3;
  if (fake < -3) fake = -3;
  if (Math.abs(fake) < 0.15) return 0;
  
  return fake;
}

function getPriceChange(symbol, currentPrice) {
  if (!priceHistory.has(symbol)) {
    priceHistory.set(symbol, []);
  }
  const h = priceHistory.get(symbol);
  h.push({ price: currentPrice, time: Date.now() });
  if (h.length > 15) h.shift();
  
  if (h.length < 3) return 0;
  
  const oldPrice = h[0].price;
  if (!oldPrice || oldPrice === 0) return 0;
  
  return ((currentPrice - oldPrice) / oldPrice) * 100;
}

function getAcceleration(symbol) {
  const h = priceHistory.get(symbol);
  if (!h || h.length < 5) return 0;
  
  const p = h.map(x => x.price);
  const v1 = (p[4] - p[3]) / p[3];
  const v2 = (p[3] - p[2]) / p[2];
  
  return v2 - v1;
}

function resetFlow() {
  for (const [symbol, f] of flowData) {
    if (!flowHistory.has(symbol)) flowHistory.set(symbol, []);
    const h = flowHistory.get(symbol);
    h.push({ buy: f.buy, sell: f.sell, time: Date.now() });
    if (h.length > 20) h.shift();
    f.buy = 0;
    f.sell = 0;
    f.trades = 0;
  }
}

function isTrap(d) {
  return (d.priceChange > 5 && d.flow < 1.1) || (d.priceChange < -5 && d.flow > 0.9);
}

function detectPressure(d) {
  return d.volume > 2.5 && d.flow > 1.3 && Math.abs(d.fakeOI) > 0.25;
}

function detectBreakoutImminent(d) {
  return d.volume > 3 && d.flow > 1.5 && Math.abs(d.fakeOI) > 0.35 && d.accel > 0.001 && d.priceChange < 2;
}

function detectEntryCandle(d, prev) {
  if (!prev) return false;
  const accelSpike = d.accel > prev.accel * 1.5;
  const volumeSpike = d.volume > prev.volume * 1.3;
  const flowStrong = d.flow > 1.7;
  const oiConfirm = Math.abs(d.fakeOI) > 0.4;
  return accelSpike && volumeSpike && flowStrong && oiConfirm;
}

function detectSniper(d) {
  return d.volume > 3.5 && d.flow > 1.6 && Math.abs(d.fakeOI) > 0.4 && Math.abs(d.accel) > 0.002;
}

function calcScore(d) {
  let s = 20;
  if (d.volume > 4) s += 25;
  else if (d.volume > 3) s += 20;
  else if (d.volume > 2.5) s += 15;
  if (d.flow > 1.8) s += 20;
  else if (d.flow > 1.5) s += 15;
  if (Math.abs(d.fakeOI) > 0.8) s += 25;
  else if (Math.abs(d.fakeOI) > 0.5) s += 20;
  else if (Math.abs(d.fakeOI) > 0.3) s += 12;
  if (Math.abs(d.oiChange || 0) > 0.2) s += 15;
  if (Math.abs(d.accel) > 0.01) s += 10;
  return Math.min(s, 95);
}

function updateBreakout(symbol, d) {
  const now = Date.now();
  
  if (detectBreakoutImminent(d)) {
    if (!breakoutTracker.has(symbol)) {
      breakoutTracker.set(symbol, { start: now, lastAccel: d.accel, volume: d.volume, flow: d.flow });
      return null;
    }
    
    const data = breakoutTracker.get(symbol);
    const duration = (now - data.start) / 1000;
    
    data.lastAccel = d.accel;
    data.volume = d.volume;
    data.flow = d.flow;
    
    if (duration > 2 && duration < 15) {
      return { type: 'BREAKOUT', seconds: Math.round(15 - duration) };
    }
    
    if (duration > 15) {
      breakoutTracker.delete(symbol);
    }
  } else {
    breakoutTracker.delete(symbol);
  }
  
  return null;
}

function broadcast(type, data) {
  wss.clients.forEach(c => {
    if (c.readyState === 1) {
      c.send(JSON.stringify({ type, data }));
    }
  });
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
      signalCount = 0;
      console.log('📊 Trades:', tradeCount, 'Flows:', flowData.size);
      tradeCount = 0;
      resetFlow();
    }, 15000);

    wsManager.onTicker(ticker => {
      tradeCount++;
      
      if (!ticker.price || ticker.price === 0) return;
      if (signalCount > 3) return;
      
      const flow = getFlow(ticker.symbol);
      const fakeOI = getFakeOI(ticker.symbol);
      const oi = oiTracker.getChange(ticker.symbol) || 0;
      const priceChange = getPriceChange(ticker.symbol, ticker.price);
      const accel = getAcceleration(ticker.symbol);
      
      const d = {
        symbol: ticker.symbol,
        priceChange: priceChange,
        volume: ticker.volume || 1,
        flow: flow,
        oiChange: oi,
        fakeOI: fakeOI,
        accel: accel,
        price: ticker.price,
        time: Date.now()
      };
      
      const prev = prevData.get(ticker.symbol);
      prevData.set(ticker.symbol, { ...d });
      
      if (isTrap(d)) return;
      if (!canTrade(d.symbol)) return;
      
      const state = stateMap.get(d.symbol) || { stage: STAGES.IDLE };
      
      // Stage 1: PRESSURE
      if (state.stage === STAGES.IDLE && detectPressure(d)) {
        const s = calcScore(d);
        if (s < 50) return;
        
        state.stage = STAGES.PRESSURE;
        state.score = s;
        stateMap.set(d.symbol, state);
        
        console.log('🟣 PRESSURE:', d.symbol, 'V=' + d.volume.toFixed(1), 'F=' + flow.toFixed(1), 'Fak=' + fakeOI.toFixed(2), 'S=' + s);
        broadcast('pressure', { symbol: d.symbol, score: s, fakeOI, flow, volume: d.volume, price: ticker.price });
      }
      
      // Stage 2: BREAKOUT TIMER
      if (state.stage === STAGES.PRESSURE) {
        const breakout = updateBreakout(d.symbol, d);
        if (breakout && breakout.seconds > 0 && breakout.seconds < 12) {
          console.log('🟠 BREAKOUT IN ' + breakout.seconds + 's:', d.symbol);
          broadcast('breakout', { symbol: d.symbol, seconds: breakout.seconds });
          state.stage = STAGES.BREAKOUT;
          state.breakout = breakout;
          stateMap.set(d.symbol, state);
        }
      }
      
      // Stage 3: SNIPER ENTRY
      const isSniper = (state.stage === STAGES.BREAKOUT || state.stage === STAGES.PRESSURE) && 
                       (detectSniper(d) || (detectEntryCandle(d, prev) && Math.abs(fakeOI) > 0.35));
      
      if (isSniper) {
        const s = calcScore(d);
        if (s < 60) return;
        
        signalCount++;
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
        
        broadcast('sniper', signal);
        broadcast('signal', signal);
        stateMap.set(d.symbol, { stage: STAGES.IDLE });
        breakoutTracker.delete(d.symbol);
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
