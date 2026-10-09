from alembic import context
from pulse.core.config import get_config
from pulse.db.models import Base
from sqlalchemy import create_engine

config = context.config
url = get_config().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_object=lambda obj, name, type_, reflected, compare_to: (
                not (
                    type_ == "index"
                    and name == "incident_title_search"
                    and connection.dialect.name != "postgresql"
                )
            ),
        )
        with context.begin_transaction():
            context.run_migrations()
