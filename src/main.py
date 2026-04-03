"""IITA Agent Runtime."""
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "status": "ok"}
