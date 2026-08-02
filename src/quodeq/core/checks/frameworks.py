"""Packages that count as frameworks or infrastructure for Clean Architecture.

Uncle Bob's line is delivery-mechanism vs business rule: a web framework, an
ORM, a message broker client, an HTTP client or a cloud SDK is a detail the
inner layers must be able to survive without. The list is curated rather than
"anything not in the standard library" because precision matters more than
reach here -- one wrong entry turns every domain file into a false positive,
and a report nobody trusts gets ignored wholesale.

Entries are top-level import names, not distribution names (``rest_framework``,
not ``djangorestframework``).
"""
from __future__ import annotations

FRAMEWORK_PACKAGES = frozenset({
    # Web / API frameworks and their servers
    "aiohttp", "bottle", "django", "falcon", "fastapi", "flask", "litestar",
    "pyramid", "quart", "sanic", "starlette", "tornado", "rest_framework",
    "gunicorn", "uvicorn", "werkzeug", "wsgiref",
    # Templating and presentation
    "jinja2", "mako", "chameleon",
    # ORMs, query builders, migrations
    "alembic", "mongoengine", "peewee", "pony", "sqlalchemy", "sqlmodel",
    "tortoise",
    # Database and cache drivers
    "asyncpg", "mysql", "psycopg", "psycopg2", "pymongo", "pymysql", "redis",
    "cassandra", "elasticsearch",
    # Validation / serialization frameworks that impose base classes
    "marshmallow", "pydantic",
    # Task queues and messaging
    "celery", "dramatiq", "kafka", "kombu", "pika", "rq",
    # HTTP clients and cloud SDKs
    "aiobotocore", "azure", "boto3", "botocore", "google", "httpx", "requests",
    "urllib3",
    # CLI frameworks (a delivery mechanism like any other)
    "click", "typer",
    # GraphQL, scraping, dashboards
    "graphene", "strawberry", "scrapy", "dash", "streamlit",
})
