import { createServer } from 'http';
import { Server } from 'socket.io';
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

const io = new Server(server);
server.listen(PORT, '0.0.0.0', () => console.log('OK', PORT));

console.log('Starting...');

const STAGES = { IDLE: 'IDLE', PRESSURE: 'PRESSURE', BREAKOUT: 'BREAKOUT', SNIPER: 'SNIPER' };
const stateMap = new Map();
const cooldowns = new Map();
const breakoutTracker = new Map();
const prevData = new Map();

const flowData = new Map();

let signalCount = 0;

function canTrade(sym) {
  const last = cooldowns.get(sym) || 0;
  return Date.now() - last > 120000;
}

function processTrade(symbol, qty, isBuyerMaker) {
  if (!flowData.has(symbol)) {
    flowData.set(symbol, { buy: 0, sell: 0, trades: 0, volume: 0 });
  }
  const f = flowData.get(symbol);
  if (isBuyerMaker) f.sell += qty;
  else f.buy += qty;
  f.volume += qty;
  f.trades++;
}

function getFlow(symbol) {
  const f = flowData.get(symbol);
  if (!f || f.trades < 10) return 1;
  if (f.sell === 0) return 1.5;
  const ratio = f.buy / f.sell;
  return Math.max(0.5, Math.min(ratio, 2.5));
}

function getFakeOI(symbol) {
  const f = flowData.get(symbol);
  if (!f || f.trades < 20) return 0;
  
  const total = f.buy + f.sell;
  if (total < 100) return 0;
  
  const imbalance = (f.buy - f.sell) / total;
  if (Math.abs(imbalance) < 0.15) return 0;
  
  let fake = imbalance;
  if (fake > 1) fake = 1;
  if (fake < -1) fake = -1;
  
  return fake;
}

function getPriceChange(symbol, currentPrice) {
  return 0;
}

function getAcceleration(symbol) {
  return 0;
}

function resetFlow() {
  for (const [, f] of flowData) {
    f.buy = 0;
    f.sell = 0;
    f.trades = 0;
    f.volume = 0;
  }
}

function isTrap(d) {
  return (d.priceChange > 5 && d.flow < 1.1) || (d.priceChange < -5 && d.flow > 0.9);
}

function detectPressure(d) {
  return d.volume > 2 && d.flow > 1.3 && d.fakeOI > 0.25 && d.priceChange < 2 && d.accel > 0;
}

function detectBreakoutImminent(d) {
  return d.volume > 3 && d.flow > 1.5 && d.fakeOI > 0.4 && d.accel > 0.001 && d.priceChange < 2;
}

function detectSniper(d) {
  const long = (
    d.priceChange > 2 &&
    d.volume > 3.5 &&
    d.flow > 1.6 &&
    d.fakeOI > 0.5 &&
    d.accel > 0.002
  );
  const short = (
    d.priceChange < -2 &&
    d.volume > 3.5 &&
    d.flow < 0.7 &&
    d.fakeOI < -0.5 &&
    d.accel < -0.002
  );
  return long ? 'LONG' : short ? 'SHORT' : null;
}

function calcScore(d) {
  let s = 40;
  if (d.volume > 3) s += 15;
  if (d.flow > 1.5) s += 15;
  if (d.fakeOI > 0.5) s += 15;
  if (d.accel > 0.002) s += 10;
  if (d.priceChange > 2) s += 10;
  return Math.min(s, 90);
}

function updateBreakout(symbol, d) {
  const now = Date.now();
  
  if (detectBreakoutImminent(d)) {
    if (!breakoutTracker.has(symbol)) {
      breakoutTracker.set(symbol, { start: now });
      return null;
    }
    
    const data = breakoutTracker.get(symbol);
    const duration = (now - data.start) / 1000;
    
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
  io.emit(type, data);
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
      
      const flow = getFlow(ticker.symbol);
      const fakeOI = getFakeOI(ticker.symbol);
      const oi = oiTracker.getChange(ticker.symbol) || 0;
      
      const d = {
        symbol: ticker.symbol,
        priceChange: ticker.priceChange || 0,
        volume: ticker.volume || 1,
        flow: flow,
        oiChange: oi,
        fakeOI: fakeOI,
        accel: ticker.acceleration || 0,
        price: ticker.price,
        time: Date.now()
      };
      
      if (isTrap(d)) return;
      if (!canTrade(d.symbol)) return;
      
      const state = stateMap.get(d.symbol) || { stage: STAGES.IDLE };
      
      // Stage 1: PRESSURE (only high score)
      if (state.stage === STAGES.IDLE && detectPressure(d)) {
        const s = calcScore(d);
        if (s < 70) return;
        
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
          stateMap.set(d.symbol, state);
        }
      }
      
      // Stage 3: SNIPER (only strong signals)
      const sniperSide = detectSniper(d);
      const isSniper = (state.stage === STAGES.BREAKOUT || state.stage === STAGES.PRESSURE) && sniperSide;
      
      if (isSniper) {
        const s = calcScore(d);
        if (s < 80) return;
        if (signalCount > 2) return;
        
        signalCount++;
        const risk = d.price * 0.015;
        cooldowns.set(d.symbol, Date.now());
        
        console.log('🔴 SNIPER ' + sniperSide + ':', d.symbol, 'V=' + d.volume.toFixed(1), 'F=' + flow.toFixed(1), 'S=' + s);
        
        const signal = {
          type: 'SNIPER',
          side: sniperSide,
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
