# Use lightweight Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    openenv-core

# Expose port
EXPOSE 8000

# Start server using your main()
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]