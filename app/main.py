"""The FastAPI app: request/response schemas, routes, LanguageTool setup,
and serving the static web page.

The web page and the API share one origin on purpose, so there's no CORS
middleware here. Static files are mounted after the API router, so they
never end up shadowing the /api routes.

The route handlers below are plain "def", not "async def". python-docx
parsing and LanguageTool calls are both blocking, CPU-heavy work, so
FastAPI runs them in its thread pool and keeps the event loop free. If
these were async instead, one slow request would block every other request
while it ran.
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import (
    APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import pipeline
from app.engine import rules_metadata
from app.pipeline import (
    LanguageToolChecker, UploadRejected, create_language_tool,
)
from app.rules.base import LanguageChecker, RuleConfig

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB_DIR = os.path.join(ROOT, "web")


# --------------------------------------------------------------------------
# Schemas - FindingModel matches the Finding dataclass field for field
# --------------------------------------------------------------------------
class FindingModel(BaseModel):
    rule_id: int
    rule_name: str
    passed: Optional[bool] = Field(
        None, description="None means the rule could not be evaluated.")
    severity: str
    message: str
    evidence: list[str] = []
    locations: list[str] = []
    confidence: str


class RuleMeta(BaseModel):
    id: int
    name: str
    severity: str
    description: str


class Summary(BaseModel):
    total: int
    passed: int
    failed: int
    not_evaluated: int
    errors: int
    warnings: int


class AnalyzeResponse(BaseModel):
    filename: str
    summary: Summary
    findings: list[FindingModel]
    extraction_file: Optional[str] = Field(
        None, description="Path of the saved extraction JSON, relative to the "
                          "project root; null if it could not be written.")
    source_file: Optional[str] = Field(
        None, description="Path of the stored copy of the uploaded .docx, "
                          "relative to the project root; null if it could "
                          "not be written.")
    extraction: Optional[dict] = Field(
        None, description="The extracted Doc model, present only when the "
                          "request asked for it.")


class AnalyzeConfig(BaseModel):
    """Optional client-supplied configuration for an analysis run."""
    required_sections: Optional[list[str]] = None
    ignore_words: Optional[list[str]] = None
    default_authors: Optional[list[str]] = None
    confidentiality_terms: Optional[list[str]] = None
    doc_id_pattern: Optional[str] = None
    readability_min_words: Optional[int] = None
    readability_flesch_min: Optional[float] = None
    readability_fog_max: Optional[float] = None
    title_match_threshold: Optional[float] = None
    date_window: Optional[int] = None

    def to_rule_config(self, filename: str, language_checker) -> RuleConfig:
        cfg = RuleConfig(filename=filename, language_checker=language_checker)
        for field_name, value in self.model_dump(exclude_none=True).items():
            if hasattr(cfg, field_name):
                setattr(cfg, field_name, value)
        return cfg


def finding_to_model(f) -> FindingModel:
    return FindingModel(
        rule_id=f.rule_id, rule_name=f.rule_name, passed=f.passed,
        severity=f.severity, message=f.message, evidence=f.evidence,
        locations=f.locations, confidence=f.confidence,
    )


def summarize(findings) -> Summary:
    passed = sum(1 for f in findings if f.passed is True)
    failed = sum(1 for f in findings if f.passed is False)
    na = sum(1 for f in findings if f.passed is None)
    errors = sum(1 for f in findings
                 if f.passed is False and f.severity == "error")
    warnings = sum(1 for f in findings
                   if f.passed is False and f.severity == "warning")
    return Summary(total=len(findings), passed=passed, failed=failed,
                   not_evaluated=na, errors=errors, warnings=warnings)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
router = APIRouter(prefix="/api")


def _extract(file: UploadFile):
    """Run the upload through the pipeline, turning rejections into HTTP errors."""
    try:
        return pipeline.extract(file.filename, file.file)
    except UploadRejected as exc:
        raise HTTPException(exc.status_code, exc.detail)


def _rel(path: Optional[str]) -> Optional[str]:
    """Turn a saved path into one relative to the project root, for display.
    None stays None."""
    return os.path.relpath(path, ROOT).replace(os.sep, "/") if path else None


def _save_extraction(doc, filename: str) -> tuple[Optional[str], dict]:
    """Turn the Doc into a dict, save it to output/, and return both the
    saved path (relative, for display) and the dict itself."""
    data = pipeline.doc_to_dict(doc)
    return _rel(pipeline.save_extraction_quietly(data, filename)), data


def _save_source(data: bytes, filename: str) -> Optional[str]:
    """Keep a copy of the uploaded .docx next to its extraction, so a run
    can be reproduced later from the exact bytes that produced it."""
    return _rel(pipeline.save_source_quietly(data, filename))


def _config(config: Optional[str], filename: str, checker) -> RuleConfig:
    if not config:
        return AnalyzeConfig().to_rule_config(filename, checker)
    try:
        data = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"Invalid config JSON: {exc}")
    try:
        model = AnalyzeConfig(**data)
    except Exception as exc:
        raise HTTPException(422, f"Invalid config: {exc}")
    return model.to_rule_config(filename, checker)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/rules", response_model=list[RuleMeta])
def get_rules():
    return rules_metadata()


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: Request,
            file: UploadFile = File(...),
            config: Optional[str] = Form(None),
            include_extraction: bool = Form(False)):
    """Run every rule against the upload. The extraction is always saved to
    output/, but it's only included in the response if include_extraction
    is set, since a long document's extracted data is much bigger than its
    findings."""
    name, doc, raw = _extract(file)
    checker = getattr(request.app.state, "language_checker", None)
    cfg = _config(config, name, checker)
    findings = pipeline.analyze(doc, cfg)
    saved, data = _save_extraction(doc, name)
    return AnalyzeResponse(
        filename=name,
        summary=summarize(findings),
        findings=[finding_to_model(f) for f in findings],
        extraction_file=saved,
        source_file=_save_source(raw, name),
        extraction=data if include_extraction else None,
    )


@router.post("/analyze/{rule_id}", response_model=FindingModel)
def analyze_one(rule_id: int, request: Request,
                file: UploadFile = File(...),
                config: Optional[str] = Form(None)):
    name, doc, _raw = _extract(file)      # a single-rule run doesn't save anything
    checker = getattr(request.app.state, "language_checker", None)
    cfg = _config(config, name, checker)
    try:
        return finding_to_model(pipeline.analyze_one(rule_id, doc, cfg))
    except UploadRejected as exc:
        raise HTTPException(exc.status_code, exc.detail)


@router.post("/extract")
def extract_endpoint(file: UploadFile = File(...), save: bool = True):
    """Return the extracted Doc model on its own, with no rules run.
    "saved_to" is where the extraction was written in output/, and
    "source_saved_to" is where the uploaded file itself was saved.
    Pass ?save=false to skip writing either."""
    name, doc, raw = _extract(file)
    if not save:
        return pipeline.doc_to_dict(doc)
    saved, data = _save_extraction(doc, name)
    return {**data,
            "saved_to": saved,
            "source_saved_to": _save_source(raw, name)}


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
def create_app(language_checker: Optional[LanguageChecker] = None) -> FastAPI:
    """Build the app. If language_checker is given (mainly for tests), it's
    used directly; otherwise a real LanguageTool instance is started up as
    part of the app's lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        lock = threading.Lock()
        app.state.lt_lock = lock
        app.state._owned_tool = None
        if language_checker is not None:
            app.state.language_checker = language_checker
        else:
            tool = create_language_tool()
            app.state._owned_tool = tool
            app.state.language_checker = LanguageToolChecker(tool, lock)
        try:
            yield
        finally:
            owned = getattr(app.state, "_owned_tool", None)
            if owned is not None:
                try:
                    owned.close()
                except Exception:
                    pass

    app = FastAPI(
        title="SOP Compliance Checker",
        version="1.0.0",
        description="Library/algorithm-based .docx SOP compliance checker.",
        lifespan=lifespan,
    )

    # register the API routes first, so static files can't shadow them
    app.include_router(router)

    os.makedirs(WEB_DIR, exist_ok=True)
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()


# --------------------------------------------------------------------------
# Direct launch: `python -m app`. uvicorn is imported inside main(), not at
# the top of the file, so importing this module in tests never pulls in the
# whole server.
# --------------------------------------------------------------------------
def main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(
        prog="python -m app",
        description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true",
                        help="restart on source changes (development)")
    args = parser.parse_args()

    # --reload needs an import string to work with. Without --reload we
    # just pass the already-built app object, so this module never gets
    # imported a second time.
    uvicorn.run("app.main:app" if args.reload else app,
                host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
