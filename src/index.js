import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 8080;

const server = createServer((req, res) => {
  const url = req.url.split('?')[0];
  
  if (url === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{"status":"ok"}');
    return;
  }
  
  if (url === '/' || url === '/dashboard') {
    try {
      const html = readFileSync(join(__dirname, '../frontend/dashboard.html'));
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
  startEngine();
});

async function startEngine() {
  console.log('Starting engine...');
  
  try {
    console.log('Loading modules...');
    
    const { wsManager } = await import('./websocket/binanceWS.js');
    console.log('wsManager loaded');
    
    const { pumpAnalyzer } = await import('./analyzer/pumpAnalyzer.js');
    console.log('pumpAnalyzer loaded');
    
    const { processSymbol, setOITracker, updateBTCPrice, updateOIRanking } = await import('./engine/signalPipeline.js');
    console.log('signalPipeline loaded');
    
    const { oiTracker } = await import('./engine/oiTracker.js');
    console.log('oiTracker loaded');
    
    const { orderflowTracker } = await import('./engine/orderflowTracker.js');
    console.log('orderflowTracker loaded');
    
    console.log('All modules loaded, initializing...');
    const { wsManager } = await import('./websocket/binanceWS.js');
    const { pumpAnalyzer } = await import('./analyzer/pumpAnalyzer.js');
    const { processSymbol, setOITracker, updateBTCPrice, updateOIRanking } = await import('./engine/signalPipeline.js');
    const { oiTracker } = await import('./engine/oiTracker.js');
    const { orderflowTracker } = await import('./engine/orderflowTracker.js');

wsManager.onTicker(ticker => {
  if (ticker.symbol === 'BTCUSDT') updateBTCPrice(ticker.priceChange || 0);
  
  const oi = oiTracker.getChange(ticker.symbol) || 0;
  const fake = oiTracker.getFakeOI(ticker.symbol) || 0;
  updateOIRanking(ticker.symbol, oi + fake);
      
      const a = pumpAnalyzer.analyze(ticker);
      if (!a?.symbol) return;
      
      const mkt = {
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
      };
      
      const r = processSymbol(ticker.symbol, mkt);
      
      if (r?.type === 'ACCUMULATION') {
        console.log('🟣', r.symbol, 'PC=' + mkt.priceChange.toFixed(1) + '%', 'Vol=' + mkt.volume.toFixed(1), 'OF=' + mkt.orderFlow.toFixed(1));
      }
      
      if (r?.type === 'SNIPER') {
        console.log('🔴 SNIPER:', r.symbol, 'Conf=' + r.confidence);
        wss.clients.forEach(c => c.send(JSON.stringify({ signal: r })));
      }
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

    console.log('Engine running');
  } catch (e) {
    console.error('Engine error:', e.message);
  }
}
