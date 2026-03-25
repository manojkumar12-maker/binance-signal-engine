console.log('Starting...');

const { wsManager } = await import('./websocket/binanceWS.js');
const { pumpAnalyzer } = await import('./analyzer/pumpAnalyzer.js');
const { processSymbol, setOITracker, updateBTCPrice } = await import('./engine/signalPipeline.js');
const { oiTracker } = await import('./engine/oiTracker.js');
const { orderflowTracker } = await import('./engine/orderflowTracker.js');

wsManager.onTicker(ticker => {
  if (ticker.symbol === 'BTCUSDT') updateBTCPrice(ticker.priceChange || 0);
  
  const a = pumpAnalyzer.analyze(ticker);
  if (!a?.symbol) return;
  
  const r = processSymbol(ticker.symbol, {
    symbol: ticker.symbol,
    priceChange: a.priceChange || 0,
    volume: a.volumeSpike || 1,
    orderFlow: a.orderflow?.ratio || 1,
    oiChange: a.openInterest?.change || 0,
    fakeOI: a.fakeOI || 0,
    priceAcceleration: a.acceleration || 0,
    momentum: a.momentum || 0,
    price: ticker.price,
    atr: a.atr || 0
  });
  
  if (r?.type === 'SNIPER') console.log('🔴', r.symbol);
});

wsManager.onTrade(trade => {
  orderflowTracker.handleTrade(trade);
  oiTracker.handleTrade(trade);
});

await wsManager.initialize();
console.log('Connected:', wsManager.symbols.length);

pumpAnalyzer.initialize(wsManager.symbols);
await oiTracker.init(wsManager.symbols);
setOITracker(oiTracker);

setInterval(() => oiTracker.runCycle().catch(() => {}), 5000);

console.log('Running');
