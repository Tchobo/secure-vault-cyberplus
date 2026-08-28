FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 
ENV PYTHONDONTWRITEBYTECODE=1

# ✅ WORKDIR doit être /app
WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    gettext \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# ✅ Copier requirements.txt depuis backend/
COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip && pip install -r /requirements.txt

# ✅ Copier tout le dossier backend dans /app/backend
COPY ./app /app

# Créer les dossiers static/media
RUN mkdir -p /vol/web/static /vol/web/media && chmod -R 755 /vol

EXPOSE 8000

# ✅ CMD avec le bon chemin (manage.py est dans /app/backend)
CMD ["gunicorn", "--chdir", "/app", "app.wsgi:application", "--bind", "0.0.0.0:8000"]