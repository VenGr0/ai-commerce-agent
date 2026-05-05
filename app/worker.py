from celery import Celery

from app.config import settings

celery_app = Celery("commerce_agent", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_routes = {"app.workers.tasks.*": {"queue": "copy_generation"}}
celery_app.conf.task_track_started = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_acks_late = True
celery_app.conf.task_always_eager = settings.CELERY_ALWAYS_EAGER
celery_app.autodiscover_tasks(["app.workers"])
