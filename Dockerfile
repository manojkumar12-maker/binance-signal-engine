# Binance Signal Engine - v3.0
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./

RUN rm -rf node_modules && npm install

COPY . .

EXPOSE 3000

CMD ["node", "src/index.js"]
