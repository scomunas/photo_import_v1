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

# Iniciamos el servidor de desarrollo de Angular en el puerto 5173
CMD ["npm", "run", "start", "--", "--host", "0.0.0.0", "--port", "5173", "--disable-host-check"]
