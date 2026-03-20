FROM node:18-alpine

RUN apk add --no-cache openssl1.1 libcrypto1.1

WORKDIR /app

COPY package*.json ./
COPY prisma ./prisma/

RUN npm ci

RUN npx prisma generate

COPY . .

EXPOSE 3000

CMD ["node", "src/index.js"]
