# Binance Signal Engine v2.0 — Railway
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./

RUN rm -rf node_modules && npm install --production

COPY . .

EXPOSE ${PORT:-8080}

CMD ["node", "src/index.js"]
