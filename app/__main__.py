"""Package entry point: ``python -m app``.

Lives in its own module rather than under ``if __name__ == "__main__"`` in
:mod:`app.main`, because ``app/__init__.py`` already imports ``app.main`` --
running that module as ``__main__`` would execute it a second time and build a
second FastAPI app. Importing it from here binds the one that already exists.
"""
from app.main import main

main()
