import asyncio
from fastapi import FastAPI
from apis import auth
from core.database import engine, Base
from apis import websocket
from contextlib import asynccontextmanager
from core.manager import manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # run in background
    task = asyncio.create_task(manager.listen_to_redis())
    yield
    task.cancel()

app=FastAPI(lifespan=lifespan)

# Auto migration
Base.metadata.create_all(bind=engine)

# Endpoints

app.include_router(auth.router, prefix="/auth", tags=["auth"])

app.include_router(websocket.router, tags=["websockets"])