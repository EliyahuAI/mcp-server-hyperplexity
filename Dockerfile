FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .
ENV MCP_TRANSPORT=http
ENV PORT=8000
EXPOSE 8000
CMD ["mcp-server-hyperplexity"]
