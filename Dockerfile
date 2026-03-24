# Binance Signal Engine v2.0 — Railway
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./

RUN rm -rf node_modules && npm install --production

COPY . .

# Railway sets PORT dynamically
EXPOSE ${PORT:-3000}

CMD ["node", "src/index.js"]
