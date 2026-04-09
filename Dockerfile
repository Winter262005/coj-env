# Use lightweight Python image
FROM python:3.10-slim

# HF Spaces requires a non-root user with uid=1000
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPYCACHEPREFIX=/tmp/pycache


# Set working directory
WORKDIR /app

# Install dependencies BEFORE copying source
# (keeps pip install layer cached when only code changes)
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    openai \
    requests \
    "openenv-core>=0.2.0"

# Copy project files
COPY --chown=user . .

# Expose port
EXPOSE 7860

# Start server using your main()
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
