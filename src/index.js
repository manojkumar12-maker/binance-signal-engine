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
const flowHistory = new Map();
const priceHistory = new Map();

function canTrade(sym) {
  const last = cooldowns.get(sym) || 0;
  return Date.now() - last > 60000;
}

function processTrade(symbol, qty, isBuyerMaker) {
  if (!flowData.has(symbol)) {
    flowData.set(symbol, { buy: 0, sell: 0, vol: 0, trades: 0 });
  }
  const f = flowData.get(symbol);
  if (isBuyerMaker) f.sell += qty;
  else f.buy += qty;
  f.vol += qty;
  f.trades++;
}

function getFlow(symbol) {
  const f = flowData.get(symbol);
  if (!f || f.trades < 3) return { ratio: 1, buy: 0, sell: 0 };
  const total = f.buy + f.sell;
  if (total < 1) return { ratio: 1, buy: 0, sell: 0 };
  const ratio = f.buy / (f.sell || 1);
  return { ratio: Math.max(0.5, Math.min(3, ratio)), buy: f.buy, sell: f.sell };
}

function getFakeOI(symbol) {
  if (!flowHistory.has(symbol)) {
    flowHistory.set(symbol, []);
  }
  const h = flowHistory.get(symbol);
  
  const f = flowData.get(symbol);
  if (!f) return 0;
  
  h.push({ buy: f.buy, sell: f.sell, vol: f.vol, time: Date.now() });
  if (h.length > 20) h.shift();
  
  if (h.length < 5) return 0;
  
  const recent = h[h.length - 1];
  const prev = h[0];
  
  const buy = recent.buy || 0;
  const sell = recent.sell || 0;
  const total = buy + sell;
  
  if (total < 1) return 0;
  
  const imbalance = (buy - sell) / total;
  const volChange = prev.vol > 0 ? (recent.vol - prev.vol) / prev.vol : 0;
  
  if (Math.abs(imbalance) < 0.1) return 0;
  if (Math.abs(volChange) < 0.1) return 0;
  
  return imbalance * Math.abs(volChange) * 10;
}

function getPriceChange(symbol, currentPrice) {
  if (!priceHistory.has(symbol)) {
    priceHistory.set(symbol, { prices: [], times: [] });
  }
  const h = priceHistory.get(symbol);
  h.prices.push(currentPrice);
  h.times.push(Date.now());
  if (h.prices.length > 10) {
    h.prices.shift();
    h.times.shift();
  }
  
  if (h.prices.length < 3) return 0;
  
  const oldPrice = h.prices[0];
  if (!oldPrice || oldPrice === 0) return 0;
  
  return ((currentPrice - oldPrice) / oldPrice) * 100;
}

function getAcceleration(symbol) {
  const h = priceHistory.get(symbol);
  if (!h || h.prices.length < 3) return 0;
  
  const prices = h.prices;
  const v1 = (prices[2] - prices[1]) / prices[1];
  const v2 = (prices[1] - prices[0]) / prices[0];
  
  return v2 - v1;
}

function resetFlow() {
  for (const [symbol, f] of flowData) {
    if (!flowHistory.has(symbol)) flowHistory.set(symbol, []);
    const h = flowHistory.get(symbol);
    h.push({ buy: f.buy, sell: f.sell, vol: f.vol, time: Date.now() });
    if (h.length > 20) h.shift();
    f.buy = 0;
    f.sell = 0;
    f.vol = 0;
    f.trades = 0;
  }
}

function detectPressure(d) {
  return d.volume > 1.5 && d.flowRatio > 1.15;
}

function detectSniper(d) {
  return d.volume > 1.8 && d.flowRatio > 1.25 && d.fakeOI > 0.15;
}

function calcScore(d) {
  let s = 15;
  if (d.volume > 2.5) s += 20;
  else if (d.volume > 1.8) s += 15;
  else if (d.volume > 1.5) s += 10;
  if (d.flowRatio > 1.5) s += 20;
  else if (d.flowRatio > 1.3) s += 15;
  else if (d.flowRatio > 1.15) s += 8;
  if (d.fakeOI > 0.3) s += 25;
  else if (d.fakeOI > 0.2) s += 18;
  else if (d.fakeOI > 0.1) s += 10;
  if (Math.abs(d.oiChange || 0) > 0.1) s += 15;
  if (Math.abs(d.accel) > 0.01) s += 10;
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
      
      if (!ticker.price || ticker.price === 0) return;
      
      const flow = getFlow(ticker.symbol);
      const fakeOI = getFakeOI(ticker.symbol);
      const oi = oiTracker.getChange(ticker.symbol) || 0;
      const priceChange = getPriceChange(ticker.symbol, ticker.price);
      const accel = getAcceleration(ticker.symbol);
      
      const d = {
        symbol: ticker.symbol,
        priceChange: priceChange,
        volume: ticker.volume || 1,
        flowRatio: flow.ratio,
        flow: flow,
        oiChange: oi,
        fakeOI: fakeOI,
        accel: accel,
        price: ticker.price
      };
      
      if (!canTrade(d.symbol)) return;
      
      const state = stateMap.get(d.symbol) || { stage: STAGES.IDLE };
      
      if (state.stage === STAGES.IDLE && detectPressure(d)) {
        const s = calcScore(d);
        if (s < 35) return;
        
        state.stage = STAGES.PRESSURE;
        state.score = s;
        stateMap.set(d.symbol, state);
        
        if (d.fakeOI > 0.15 || d.flowRatio > 1.3) {
          console.log('🟣', d.symbol, 'PC=' + priceChange.toFixed(1) + '%', 'V=' + d.volume.toFixed(1), 'F=' + flow.ratio.toFixed(2), 'Fak=' + fakeOI.toFixed(2), 'S=' + s);
          wss.clients.forEach(c => c.send(JSON.stringify({ type: 'pressure', data: { symbol: d.symbol, score: s } })));
        }
      }
      
      if (state.stage === STAGES.PRESSURE && detectSniper(d)) {
        const s = calcScore(d);
        if (s < 40) return;
        
        const risk = d.price * 0.015;
        cooldowns.set(d.symbol, Date.now());
        
        console.log('🔴 SNIPER:', d.symbol, 'V=' + d.volume.toFixed(1), 'F=' + flow.ratio.toFixed(2), 'Fak=' + fakeOI.toFixed(2), 'S=' + s);
        
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
