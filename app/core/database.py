from sqlmodel import Session, create_engine

DATABASE_URL = "sqlite:///./surat_generator.db"
engine = create_engine(DATABASE_URL, echo=False)


def get_session():
    with Session(engine) as session:
        yield session