FROM node:18-alpine

WORKDIR /app

COPY package*.json ./

RUN npm ci --only=production

COPY . .

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "const http=require('http');http.get('http://localhost:3000/api/health',(r)=>process.exit(r.statusCode===200?0:1))"

CMD ["node", "src/index.js"]
