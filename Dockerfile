FROM node:22-bookworm-slim AS node
FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
WORKDIR /app
COPY seremy/tools/package*.json seremy/tools/
RUN npm ci --prefix seremy/tools --omit=dev --ignore-scripts && npm cache clean --force
COPY requirements-hosted.txt ./
RUN pip install --no-cache-dir -r requirements-hosted.txt
COPY seremy ./seremy
RUN useradd --create-home seremy && chown -R seremy:seremy /app
USER seremy
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["sh", "-c", "exec gunicorn 'seremy.hosted:create_app()' --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 240 --access-logfile -"]
