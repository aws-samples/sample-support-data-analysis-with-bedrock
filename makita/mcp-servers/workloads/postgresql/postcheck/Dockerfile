FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app
COPY . .
RUN uv pip install --system "mcp[cli]" strands-agents boto3
EXPOSE 8080
CMD ["python", "server.py"]
