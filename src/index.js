import { createServer } from 'http';

const PORT = process.env.PORT || 8080;

const server = createServer((req, res) => {
  const url = req.url.split('?')[0];
  
  if (url === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', timestamp: Date.now() }));
    return;
  }
  
  res.writeHead(404);
  res.end('Not found');
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`✅ Healthcheck on port ${PORT}`);
  
  setTimeout(() => {
    import('./engine.js').catch(e => console.error('Engine error:', e.message));
  }, 2000);
});
