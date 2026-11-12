FROM python:3.11-slim

# System deps needed by chromadb (C extensions) and pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so this layer is cached on code-only changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Streamlit config: disable the "Press Enter to continue" prompt and set port
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONPATH=/app/src:/app

EXPOSE 8501

# OPENAI_API_KEY must be supplied at run time via --env or docker-compose env_file.
# The index (data/indexes/) should be built before running, or mounted in.
CMD ["streamlit", "run", "app.py", "--server.headless=true"]
