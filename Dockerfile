FROM node:20-slim

# Install Python 3, pip, and Chromium for Puppeteer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        chromium \
    && rm -rf /var/lib/apt/lists/*

# Tell Puppeteer to use the installed Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Node dependencies
COPY package.json ./
RUN npm install --production

# Install Python dependencies
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application source
COPY main.py ha_client.py config.py whatsapp_bridge.js ./
COPY config.yaml.example ./

ENTRYPOINT ["python3", "main.py"]
