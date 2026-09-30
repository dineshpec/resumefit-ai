# Tools-service image: the FastMCP server (text extraction, skill
# normalisation, PDF rendering). Build context: ./mcp_server.

FROM python:3.11-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.11-slim
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp
RUN groupadd --gid 10001 mcpuser \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp \
       --shell /usr/sbin/nologin mcpuser
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY resumefit_tools ./resumefit_tools
USER mcpuser
EXPOSE 8000
CMD ["python", "-m", "resumefit_tools.server"]
