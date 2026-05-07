import json
import traceback

from app.db import SessionLocal
from app.models import GenerationJob, ProductSnapshot, Shop, utcnow
from app.schemas import GenerateCopyRequest
from app.services.copywriter import generate_product_copy
from app.services.shopify import get_product, normalize_product_node, update_product_copy
from app.services.usage import record_usage
from app.worker import celery_app


@celery_app.task(name="app.workers.tasks.generate_copy_task", autoretry_for=(TimeoutError,), retry_backoff=True, max_retries=3)
def generate_copy_task(job_id: str) -> str:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return "missing_job"
        job.status = "running"
        job.error = None
        db.add(job)
        db.commit()

        shop = db.get(Shop, job.shop_id)
        if not shop:
            raise RuntimeError("Shop not found")

        request = GenerateCopyRequest.model_validate_json(job.input_json)
        product = get_product(shop=shop, product_gid=job.shopify_gid)
        result = generate_product_copy(product, request)

        output = result.model_dump()
        if job.publish:
            updated_product = update_product_copy(
                shop=shop,
                product_gid=job.shopify_gid,
                title=result.title if request.include_title else None,
                description_html=result.description_html,
                meta_title=result.meta_title,
                meta_description=result.meta_description,
                tags=result.tags if request.include_tags else None,
            )
            output["published_product"] = updated_product
            snapshot = db.query(ProductSnapshot).filter_by(
                shop_id=shop.id, shopify_gid=job.shopify_gid
            ).one_or_none()
            incoming = normalize_product_node(shop.id, {**product, **updated_product})
            if snapshot:
                for attr in [
                    "title",
                    "handle",
                    "vendor",
                    "product_type",
                    "status",
                    "tags_json",
                    "description_html",
                    "seo_title",
                    "seo_description",
                    "image_url",
                    "raw_json",
                ]:
                    setattr(snapshot, attr, getattr(incoming, attr))
                snapshot.synced_at = utcnow()
            else:
                db.add(incoming)

        job.output_json = json.dumps(output, ensure_ascii=False)
        job.status = "succeeded"
        job.credits_charged = 1
        record_usage(db, user_id=job.user_id, shop_id=job.shop_id, job_id=job.id, credits=1)
        db.add(job)
        db.commit()
        return "succeeded"
    except Exception as exc:  # Keep failed jobs inspectable for operators.
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job:
            job.status = "failed"
            job.error = f"{exc}\n{traceback.format_exc(limit=5)}"
            db.add(job)
            db.commit()
        raise
    finally:
        db.close()
