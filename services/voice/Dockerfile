FROM node:20-alpine

WORKDIR /app

COPY services/voice/package.json package.json
RUN npm install --omit=dev

COPY services/voice/server.mjs server.mjs

ENV PORT=8001

EXPOSE 8001

CMD ["npm", "run", "dev"]
