FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install required packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the monitoring script
COPY monitor.py .

# Run the monitor
CMD ["python", "-u", "monitor.py"]
