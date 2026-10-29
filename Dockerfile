FROM python:3.13-slim

# Install system dependencies (FFmpeg is required for WebM-to-WAV transcoding)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file first to leverage Docker build cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire workspace into the container
COPY . .

# Expose port 8000
EXPOSE 8000

# Start FastAPI server using uvicorn
# --proxy-headers: behind Render's proxy, take the client address from
# X-Forwarded-For so per-IP rate limits see real users, not the proxy.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
