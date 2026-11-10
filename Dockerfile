FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Install Unicode TTF font for Arabic guest names in owner PDF exports.
# No font files are copied into the repository or distribution.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
ENV HOME=/tmp
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py store.py reporting.py engine.py owner_exports.py ./
RUN mkdir -p /app/app_data && chown -R 10001:10001 /app
USER 10001:10001
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--server.enableCORS=true", "--server.enableXsrfProtection=true"]
