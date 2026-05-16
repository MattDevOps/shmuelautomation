FROM node:20-alpine

WORKDIR /app

# tsx (runtime transpiler) lives in devDependencies; install all deps so
# `tsx src/index.ts` works in prod. Image stays under 200MB.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json ./
COPY src ./src

EXPOSE 8787

CMD ["npm", "start"]
