FROM python:3.11-slim

# Create required directories
RUN mkdir -p /opt/gpu-brrrometer \
    /var/lib/gpu-brrrometer

# Copy requirements and install dependencies
COPY requirements.txt /opt/gpu-brrrometer/
RUN pip3 install --no-cache-dir -r /opt/gpu-brrrometer/requirements.txt

# Copy the collector script
COPY gpu_activity_collector.py /opt/gpu-brrrometer/
RUN chmod 755 /opt/gpu-brrrometer/gpu_activity_collector.py

# Set working directory
WORKDIR /opt/gpu-brrrometer

# Run the collector
ENTRYPOINT ["python3", "gpu_activity_collector.py"] 