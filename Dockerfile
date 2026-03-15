FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Streamlit config
RUN mkdir -p /app/.streamlit
RUN echo '[server]\nheadless = true\nenableCORS = false\nenableXsrfProtection = false\n\n[browser]\ngatherUsageStats = false' > /app/.streamlit/config.toml

# Railway ustawia PORT dynamicznie — skrypt startowy go odczyta
ENV PORT=8501
EXPOSE 8501

# Użyj shell form żeby $PORT się rozwinął
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0
