FROM python:3.11-slim

WORKDIR /app

# System-Dependencies für WeasyPrint (PDF-Export)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# App-Code (wird bei Volume-Mount überschrieben)
COPY . .

# Port
EXPOSE 5000

# Gunicorn starten
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "run:app"]
