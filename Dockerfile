# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Make the CLI script executable
RUN chmod +x twitter_bot.py

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash twitterbot
RUN chown -R twitterbot:twitterbot /app
USER twitterbot

# Default command
CMD ["python", "twitter_bot.py", "start"]

# Health check
HEALTHCHECK --interval=300s --timeout=30s --start-period=60s --retries=3 \
    CMD python twitter_bot.py test || exit 1