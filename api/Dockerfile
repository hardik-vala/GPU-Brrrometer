FROM python:3.11-slim

# Create required directories
RUN mkdir -p /opt/gpu-api \
    /var/lib/gpu-brrrometer

# Copy requirements and install dependencies
COPY requirements.txt /opt/gpu-api/
RUN pip3 install --no-cache-dir -r /opt/gpu-api/requirements.txt

# Copy the API script
COPY api.py /opt/gpu-api/
RUN chmod 755 /opt/gpu-api/api.py

# Set working directory
WORKDIR /opt/gpu-api

# Expose port
EXPOSE 8080

# Run the API server
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"] 