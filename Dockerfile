# Multi-arch (amd64 + arm64):  docker buildx build --platform linux/amd64,linux/arm64 -t hpeo .
FROM python:3.12-slim
WORKDIR /opt/hpeo
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY . .
RUN useradd --system --uid 10001 hpeo && mkdir -p /var/lib/hpeo && chown hpeo /var/lib/hpeo
USER hpeo
ENV HPEO_STATE_DIR=/var/lib/hpeo PYTHONUNBUFFERED=1
VOLUME /var/lib/hpeo
EXPOSE 4840
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1',4840),3)" || exit 1
ENTRYPOINT ["python", "-m", "deploy"]
CMD ["start"]
