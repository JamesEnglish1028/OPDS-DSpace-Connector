# Use a slim Python image for faster builds
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port Render expects (default 10000)
EXPOSE 10000

# Start with configurable workers and Render's injected PORT.
CMD ["sh", "-c", "gunicorn app:app -w ${WEB_CONCURRENCY:-2} -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-10000}"]
