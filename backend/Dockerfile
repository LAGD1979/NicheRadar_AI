FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

# Cliente de PostgreSQL 16, igual que el servidor: un pg_dump más nuevo escribe un volcado
# que el servidor 16 no restaura. Viene del repositorio oficial de PostgreSQL (PGDG).
RUN apt-get update     && apt-get install -y --no-install-recommends tzdata ca-certificates curl     && install -d /usr/share/postgresql-common/pgdg     && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc         https://www.postgresql.org/media/keys/ACCC4CF8.asc     && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main"         > /etc/apt/sources.list.d/pgdg.list     && apt-get update     && apt-get install -y --no-install-recommends postgresql-client-16     && apt-get purge -y curl     && apt-get autoremove -y     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

ENV PYTHONPATH=/app
