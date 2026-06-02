import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "sqlite:///./books.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


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


def call_gemini(system_prompt: str, messages: list[dict]) -> str:
    try:
        if not GEMINI_API_KEY:
            return "API key is missing. Please add GEMINI_API_KEY to the .env file."

        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_prompt,
        )

        conversation_text = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            conversation_text += f"{role}: {content}\n"

        response = model.generate_content(conversation_text)

        return response.text

    except Exception as e:
        return f"Gemini API error: {str(e)}"


@app.get("/")
def home():
    return {"message": "Week 5 Book API is running"}


@app.post("/books")
def create_book(book: BookCreate, db: Session = Depends(get_db)):
    new_book = Book(
        title=book.title,
        author=book.author,
        status=book.status,
        rating=book.rating,
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
    messages = request.conversation_history + [
        {"role": "user", "content": request.message}
    ]

    system_prompt = """You are a helpful book assistant for a personal book tracking app.
Help users discover books, discuss what they've read, and get personalized recommendations.
Be conversational, enthusiastic about books, and concise in your responses."""

    reply = call_gemini(system_prompt, messages)

    return {
        "reply": reply,
        "updated_history": messages + [
            {"role": "assistant", "content": reply}
        ],
    }


@app.post("/ai/recommend")
def get_recommendations(request: ChatRequest, db: Session = Depends(get_db)):
    books = db.query(Book).all()

    read_books = [b for b in books if b.status == "read"]
    reading_books = [b for b in books if b.status == "reading"]

    book_context = "Here is the user's book library:\n"

    if read_books:
        book_context += "\nBooks they've read:\n"
        for b in read_books:
            rating_str = f" (rated {b.rating}/5)" if b.rating else ""
            book_context += f"- {b.title} by {b.author}{rating_str}\n"

    if reading_books:
        book_context += "\nCurrently reading:\n"
        for b in reading_books:
            book_context += f"- {b.title} by {b.author}\n"

    if not read_books and not reading_books:
        book_context += "No books tracked yet.\n"

    system_prompt = f"""You are a personalized book recommendation assistant.

{book_context}

Based on this reading history, provide thoughtful, personalized recommendations.
Be specific about why each recommendation matches their taste.
Keep responses concise — 2-3 recommendations at most unless asked for more."""

    messages = request.conversation_history + [
        {"role": "user", "content": request.message}
    ]

    reply = call_gemini(system_prompt, messages)

    return {
        "reply": reply,
        "updated_history": messages + [
            {"role": "assistant", "content": reply}
        ],
    }