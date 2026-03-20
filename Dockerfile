FROM node:18-slim

WORKDIR /app

COPY package*.json ./

RUN npm ci --only=production --ignore-scripts

COPY . .

RUN npm cache clean --force

EXPOSE 3000

CMD ["node", "src/index.js"]
