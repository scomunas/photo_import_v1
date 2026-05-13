FROM node:18-alpine

WORKDIR /app

# Copiamos los archivos de dependencias
COPY package*.json ./

# Instalamos dependencias
RUN npm install

# Copiamos el resto del código
COPY . .

# Exponemos el puerto 5173 que tienes configurado en el docker-compose
EXPOSE 5173

# Generamos el env.js a partir de las variables de entorno y arrancamos
CMD mkdir -p src/assets && echo "window.__env = { apiUrl: 'http://${BACKEND_IP:-localhost}:${BACKEND_PORT:-8080}' };" > src/assets/env.js && npm run start -- --host 0.0.0.0 --port 5173 --disable-host-check
