from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = "sqlite:///./surat_generator.db"
engine = create_engine(DATABASE_URL, echo=False)


def init_db():
    from app.models import letter_type  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session