# utils/huey_config.py

from huey import RedisHuey
from decouple import config

HUEY = RedisHuey(
    'network_tasks',
    host=config("REDIS_HOST", default="localhost"),
    port=config("REDIS_PORT", cast=int, default=6379),
    password=config("REDIS_PASSWORD", default=None),
    db=config("REDIS_DB", cast=int, default=0),
)

