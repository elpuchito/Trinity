# ============================================
# Frontend Dockerfile — Node 20
# ============================================
FROM node:20-alpine

WORKDIR /app

# Install deps
COPY package.json package-lock.json* ./
RUN npm install

# Copy source
COPY . .

# Expose Vite dev server port
EXPOSE 3000

# Run Vite dev server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
