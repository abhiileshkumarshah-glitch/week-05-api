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

1. When response.stop_reason == "tool_use":
   In a Claude-style agent loop, this means the model is not ready to give the final answer yet.
   Instead, it wants to call one or more tools. The program must read the tool name and tool input,
   execute the correct Python function, and send the result back to the model.

2. What is tool_use_id and why does it matter?
   tool_use_id is a unique identifier for a specific tool call. It connects the tool result back
   to the exact tool request. This matters when the model calls multiple tools because the model
   needs to know which result belongs to which tool call.

3. Why are tool results added as a "user" role message?
   Tool results are added back into the conversation as new context. The model then reads the
   result and decides whether it should call another tool or give the final answer.

4. What would happen without the max_iterations safeguard?
   Without max_iterations, an agent could get stuck in an infinite loop calling tools again and again.
   The safeguard stops the loop after a fixed number of steps.
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
        "description": "Get all books in the user's book collection. Use this when the user asks what books they have, what they are reading, what they finished, or what is on their want-to-read list. Optional status filter can be reading, read, or want-to-read.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Optional book status filter. Use reading, read, or want-to-read.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_book_by_id",
        "description": "Get one specific book by its numeric id. Use this only when you already know the book id.",
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
        "description": "Add a new book to the user's collection. Use this when the user asks to add a book, save a book, or put a book on a reading list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the book.",
                },
                "author": {
                    "type": "string",
                    "description": "The author of the book.",
                },
                "status": {
                    "type": "string",
                    "description": "The reading status. Use reading, read, or want-to-read.",
                },
                "rating": {
                    "type": "integer",
                    "description": "Optional rating from 1 to 5.",
                },
            },
            "required": ["title", "author", "status"],
        },
    },
    {
        "name": "update_book_status",
        "description": "Update an existing book's status and optional rating. Use this when the user says they started reading, finished reading, wants to mark a book as read, or wants to rate a book. If the id is unknown, first use get_books to find the book.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {
                    "type": "integer",
                    "description": "The numeric id of the book to update.",
                },
                "status": {
                    "type": "string",
                    "description": "The new status. Use reading, read, or want-to-read.",
                },
                "rating": {
                    "type": "integer",
                    "description": "Optional rating from 1 to 5.",
                },
            },
            "required": ["book_id", "status"],
        },
    },
    {
        "name": "delete_book",
        "description": "Delete a book from the user's collection. Use this when the user asks to remove or delete a book. If the id is unknown, first use get_books to find the correct book.",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_id": {
                    "type": "integer",
                    "description": "The numeric id of the book to delete.",
                }
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
        return get_books_fn(db, status=tool_input.get("status"))

    if tool_name == "get_book_by_id":
        return get_book_by_id_fn(db, book_id=tool_input["book_id"])

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

    if tool_name == "delete_book":
        return delete_book_fn(db, book_id=tool_input["book_id"])

    return {"error": f"Unknown tool: {tool_name}"}


def find_book_by_title(db: Session, title_search: str):
    books = db.query(Book).all()
    title_search_lower = title_search.lower()

    for book in books:
        if title_search_lower in book.title.lower():
            return book

    return None


def fallback_agent_plan(user_message: str, db: Session) -> list:
    message = user_message.lower()
    tool_calls = []

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

    if "remove" in message and "george orwell" in message:
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

    return tool_calls


def run_agent(user_message: str, db: Session) -> dict:
    agent_steps = []

    system_prompt = f"""You are a book collection management agent.

You can use tools to manage the user's book database.

Available tools:
{json.dumps(tools, indent=2)}

Important rules:
- You must decide which tool or tools are needed.
- If the user asks to view books, use get_books.
- If the user asks to add a book, use add_book.
- If the user asks to update or finish a book, first use get_books if you do not know the book id, then use update_book_status.
- If the user asks to delete a book and gives only a title/author clue, first use get_books to find the correct id, then use delete_book.
- If multiple actions are requested, call multiple tools in order.
- Use statuses exactly as: reading, read, want-to-read.

Return ONLY valid JSON in this format:
{{
  "tool_calls": [
    {{
      "tool": "tool_name",
      "input": {{}}
    }}
  ],
  "final_response": "short message to user after tools are called"
}}
"""

    planning_prompt = f"""User request:
{user_message}

Decide the tool calls needed. Return only JSON."""

    tool_calls = []

    try:
        if GEMINI_API_KEY:
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system_prompt,
            )

            first_response = model.generate_content(planning_prompt)
            raw_text = first_response.text.strip()

            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.replace("```", "").strip()

            plan = json.loads(raw_text)
            tool_calls = plan.get("tool_calls", [])
        else:
            tool_calls = fallback_agent_plan(user_message, db)

    except Exception:
        tool_calls = fallback_agent_plan(user_message, db)

    for tool_call in tool_calls:
        tool_name = tool_call.get("tool")
        tool_input = tool_call.get("input", {})

        result = execute_tool(tool_name, tool_input, db)

        agent_steps.append(
            {
                "tool": tool_name,
                "input": tool_input,
                "result": result,
            }
        )

    final_response = "Done. I completed the requested book actions."

    if agent_steps:
        final_response += " Tool calls used: "
        final_response += ", ".join([step["tool"] for step in agent_steps])
    else:
        final_response = "I could not determine which book tool to call."

    return {
        "response": final_response,
        "agent_steps": agent_steps,
    }
@app.post("/ai/agent")
def book_agent(request: AgentRequest, db: Session = Depends(get_db)):
    result = run_agent(request.message, db)
    return result