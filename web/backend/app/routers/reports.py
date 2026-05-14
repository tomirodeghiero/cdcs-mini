"""Report endpoints.

Both routes hand off to the same ``ReportService`` + ``Reporter``
pair that FastAPI injects. To add another input shape (tarball, stdin
stream, git ref, ...) drop in another ``@router.post`` here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from web.backend.app.dependencies import ReporterDep, ServiceDep
from web.backend.app.schemas import FromSourceRequest, ReportResponse
from web.backend.app.settings import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/reports", tags=["Reports"])

PythonFile = Annotated[UploadFile, File(..., description="Python source file")]


@router.post(
    "/from-source",
    response_model=ReportResponse,
    summary="Analyze inline source code",
    description=(
        "Run the deterministic analyzer against a Python source string.\n\n"
        "The response is identical to what the `cdcs-mini` CLI writes "
        "when given the same input."
    ),
    responses={
        200: {
            "description": "Report generated. May still include diagnostics under each function.",
        },
        422: {
            "description": "Request body fails schema validation.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "string_too_long",
                                "loc": ["body", "source"],
                                "msg": "String should have at most 1000000 characters",
                            }
                        ]
                    }
                }
            },
        },
    },
)
def from_source(
    payload: FromSourceRequest,
    service: ServiceDep,
    reporter: ReporterDep,
) -> ReportResponse:
    report = service.build_report(payload.source, filename=payload.filename)
    return ReportResponse(report=reporter.to_dict(report))


@router.post(
    "/from-file",
    response_model=ReportResponse,
    summary="Analyze an uploaded .py file",
    description=(
        "Multipart upload of a single `.py` file (UTF-8, ≤ 1 MB). "
        "Returns the same shape as `/reports/from-source`."
    ),
    responses={
        200: {"description": "Report generated."},
        400: {
            "description": "File rejected by validation.",
            "content": {
                "application/json": {
                    "examples": {
                        "wrong_extension": {
                            "summary": "Non-.py extension",
                            "value": {"detail": "only .py files are accepted"},
                        },
                        "not_utf8": {
                            "summary": "Invalid encoding",
                            "value": {"detail": "file must be UTF-8 encoded"},
                        },
                    }
                }
            },
        },
        413: {
            "description": "Upload exceeds the 1 MB cap.",
            "content": {"application/json": {"example": {"detail": "file too large"}}},
        },
    },
)
async def from_file(
    file: PythonFile,
    service: ServiceDep,
    reporter: ReporterDep,
) -> ReportResponse:
    if not (file.filename or "").endswith(".py"):
        raise HTTPException(status_code=400, detail="only .py files are accepted")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="file must be UTF-8 encoded") from exc

    report = service.build_report(source, filename=file.filename or "input.py")
    return ReportResponse(report=reporter.to_dict(report))
