export async function start() {
  console.log('🚀 Starting engine...');
  
  const { wsManager } = await import('./websocket/binanceWS.js');
  const { pumpAnalyzer } = await import('./analyzer/pumpAnalyzer.js');
  const { signalGenerator } = await import('./signals/signalGenerator.js');
  const { orderBookAnalyzer } = await import('./engine/orderBookAnalyzer.js');
  const { marketDataTracker } = await import('./engine/marketDataTracker.js');
  const { initDatabase } = await import('./database/db.js');
  const { canTrigger, strongCanTrigger, addSignal } = await import('./state.js');
  const { orderflowTracker } = await import('./engine/orderflowTracker.js');
  const { oiTracker } = await import('./engine/oiTracker.js');
  const { processSymbol, setOITracker, updateBTCPrice } = await import('./engine/signalPipeline.js');

  wsManager.onTicker((ticker) => {
    if (ticker.symbol === 'BTCUSDT') {
      updateBTCPrice(ticker.priceChange || 0);
    }
    processTicker(ticker);
  });

  wsManager.onTrade((trade) => {
    marketDataTracker.handleTrade(trade);
    orderflowTracker.handleTrade(trade);
    oiTracker.handleTrade(trade);
  });

  await wsManager.initialize();
  console.log(`✅ Connected: ${wsManager.symbols.length} symbols`);

  pumpAnalyzer.initialize(wsManager.symbols);
  marketDataTracker.initialize(wsManager.symbols);
  orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
  await oiTracker.init(wsManager.symbols);
  setOITracker(oiTracker);

  initDatabase().catch(() => {});

  setInterval(() => orderflowTracker.reset(), 60000);
  setInterval(() => oiTracker.runCycle().catch(() => {}), 5000);

  function processTicker(ticker) {
    const analysis = pumpAnalyzer.analyze(ticker);
    if (!analysis?.symbol) return;
    
    const marketData = {
      symbol: ticker.symbol,
      priceChange: analysis.priceChange || 0,
      volume: analysis.volumeSpike || 1,
      orderFlow: analysis.orderflow?.ratio || 1,
      oiChange: analysis.openInterest?.change || 0,
      fakeOI: analysis.fakeOI || 0,
      priceAcceleration: analysis.acceleration || 0,
      momentum: analysis.momentum || 0,
      price: ticker.price,
      atr: analysis.atr || 0
    };
    
    const result = processSymbol(ticker.symbol, marketData);
    
    if (result?.type === 'SNIPER') {
      signalGenerator.generateSignal(ticker.symbol, result).then(signal => {
        if (signal) {
          addSignal(signal);
          console.log(`🔴 SNIPER: ${signal.symbol}`);
        }
      });
    }
  }
  
  console.log('✅ Engine running!');
}
