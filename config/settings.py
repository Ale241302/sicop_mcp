"""
Django settings for sicop_mcp.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "sicop",
    "sicop.atlas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "sicop.middleware.EnforcementMiddleware",
    "sicop.middleware.RegistroMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "sicop" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "sicop"),
        "USER": os.environ.get("POSTGRES_USER", "sicop"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "sicop_dev_2026"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("PG_CONN_MAX_AGE", "300")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-cr"
TIME_ZONE = "America/Costa_Rica"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- CORS (dev: abierto) ----
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o]

# ---- DRF ----
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": ["rest_framework.filters.SearchFilter", "rest_framework.filters.OrderingFilter"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# ---- Cache (Redis): el resumen de conteos se cachea ~6h (los datos solo
# cambian en el ciclo de 06:00/18:00) para que /api/v1/resumen/ y el Atlas
# carguen en milisegundos en vez de contar 55 tablas (incl. 42M filas) cada vez.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        "TIMEOUT": 6 * 3600,
    }
}

# ---- Celery ----
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_IGNORE_RESULT = False
CELERY_TASK_TRACK_STARTED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# --- zona horaria: el cron debe disparar a las 06:00 y 18:00 hora de CR ---
# (sin esto, el beat en UTC dispara a las 00:00 y 12:00 CR).
CELERY_TIMEZONE = "America/Costa_Rica"
# --- robustez: evitar re-entregas del broker cuando el worker esta ocupado ---
# El worker con prefetch=1 no reclama mas mensajes de los que puede correr;
# con un visibility_timeout mayor, un task largo (ciclo ~10 min) no se
# re-entrega mientras espera slot. El ciclo diario corre UNA vez, a tiempo.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 7200}  # 2h

# ---- FASE 2: ciclo diario 00:00 CR (domingo-viernes) + vigilancia ----
# El ciclo corre UNA vez al dia a las 00:00 hora CR, de domingo a viernes
# (NO sabado). Es la unica ventana en que puede dispararse la re-extraccion
# pesada (sicop_loop.py --pesados, 4-6 h, ~38% CPU) cuando la fuente reescribe
# un mes: a esa hora nadie usa el sistema y el CPU queda libre el resto del dia.
from celery.schedules import crontab

DIAS_CR = (0, 1, 2, 3, 4, 5)  # cron: 0=domingo ... 5=viernes (6=sabado, excluido)

CELERY_BEAT_SCHEDULE = {
    "ciclo-diario-00-00": {
        "task": "sicop.ciclo_diario",
        "schedule": crontab(day_of_week=DIAS_CR, hour=0, minute=0),
    },
    "vigilancia-reescritura-00-05": {
        "task": "sicop.vigilancia_reescritura",
        "schedule": crontab(day_of_week=DIAS_CR, hour=0, minute=5),
    },
    "consolidar-resultados-00-15": {
        "task": "sicop.consolidar_resultados",
        "schedule": crontab(day_of_week=DIAS_CR, hour=0, minute=15),
    },
    "sync-capas-00-20": {
        "task": "sicop.sync_capas",
        "schedule": crontab(day_of_week=DIAS_CR, hour=0, minute=20),
    },
    "retencion-anual-01-01": {
        "task": "sicop.retencion_anual",
        "schedule": crontab(month_of_year=1, day_of_month=1, hour=4, minute=30),
    },
    # Limpieza de disco semanal: lunes 04:10 (dry_run por defecto; la primera
    # corrida real se dispara a mano con --ejecutar/dry_run=False tras validar).
    "limpieza-disco-semanal": {
        "task": "sicop.limpieza_disco",
        "schedule": crontab(day_of_week=1, hour=4, minute=10),
    },
}

# ---- Datos SICOP ----
SICOP_DATA_DIR = os.environ.get("SICOP_DATA_DIR", str(BASE_DIR.parent / "Salidas"))
SICOP_SCRIPTS_DIR = os.environ.get("SICOP_SCRIPTS_DIR", str(BASE_DIR.parent / "03_scripts"))
SICOP_RECOVERY_DIR = os.environ.get("SICOP_RECOVERY_DIR", str(BASE_DIR.parent / "salida_recuperacion"))

# ---- Fuentes externas (F5) ----
BCCR_TOKEN = os.environ.get("BCCR_TOKEN", "")
BCCR_EMAIL = os.environ.get("BCCR_EMAIL", "")
