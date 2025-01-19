# Use a lightweight Python base image
FROM python:3.9-slim

# Set a working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . /app

# Expose the port your Flask app runs on (5000 by default)
EXPOSE 5001

# Run the app
CMD ["python", "app.py"]
