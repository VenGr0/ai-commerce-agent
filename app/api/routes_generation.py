import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import GenerationJob, Shop, User
from app.schemas import GenerateCopyRequest, GenerationJobOut, UsageOut
from app.services.usage import assert_has_credits, monthly_limit, used_credits
from app.workers.tasks import generate_copy_task

router = APIRouter(prefix="/generation", tags=["generation"])


def get_owned_shop(db: Session, user: User, shop_id: str) -> Shop:
    shop = db.get(Shop, shop_id)
    if not shop or shop.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shop not found")
    if not shop.is_active:
        raise HTTPException(status_code=400, detail="Shop is not active")
    return shop


def serialize_job(job: GenerationJob) -> GenerationJobOut:
    return GenerationJobOut(
        id=job.id,
        user_id=job.user_id,
        shop_id=job.shop_id,
        shopify_gid=job.shopify_gid,
        status=job.status,
        publish=job.publish,
        input=json.loads(job.input_json or "{}"),
        output=json.loads(job.output_json) if job.output_json else None,
        error=job.error,
        credits_charged=job.credits_charged,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/jobs", response_model=GenerationJobOut, status_code=202)
def create_generation_job(
    payload: GenerateCopyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GenerationJobOut:
    get_owned_shop(db, user, payload.shop_id)
    assert_has_credits(db, user, requested_credits=1)

    job = GenerationJob(
        user_id=user.id,
        shop_id=payload.shop_id,
        shopify_gid=payload.shopify_gid,
        publish=payload.publish,
        input_json=payload.model_dump_json(),
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    generate_copy_task.delay(job.id)
    return serialize_job(job)


@router.get("/jobs/{job_id}", response_model=GenerationJobOut)
def get_generation_job(
    job_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GenerationJobOut:
    job = db.get(GenerationJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job)


@router.get("/jobs", response_model=list[GenerationJobOut])
def list_generation_jobs(
    shop_id: str | None = None,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[GenerationJobOut]:
    query = select(GenerationJob).where(GenerationJob.user_id == user.id)
    if shop_id:
        query = query.where(GenerationJob.shop_id == shop_id)
    query = query.order_by(GenerationJob.created_at.desc()).limit(max(1, min(limit, 100)))
    return [serialize_job(job) for job in db.scalars(query)]


@router.get("/usage", response_model=UsageOut)
def usage(user: User = Depends(current_user), db: Session = Depends(get_db)) -> UsageOut:
    used = used_credits(db, user.id)
    limit = monthly_limit(user)
    return UsageOut(
        plan=user.plan,
        used_credits=used,
        monthly_limit=limit,
        remaining_credits=max(0, limit - used),
    )
