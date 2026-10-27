"""
SIST - Sistema Integrado de Gestão de RPPS
Configurações do Django.

Todas as configurações sensíveis vêm de variáveis de ambiente (arquivo .env).
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    TRUSTED_PROXY_IPS=(list, ["127.0.0.1", "::1"]),
    CELERY_TASK_ALWAYS_EAGER=(bool, False),
    JWT_ACCESS_MINUTES=(int, 15),
    JWT_REFRESH_HOURS=(int, 10),
    LOGIN_MAX_FAILED_ATTEMPTS=(int, 5),
    LOGIN_LOCK_MINUTES=(int, 15),
)
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------
DEBUG = env("DJANGO_DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceiros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # SIST
    "apps.core",
    "apps.institutions",
    "apps.accounts",
    "apps.audit",
    "apps.alerts",
    "apps.dashboard",
    "apps.search",
    "apps.actuarial",
    "apps.cadastros",
    "apps.people",
    "apps.employment",
    "apps.protocolo",
    "apps.previdencia",
    "apps.concessao",
    "apps.folha",
    "apps.esocial",
    "apps.financeiro",
    "apps.portal",
    "apps.reports",
    "apps.provadevida",
    "apps.recadastramento",
    "apps.comprev",
    "apps.leitura",
    "apps.pessoal",
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
    # Contexto da requisição (usuário, IP, instituição) usado pela auditoria
    "apps.core.middleware.RequestContextMiddleware",
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

# ---------------------------------------------------------------------------
# Banco de dados - PostgreSQL obrigatório
# ---------------------------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"]["CONN_MAX_AGE"] = 60
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError(
        "O SIST exige PostgreSQL. Ajuste DATABASE_URL para postgres://..."
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Senhas - Argon2 como hasher principal
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internacionalização - padrão brasileiro
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Arquivos estáticos e mídia
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / env("MEDIA_ROOT", default="media")

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.accounts.permissions.ModulePermission",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.sist_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "2000/hour",
        "login": "10/minute",
        "search": "120/minute",
    },
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "COERCE_DECIMAL_TO_STRING": True,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("JWT_ACCESS_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=env("JWT_REFRESH_HOURS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,  # o login é registrado pelo próprio SIST
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SIST FOPAG - Sistema Integrado de Gestão de RPPS",
    "DESCRIPTION": "API do SIST FOPAG.",
    "VERSION": "0.1.0 (Fase 1)",
    "SERVE_INCLUDE_SCHEMA": False,
    # Documentação aberta apenas em desenvolvimento
    "SERVE_PERMISSIONS": (
        ["rest_framework.permissions.AllowAny"] if DEBUG
        else ["rest_framework.permissions.IsAdminUser"]
    ),
}

# ---------------------------------------------------------------------------
# CORS / CSRF
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_HEADERS = [
    "accept", "authorization", "content-type", "user-agent",
    "x-institution-id", "x-request-id", "x-justification",
]
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
TRUSTED_PROXY_IPS = env("TRUSTED_PROXY_IPS")

# ---------------------------------------------------------------------------
# Segurança (reforçada fora do modo DEBUG)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

LOGIN_MAX_FAILED_ATTEMPTS = env("LOGIN_MAX_FAILED_ATTEMPTS")
LOGIN_LOCK_MINUTES = env("LOGIN_LOCK_MINUTES")

# Consulta de CPF na Receita Federal — Conecta gov.br, API CPF Light (ver apps/people/receita.py)
CONECTA_CLIENT_ID = env("CONECTA_CLIENT_ID", default="")
CONECTA_CLIENT_SECRET = env("CONECTA_CLIENT_SECRET", default="")
CONECTA_AMBIENTE = env("CONECTA_AMBIENTE", default="homologacao")

# eSocial: chave Fernet que criptografa o certificado A1 (.pfx) guardado no banco
ESOCIAL_CERT_KEY = env("ESOCIAL_CERT_KEY", default="")
# Segredos guardados no banco (ex.: chave de API da leitura inteligente), criptografados com Fernet
SIST_SECRETS_KEY = env("SIST_SECRETS_KEY", default="")

# ---------------------------------------------------------------------------
# Celery / Redis
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER")
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_TRACK_STARTED = True
CELERY_BEAT_SCHEDULE = {
    "verificar-alertas-a-cada-30-min": {
        "task": "apps.alerts.tasks.run_alert_checks_all",
        "schedule": 30 * 60,
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sist-default",
    }
}

# ---------------------------------------------------------------------------
# Logs - sem dados sensíveis
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mask_sensitive": {"()": "apps.core.logging.MaskSensitiveDataFilter"},
    },
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["mask_sensitive"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "sist": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
