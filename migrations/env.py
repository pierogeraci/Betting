from alembic import context
from sqlalchemy import create_engine

from core.config import get_settings
from core.models import Base

target_metadata = Base.metadata


def run() -> None:
    url = context.config.attributes.get("url") or get_settings().database_url
    connection = context.config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        conn.commit()


run()
