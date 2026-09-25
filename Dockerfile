# Use a lightweight Python 3.11 version
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY . .

# Ensure data directory permissions
RUN mkdir -p /app/data && chmod -R 777 /app/data

# Hugging Face Spaces default port
ENV PORT 7860
EXPOSE 7860

# Command to run application via Gunicorn WSGI server
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 main:app