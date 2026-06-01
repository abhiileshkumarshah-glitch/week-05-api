from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv
import anthropic

load_dotenv()

ai_client = anthropic.Anthropic()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "sqlite:///./books.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

ai_client = anthropic.Anthropic()


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    author = Column(String, index=True)
    status = Column(String, default="want-to-read")
    rating = Column(Integer, nullable=True)


Base.metadata.create_all(bind=engine)


class BookCreate(BaseModel):
    title: str
    author: str
    status: str = "want-to-read"
    rating: int | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def home():
    return {"message": "Week 5 Book API is running"}


@app.post("/books")
def create_book(book: BookCreate, db: Session = Depends(get_db)):
    new_book = Book(
        title=book.title,
        author=book.author,
        status=book.status,
        rating=book.rating
    )

    db.add(new_book)
    db.commit()
    db.refresh(new_book)

    return new_book


@app.get("/books")
def get_books(db: Session = Depends(get_db)):
    books = db.query(Book).all()
    return books


@app.post("/ai/chat")
def chat_with_assistant(request: ChatRequest):
    reply = (
        "Demo response: 1984 is a dystopian novel about surveillance, "
        "control, and personal freedom."
    )

    return {




        "reply": reply,
        "updated_history": request.conversation_history + [
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": reply},
        ],
    }


@app.post("/ai/recommend")
def get_recommendations(request: ChatRequest, db: Session = Depends(get_db)):
    books = db.query(Book).all()

    book_list = ""
    for b in books:
        book_list += f"- {b.title} by {b.author}, status: {b.status}, rating: {b.rating}\n"

    reply = f"""Demo personalized recommendations based on your library:

Your current book library:
{book_list}

1. Brave New World by Aldous Huxley
Why: Since you are reading 1984, this is another classic dystopian novel about control and society.

2. The Psychology of Money by Morgan Housel
Why: Since you read Atomic Habits, this matches your interest in practical self-improvement.

3. Fahrenheit 451 by Ray Bradbury
Why: It is a short, powerful book about censorship, books, and society."""

    return {
        "reply": reply,
        "updated_history": request.conversation_history + [
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": reply},
        ],
    }