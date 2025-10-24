FROM python:3.11

WORKDIR /app

# Create and activate virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Copy start script and make it executable
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Expose port
EXPOSE 8080

# Command to run the application
CMD ["/app/start.sh"] 
