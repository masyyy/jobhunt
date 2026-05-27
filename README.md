# Fulcrum Chat

A full-stack AI agent harness built for rapid customer deployment. PydanticAI backend + Vercel AI SDK frontend — a complete, polished chat application where the only variable is **what the agent can do**.

## Why

Fulcrum's promise is simple: engage with us, and you'll have a working AI application in days, not months.

This template is how we deliver on that. It ships as a **complete chat app** — streaming, conversation history, modern UI, all the bells and whistles already done. When we go to a customer, we don't rebuild the app. We figure out their systems and APIs, then write **skills** — Python modules that give the agent new capabilities.

Write a skill, plug it in, the agent can now query spare parts inventory, look up pricing, search maintenance logs — whatever the customer needs. The app stays clean. The skills are the only customer-specific code.

**The workflow:**
1. Fork the template
2. Meet the customer, learn their systems and APIs
3. Write skills (PydanticAI tools) that connect the agent to their world
4. Deploy — customer has a working product in days

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework with automatic API docs
- **PydanticAI** - AI agent framework with Vercel AI SDK integration
- **PostgreSQL** - Production-ready database (via asyncpg)
- **SQLAlchemy** - Async ORM for database operations
- **Alembic** - Database migration management
- **UV** - Ultra-fast Python package manager

### Frontend
- **React 19** - Latest React with concurrent features
- **TypeScript** - Type safety and enhanced developer experience
- **Vite** - Next-generation frontend build tool
- **Vercel AI SDK** - `@ai-sdk/react` for streaming chat with tool support
- **shadcn/ui** - Polished, accessible UI components
- **TailwindCSS v4** - Latest utility-first CSS framework

## Features

- **Streaming Chat** - Real-time AI responses with the Vercel AI Data Stream Protocol
- **Tool Calls** - Demonstration tools (time, calculator, weather) with UI display
- **Production-Ready Database** - PostgreSQL with Alembic migrations, local dev via Docker Compose
- **Modern UI** - shadcn/ui components with Tailwind CSS
- **Type Safety** - Full TypeScript on frontend, Pydantic on backend

## Project Structure

```
├── backend/
│   ├── api/              # API routes and endpoints
│   ├── core/             # Core business logic and AI agent
│   ├── infrastructure/   # Database and external services
│   └── config.py         # Configuration settings
├── frontend/
│   ├── src/
│   │   ├── components/   # UI components (Chat, ToolCallDisplay)
│   │   │   └── ui/       # shadcn/ui components
│   │   ├── lib/          # Utility functions
│   │   └── pages/        # Page components
│   └── ...
├── main.py               # FastAPI application entry point
├── entrypoint.sh         # Docker entrypoint (migrations + app start)
├── docker-compose.yml    # Local dev PostgreSQL + app
├── start.sh              # Run frontend + backend together
└── pyproject.toml        # Python project configuration
```

## Quick Start

### Prerequisites
- **Python 3.13+** - [Download here](https://www.python.org/downloads/)
- **Node.js 18+** - [Download here](https://nodejs.org/)
- **Docker** - For local PostgreSQL (or a running PostgreSQL instance)
- **UV** - Fast Python package manager
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### Installation

1. **Clone and initialize the project:**
   ```bash
   git clone <your-repo-url>
   cd react-python-chatbot
   ```

2. **Set up Python environment:**
   ```bash
   # Install all dependencies (including dev tools)
   uv sync --all-groups
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env.local
   ```

   Edit `.env.local` and set your OpenAI API key and database URL:
   ```bash
   OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fulcrum
   ```

4. **Start PostgreSQL:**
   ```bash
   docker compose up db -d
   ```

5. **Run database migrations:**
   ```bash
   uv run alembic upgrade head
   ```

6. **Set up frontend:**
   ```bash
   cd frontend
   npm install
   ```

## Development

**Run both (recommended):**
```bash
./start.sh          # start without seed data
./start.sh --seed   # start and seed dummy data (template dev / demos)
```

**Or run separately:**

Backend:
```bash
uv run uvicorn main:app --reload --port 8000
```
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

Frontend (new terminal):
```bash
cd frontend
npm run dev
```
- App: http://localhost:5173

## Demo Tools

The chatbot includes three demonstration tools:

1. **Get Current Time** - Ask "What time is it?"
2. **Calculate** - Ask "Calculate 25 * 4"
3. **Get Weather** - Ask "What's the weather in Tokyo?"

Tool calls are displayed in the chat UI with their inputs and outputs.

## API Endpoints

- `POST /api/chat` - Chat endpoint (Vercel AI Data Stream Protocol)
- `POST /api/conversation` - Create a new conversation
- `GET /api/conversation/latest` - Get the latest conversation
- `GET /api/conversation/history` - Get conversation history with messages
- `GET /docs` - Interactive API documentation

## Configuration

### Backend (`.env.local`)
```bash
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fulcrum
```

### Database Migrations
```bash
# Create a new migration
uv run alembic revision --autogenerate -m "Description"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1
```

## Docker

Run the full stack locally (PostgreSQL + app) with a single command:

```bash
docker compose up -d --build
```

Migrations run automatically on startup via `entrypoint.sh`. The app is available at http://localhost:8000.

### Azure Deployment

Build and push the container image for Azure (linux/amd64):

```bash
docker build --platform linux/amd64 -t crfulcrumdev.azurecr.io/fulcrum-chat:latest .
docker push crfulcrumdev.azurecr.io/fulcrum-chat:latest
```

> **Note:** The `--platform linux/amd64` flag is required when building on Apple Silicon (M-series) Macs, since Azure runs on x86_64.
