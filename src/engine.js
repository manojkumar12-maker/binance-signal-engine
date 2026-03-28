console.log('Starting...');

const { wsManager } = await import('./websocket/binanceWS.js');
const { pumpAnalyzer } = await import('./analyzer/pumpAnalyzer.js');
const { processSymbol, setOITracker, updateBTCPrice, getTopSymbols } = await import('./engine/signalPipeline.js');
const { oiTracker } = await import('./engine/oiTracker.js');
const { orderflowTracker } = await import('./engine/orderflowTracker.js');
const { startFundingLoop, fetchFundingRates } = await import('./data/funding.js');
const { getLiquidations, analyzeLiquidations } = await import('./data/liquidations.js');
const { createServer } = await import('http');
const { WebSocketServer } = await import('ws');
const { readFileSync } = await import('fs');
const { join, dirname } = await import('path');
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 8080;

const server = createServer((req, res) => {
  const url = req.url.split('?')[0];
  
  if (url === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ 
      status: 'ok', 
      symbols: wsManager?.symbols?.length || 0,
      timestamp: Date.now()
    }));
    return;
  }
  
  if (url === '/api/liquidations') {
    const liqs = getLiquidations();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(liqs));
    return;
  }
  
  if (url === '/api/top') {
    const top = getTopSymbols(10);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ top }));
    return;
  }
  
  if (url === '/' || url === '/index.html') {
    try {
      const html = readFileSync(join(__dirname, '../index.html'));
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    } catch (e) {
      res.writeHead(500);
      res.end('Dashboard not found');
    }
    return;
  }
  
  res.writeHead(404);
  res.end('Not found');
});

const wss = new WebSocketServer({ server });

server.listen(PORT, '0.0.0.0', () => {
  console.log('OK ' + PORT);
});

wsManager.onTicker(ticker => {
  if (ticker.symbol === 'BTCUSDT') updateBTCPrice(ticker.priceChange || 0);
  
  const a = pumpAnalyzer.analyze(ticker);
  if (!a?.symbol) return;
  
  const r = processSymbol(ticker.symbol, {
    symbol: ticker.symbol,
    priceChange: a.priceChange || 0,
    volume: a.volumeSpike || 1,
    orderFlow: a.orderflow?.ratio || a.imbalance || 1,
    oiChange: a.oiChange || 0,
    fakeOI: a.fakeOI || 0,
    priceAcceleration: a.acceleration || 0,
    momentum: a.momentum || 0,
    price: ticker.price,
    atr: a.atr || 0
  });
  
  if (r?.type === 'SNIPER') {
    console.log('🔴 SNIPER:', r.symbol);
    wss.clients.forEach(c => c.send(JSON.stringify({ signal: r })));
  }
  
  if (r?.type === 'EARLY_PUMP') {
    console.log('🚀 EARLY PUMP:', r.symbol, '| Score:', r.confidence);
    wss.clients.forEach(c => c.send(JSON.stringify({ signal: r })));
  }
  
  if (r?.type === 'HIGH_PUMP') {
    console.log('🔥🔥🔥 HIGH PUMP SIGNAL:', r.symbol, '| Phase:', r.pumpPhase, '| Score:', r.confidence);
    wss.clients.forEach(c => c.send(JSON.stringify({ signal: r })));
  }
  
  if (r?.type === 'ACCUMULATION') {
    console.log('📍 ACCUMULATION:', r.symbol, '| Phase:', r.pumpPhase);
    wss.clients.forEach(c => c.send(JSON.stringify({ signal: r })));
  }
  
  if (r?.type === 'PRESSURE' && r.confidence >= 7) {
    wss.clients.forEach(c => c.send(JSON.stringify({ signal: r })));
  }
});

wsManager.onTrade(trade => {
  orderflowTracker.handleTrade(trade);
  oiTracker.handleTrade(trade);
});

wsManager.onLiquidation(liq => {
  console.log(`💥 LIQUIDATION: ${liq.symbol} ${liq.side} ${liq.price}`);
});

await wsManager.initialize();
console.log('Connected:', wsManager.symbols.length);

pumpAnalyzer.initialize(wsManager.symbols);
await oiTracker.init(wsManager.symbols);
setOITracker(oiTracker);

fetchFundingRates();
startFundingLoop(60000);

setInterval(() => oiTracker.runCycle().catch(() => {}), 5000);

setInterval(() => {
  const ofStats = orderflowTracker.getStats();
  if (ofStats.activeSymbols > 0) {
    console.log(`🔥 Active trade symbols: ${ofStats.activeSymbols} | OF tracked: ${ofStats.trackedSymbols}`);
  }
}, 30000);

setInterval(() => {
  const topSymbols = getTopSymbols(5);
  if (topSymbols.length > 0) {
    const topList = topSymbols.map(([s, score]) => `${s}(${score})`).join(', ');
    console.log(`🏆 Top 5 Symbols: ${topList}`);
  }
}, 60000);

console.log('Running');
