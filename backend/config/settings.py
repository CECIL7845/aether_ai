"""Django settings. All deployment-specific values come from environment variables (see .env.example)."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173"])

# Product identity is configurable so a licensee can rebrand without code changes.
PRODUCT_NAME = env("PRODUCT_NAME", default="Aether")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_tasks_db",
    "apps.core",
    "apps.accounts",
    "apps.providers",
    "apps.chat",
    "apps.usage",
    "apps.documents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)

AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The SPA authenticates with Django sessions + CSRF rather than tokens in browser storage.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="30/min"),
        "user": env("THROTTLE_USER", default="120/min"),
        "auth": env("THROTTLE_AUTH", default="10/min"),
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

# Self-hosted Postgres roles usually can't CREATE EXTENSION; tests clone a template that already has pgvector.
if env("DATABASE_TEST_TEMPLATE", default=""):
    DATABASES["default"]["TEST"] = {"TEMPLATE": env("DATABASE_TEST_TEMPLATE")}

# --- AI providers. Keys live only in the server environment, never in the frontend. ---
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
DEFAULT_MODEL = env("DEFAULT_MODEL", default="")
PROVIDER_TIMEOUT_SECONDS = env.float("PROVIDER_TIMEOUT_SECONDS", default=300.0)

# --- Generation limits and cost controls ---
MAX_USER_MESSAGE_CHARS = env.int("MAX_USER_MESSAGE_CHARS", default=32_000)
MAX_OUTPUT_TOKENS = env.int("MAX_OUTPUT_TOKENS", default=8_192)
MAX_CONTEXT_TOKENS = env.int("MAX_CONTEXT_TOKENS", default=60_000)
USER_GENERATIONS_PER_MINUTE = env.int("USER_GENERATIONS_PER_MINUTE", default=12)
USER_DAILY_TOKEN_LIMIT = env.int("USER_DAILY_TOKEN_LIMIT", default=500_000)
USER_MONTHLY_COST_LIMIT_USD = env("USER_MONTHLY_COST_LIMIT_USD", default="10.00")
# Empty disables the deployment-wide cap.
GLOBAL_MONTHLY_COST_LIMIT_USD = env("GLOBAL_MONTHLY_COST_LIMIT_USD", default="")

# --- Background tasks (database-backed queue; run `manage.py db_worker`) ---
TASKS = {"default": {"BACKEND": env("TASK_BACKEND", default="django_tasks_db.DatabaseBackend")}}

# --- Documents and retrieval ---
# Uploaded files are stored privately under MEDIA_ROOT and are never served by URL; downloads go through an
# authenticated view.
MAX_UPLOAD_MB = env.int("MAX_UPLOAD_MB", default=20)
MAX_DOCUMENTS_PER_USER = env.int("MAX_DOCUMENTS_PER_USER", default=200)
MAX_STORAGE_MB_PER_USER = env.int("MAX_STORAGE_MB_PER_USER", default=500)
MAX_PDF_PAGES = env.int("MAX_PDF_PAGES", default=600)
MAX_EXTRACTED_CHARS = env.int("MAX_EXTRACTED_CHARS", default=3_000_000)
MAX_UNCOMPRESSED_MB = env.int("MAX_UNCOMPRESSED_MB", default=200)  # zip-bomb guard for DOCX/XLSX
MAX_SPREADSHEET_ROWS = env.int("MAX_SPREADSHEET_ROWS", default=100_000)
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", default="gemini")  # "gemini" or "none" (keyword search only)
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="gemini-embedding-001")
EMBEDDING_DIMENSIONS = 768  # fixed by the database column; changing it requires a migration and re-indexing
# Attached documents up to this size are sent to the model in full; larger ones use retrieval.
FULL_CONTEXT_MAX_CHARS = env.int("FULL_CONTEXT_MAX_CHARS", default=60_000)
RETRIEVAL_TOP_K = env.int("RETRIEVAL_TOP_K", default=8)
