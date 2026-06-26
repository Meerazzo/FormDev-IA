from __future__ import annotations

import logging
from typing import Any

from db.models.ai_interaction import AIInteraction
from db.session import SessionLocal

logger = logging.getLogger("formdev_ia_api")


def _safe_commit(session) -> None:
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def _ai_extra(
    *,
    request_id: str | None,
    project: str,
    client_id: str | None,
    endpoint: str,
    feature: str,
    status_code: int,
    pipeline_name: str | None,
    pipeline_version: str | None,
    prompt_version: str | None,
    source_ref: str | None,
    model_requested: str | None = None,
    model_used: str | None = None,
    finish_reason: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    latency_ms: float | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    app_module = "surveys" if feature.startswith("survey") else feature
    return {
        "event_type": "ai_interaction",
        "service_name": "formdev-api",
        "request_id": request_id or "-",
        "project": project,
        "client_id": client_id or "-",
        "app_module": app_module,
        "feature": feature,
        "endpoint": endpoint,
        "status_code": status_code,
        "status_family": f"{status_code // 100}xx",
        "is_error": status_code >= 400,
        "pipeline_name": pipeline_name or "-",
        "pipeline_version": pipeline_version or "-",
        "prompt_version": prompt_version or "-",
        "source_ref": source_ref or "-",
        "model_requested": model_requested or "-",
        "model_used": model_used or "-",
        "finish_reason": finish_reason or "-",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": latency_ms,
        "error_type": error_type or "-",
    }


def log_ai_interaction_success(
    *,
    request_id: str | None,
    project: str,
    client_id: str | None,
    endpoint: str,
    feature: str,
    model_requested: str | None,
    model_used: str | None,
    input_text: str | None,
    messages_json: list[dict[str, Any]] | None,
    request_params_json: dict[str, Any] | None,
    output_text: str | None,
    response_json: dict[str, Any] | None,
    finish_reason: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    latency_ms: float | None,
    status_code: int,
    pipeline_name: str | None = None,
    pipeline_version: str | None = None,
    prompt_version: str | None = None,
    source_ref: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    session = SessionLocal()
    try:
        row = AIInteraction(
            request_id=request_id,
            project=project,
            client_id=client_id,
            endpoint=endpoint,
            feature=feature,
            model_requested=model_requested,
            model_used=model_used,
            input_text=input_text,
            messages_json=messages_json,
            request_params_json=request_params_json,
            output_text=output_text,
            response_json=response_json,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            status_code=status_code,
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            prompt_version=prompt_version,
            source_ref=source_ref,
            metadata_json=metadata_json,
        )
        session.add(row)
        _safe_commit(session)
        logger.info(
            "ai interaction completed",
            extra=_ai_extra(
                request_id=request_id,
                project=project,
                client_id=client_id,
                endpoint=endpoint,
                feature=feature,
                model_requested=model_requested,
                model_used=model_used,
                finish_reason=finish_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                status_code=status_code,
                pipeline_name=pipeline_name,
                pipeline_version=pipeline_version,
                prompt_version=prompt_version,
                source_ref=source_ref,
            ),
        )
    except Exception:
        logger.exception(
            "interaction_log_error type=error  request_id=%s endpoint=%s",
            request_id,
            endpoint,
        )
    finally:
        session.close()


def log_ai_interaction_error(
    *,
    request_id: str | None,
    project: str,
    client_id: str | None,
    endpoint: str,
    feature: str,
    model_requested: str | None,
    input_text: str | None,
    messages_json: list[dict[str, Any]] | None,
    request_params_json: dict[str, Any] | None,
    status_code: int,
    error_type: str | None,
    error_message: str | None,
    pipeline_name: str | None = None,
    pipeline_version: str | None = None,
    prompt_version: str | None = None,
    source_ref: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    session = SessionLocal()
    try:
        row = AIInteraction(
            request_id=request_id,
            project=project,
            client_id=client_id,
            endpoint=endpoint,
            feature=feature,
            model_requested=model_requested,
            input_text=input_text,
            messages_json=messages_json,
            request_params_json=request_params_json,
            status_code=status_code,
            error_type=error_type,
            error_message=error_message,
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            prompt_version=prompt_version,
            source_ref=source_ref,
            metadata_json=metadata_json,
        )
        session.add(row)
        _safe_commit(session)
        logger.error(
            "ai interaction failed",
            extra=_ai_extra(
                request_id=request_id,
                project=project,
                client_id=client_id,
                endpoint=endpoint,
                feature=feature,
                model_requested=model_requested,
                model_used=None,
                status_code=status_code,
                pipeline_name=pipeline_name,
                pipeline_version=pipeline_version,
                prompt_version=prompt_version,
                source_ref=source_ref,
                error_type=error_type,
            ),
        )
    except Exception as e:
        logger.exception(
            "interaction_log_error type=error  request_id=%s endpoint=%s error=%s",
            request_id,
            endpoint,
            str(e),
        )
    finally:
        session.close()
