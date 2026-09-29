"""Initialize LangGraph PostgreSQL tables before application sessions exist."""

from .config import get_settings


def initialize_checkpoint_store() -> None:
    database_url = get_settings().database_url
    if not database_url.startswith("postgresql"):
        return
    from langgraph.checkpoint.postgres import PostgresSaver

    uri = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with PostgresSaver.from_conn_string(uri) as checkpointer:
        checkpointer.setup()


if __name__ == "__main__":
    initialize_checkpoint_store()
