import os
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

_MD_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "AURUM.md")


@router.get("", response_class=PlainTextResponse)
async def get_docs():
    """Serve the AURUM documentation markdown file."""
    try:
        with open(os.path.abspath(_MD_PATH), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "# AURUM Documentation\n\nDocumentation file not found."
