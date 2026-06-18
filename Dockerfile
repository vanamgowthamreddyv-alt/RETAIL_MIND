# Use the official Python 3.11 slim image for a smaller footprint
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Prevent Python from writing .pyc files to disk
ENV PYTHONDONTWRITEBYTECODE 1
# Prevent Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED 1

# Install system dependencies (required for some Python packages like psycopg2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first, to leverage Docker cache for dependencies
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 8000 for the FastAPI server
EXPOSE 8000

# Command to run the application (Render will override the port if needed)
CMD ["uvicorn", "app:api", "--host", "0.0.0.0", "--port", "8000"]
