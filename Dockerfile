FROM python:3.12-slim
WORKDIR /app
COPY server.py index.html admin.html ./
ENV BLOOM_HOST=0.0.0.0 PORT=8080 BLOOM_DB=/app/data/bloom.sqlite3
RUN mkdir -p /app/data && chown -R 10001:10001 /app
USER 10001:10001
EXPOSE 8080
VOLUME ["/app/data"]
CMD ["python", "server.py"]
