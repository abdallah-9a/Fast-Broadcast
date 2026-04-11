from fastapi import FastAPI
from apis import auth
from core.database import engine, Base

app=FastAPI()

# Auto migration
Base.metadata.create_all(bind=engine)

# Endpoints

app.include_router(auth.router, prefix="/auth", tags=["auth"])
