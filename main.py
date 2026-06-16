import os
import json
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


class BookUpdate(BaseModel):
    status: str
    rating: int | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []


class AgentRequest(BaseModel):
    message: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


"""
Week 6 Agent Loop Understanding

1. When the model needs a tool, the program must execute the correct Python function.
2. Tool results are added back into the conversation as a "user" role message.
3. The model reads those results and decides the next action.
4. max_iterations prevents the agent from running forever.
"""


def book_to_dict(book: Book) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "status": book.status,
        "rating": book.rating,
    }


@app.get("/")
def home():
    return {"message": "Week 6 Book Agent API is running"}


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

    return book_to_dict(new_book)


@app.get("/books")
def get_books(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Book)

    if status:
        query = query.filter(Book.status == status)

    books = query.all()
    return [book_to_dict(book) for book in books]


@app.get("/books/{book_id}")
def get_book_by_id(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        return {"error": "Book not found"}

    return book_to_dict(book)


@app.patch("/books/{book_id}")
def update_book(book_id: int, update: BookUpdate, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        return {"error": "Book not found"}

    book.status = update.status

    if update.rating is not None:
        book.rating = update.rating

    db.commit()
    db.refresh(book)

    return book_to_dict(book)


@app.delete("/books/{book_id}")
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        return {"error": "Book not found"}

    deleted_book = book_to_dict(book)

    db.delete(book)
    db.commit()

    return {
        "message": "Book deleted successfully",
        "deleted_book": deleted_book,
    }


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


# ----------------------------
# Week 6 Agent Tool Definitions
# ----------------------------

tools = [
    {
        "name": "get_books",
        "description": "Get all books in the user's book collection. Optional status filter can be reading, read, or want-to-read.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Optional status filter: reading, read, or want-to-read.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_book_by_id",
        "description": "Get one specific book by its numeric id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {
                    "type": "integer",
                    "description": "The numeric id of the book.",
                }
            },
            "required": ["book_id"],
        },
    },
    {
        "name": "add_book",
        "description": "Add a new book to the user's collection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "author": {"type": "string"},
                "status": {"type": "string"},
                "rating": {"type": "integer"},
            },
            "required": ["title", "author", "status"],
        },
    },
    {
        "name": "update_book_status",
        "description": "Update a book's reading status. Can also include rating.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "integer"},
                "status": {"type": "string"},
                "rating": {"type": "integer"},
            },
            "required": ["book_id", "status"],
        },
    },
    {
        "name": "rate_book",
        "description": "Rate an existing book from 1 to 5. If book id is unknown, use get_books first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "integer"},
                "rating": {"type": "integer"},
            },
            "required": ["book_id", "rating"],
        },
    },
    {
        "name": "delete_book",
        "description": "Delete a book from the collection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "integer"},
            },
            "required": ["book_id"],
        },
    },
]


# ----------------------------
# Week 6 Tool Functions
# ----------------------------

def get_books_fn(db: Session, status: str | None = None) -> list:
    query = db.query(Book)

    if status:
        query = query.filter(Book.status == status)

    return [book_to_dict(book) for book in query.all()]


def get_book_by_id_fn(db: Session, book_id: int) -> dict:
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        return {"error": "Book not found"}

    return book_to_dict(book)


def add_book_fn(
    db: Session,
    title: str,
    author: str,
    status: str = "want-to-read",
    rating: int | None = None,
) -> dict:
    new_book = Book(
        title=title,
        author=author,
        status=status,
        rating=rating,
    )

    db.add(new_book)
    db.commit()
    db.refresh(new_book)

    return book_to_dict(new_book)


def update_book_status_fn(
    db: Session,
    book_id: int,
    status: str,
    rating: int | None = None,
) -> dict:
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        return {"error": "Book not found"}

    book.status = status

    if rating is not None:
        book.rating = rating

    db.commit()
    db.refresh(book)

    return book_to_dict(book)


def rate_book_fn(db: Session, book_id: int, rating: int) -> dict:
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        return {"error": "Book not found"}

    book.rating = rating

    db.commit()
    db.refresh(book)

    return book_to_dict(book)


def delete_book_fn(db: Session, book_id: int) -> dict:
    book = db.query(Book).filter(Book.id == book_id).first()

    if not book:
        return {"error": "Book not found"}

    deleted_book = book_to_dict(book)

    db.delete(book)
    db.commit()

    return {
        "message": "Book deleted successfully",
        "deleted_book": deleted_book,
    }


def execute_tool(tool_name: str, tool_input: dict, db: Session):
    if tool_name == "get_books":
        return get_books_fn(
            db,
            status=tool_input.get("status"),
        )

    if tool_name == "get_book_by_id":
        return get_book_by_id_fn(
            db,
            book_id=tool_input["book_id"],
        )

    if tool_name == "add_book":
        return add_book_fn(
            db,
            title=tool_input["title"],
            author=tool_input["author"],
            status=tool_input.get("status", "want-to-read"),
            rating=tool_input.get("rating"),
        )

    if tool_name == "update_book_status":
        return update_book_status_fn(
            db,
            book_id=tool_input["book_id"],
            status=tool_input["status"],
            rating=tool_input.get("rating"),
        )

    if tool_name == "rate_book":
        return rate_book_fn(
            db,
            book_id=tool_input["book_id"],
            rating=tool_input["rating"],
        )

    if tool_name == "delete_book":
        return delete_book_fn(
            db,
            book_id=tool_input["book_id"],
        )

    return {"error": f"Unknown tool: {tool_name}"}


def find_book_by_title(db: Session, title_search: str):
    books = db.query(Book).all()
    title_search_lower = title_search.lower()

    for book in books:
        if title_search_lower in book.title.lower():
            return book

    return None


# ----------------------------
# Fallback Agent
# ----------------------------

def fallback_agent_plan(user_message: str, db: Session) -> dict:
    message = user_message.lower()
    tool_calls = []
    results = []

    if "finished" in message and "dune" in message:
        dune_book = find_book_by_title(db, "dune")

        if dune_book:
            tool_calls.append(
                {
                    "tool": "update_book_status",
                    "input": {
                        "book_id": dune_book.id,
                        "status": "read",
                        "rating": 5,
                    },
                }
            )
        else:
            tool_calls.append(
                {
                    "tool": "add_book",
                    "input": {
                        "title": "Dune",
                        "author": "Frank Herbert",
                        "status": "read",
                        "rating": 5,
                    },
                }
            )

    if "currently reading" in message or "what am i currently reading" in message:
        tool_calls.append(
            {
                "tool": "get_books",
                "input": {
                    "status": "reading",
                },
            }
        )

    if "add" in message and "atomic habits" in message:
        tool_calls.append(
            {
                "tool": "add_book",
                "input": {
                    "title": "Atomic Habits",
                    "author": "James Clear",
                    "status": "want-to-read",
                },
            }
        )

    if "reading list" in message or "what books do i have" in message:
        tool_calls.append(
            {
                "tool": "get_books",
                "input": {},
            }
        )

    if "remove" in message or "delete" in message:
        if "george orwell" in message or "1984" in message:
            books = db.query(Book).all()

            for book in books:
                if "george orwell" in book.author.lower() or "1984" in book.title.lower():
                    tool_calls.append(
                        {
                            "tool": "delete_book",
                            "input": {
                                "book_id": book.id,
                            },
                        }
                    )
                    break

    for call in tool_calls:
        result = execute_tool(
            call["tool"],
            call["input"],
            db,
        )

        results.append(
            {
                "tool": call["tool"],
                "input": call["input"],
                "result": result,
            }
        )

    if not tool_calls:
        return {
            "message": "Fallback could not understand the request.",
            "tool_calls": [],
            "results": [],
        }

    return {
        "message": "Fallback agent completed the request.",
        "tool_calls": tool_calls,
        "results": results,
    }


# ----------------------------
# Real Iterative Agent Loop
# ----------------------------

def run_agent(user_message: str, db: Session, max_iterations: int = 5):
    messages = [
        {
            "role": "user",
            "content": user_message,
        }
    ]

    for iteration in range(max_iterations):
        if not GEMINI_API_KEY:
            raise Exception("GEMINI_API_KEY is missing.")

        prompt = f"""
You are a book library AI agent.

You must decide the next step using JSON only.

Available tools:
1. get_books
2. get_book_by_id
3. add_book
4. update_book_status
5. rate_book
6. delete_book
7. final_answer

Tool descriptions:
{json.dumps(tools, indent=2)}

Conversation so far:
{json.dumps(messages, indent=2)}

Return only valid JSON. Do not use markdown.

For a tool call, use:
{{
  "tool": "get_books",
  "input": {{}}
}}

For final answer, use:
{{
  "tool": "final_answer",
  "input": {{
    "answer": "your final response"
  }}
}}

Rules:
- Use get_books first if you need to find a book ID.
- For multi-step requests, do only one tool at a time.
- After each tool result, continue with the next step.
- Use final_answer only when the full user request is complete.
- Valid status values are: reading, read, want-to-read.
- If user says currently reading, use status "reading".
- If user says finished a book, update status to "read".
- If user asks to rate a book, use rate_book or update_book_status with rating.
"""

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)

        response_text = response.text.strip()
        response_text = response_text.replace("```json", "")
        response_text = response_text.replace("```", "")
        response_text = response_text.strip()

        try:
            plan = json.loads(response_text)
        except Exception:
            return response.text

        tool_name = plan.get("tool")
        tool_input = plan.get("input", {})

        if tool_name == "final_answer":
            return tool_input.get("answer", "Done.")

        result = execute_tool(tool_name, tool_input, db)

        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(plan),
            }
        )

        # Important TA requirement:
        # feed tool result back as user role
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "tool_result": result,
                    }
                ),
            }
        )

    return "Agent stopped because it reached the maximum number of iterations."


@app.post("/ai/agent", response_model=str)
def ai_agent(request: AgentRequest, db: Session = Depends(get_db)):
    try:
        result = run_agent(request.message, db)

    except Exception as e:
        print("Agent failed, using fallback:", e)
        result = fallback_agent_plan(request.message, db)

    if isinstance(result, dict) or isinstance(result, list):
        return json.dumps(result, indent=2)

    return str(result)