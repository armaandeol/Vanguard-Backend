from app import config  # noqa: F401  (loads .env before other modules read it)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import github, repos, users

app = FastAPI(title="DeployIQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(github.router)
app.include_router(repos.router)


@app.get("/")
async def root():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
