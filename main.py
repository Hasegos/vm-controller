from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from db.session import engine
from db.base import Base
from api.v1.routers import api_router
from core.config import settings

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message" : "CloudForge API Server is running"}