# Application image: the Streamlit page with the in-process AutoGen team.
# Build context: ./app (see app/.dockerignore).

FROM python:3.14-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.14-slim
# HOME points at the tmpfs so Streamlit can write its runtime files while the
# root filesystem stays read-only.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp \
       --shell /usr/sbin/nologin appuser
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY resumefit ./resumefit
COPY skills ./skills
COPY .streamlit ./.streamlit
COPY streamlit_app.py ./
USER appuser
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py"]
