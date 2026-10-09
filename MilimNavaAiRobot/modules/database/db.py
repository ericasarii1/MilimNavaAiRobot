# ══════════════════════════════════════════════════════════════════
#   DATABASE LAYER — MongoDB / Redis / PostgreSQL
#   Write-through ke semua backend aktif, fallback baca otomatis.
# ══════════════════════════════════════════════════════════════════

import json
import asyncio
import logging
from typing import Optional

log = logging.getLogger("milim.db")


class Database:
    def __init__(self, mongo_uri: str, mongo_db: str, redis_url: str, pg_dsn: str):
        self.mongo = None
        self.redis = None
        self.pg = None
        self.lock = asyncio.Lock()
        self._mem = {}          # fallback in-memory bila tidak ada backend / backend down

        if mongo_uri:
            try:
                from pymongo import MongoClient
                self.mongo = MongoClient(
                    mongo_uri, serverSelectionTimeoutMS=5000, tz_aware=True
                )[mongo_db]
                self.mongo.command("ping")
                log.info("✔ MongoDB Atlas terhubung")
            except Exception as e:
                log.warning(f"MongoDB gagal: {e}")
                self.mongo = None

        if redis_url:
            try:
                import redis.asyncio as aioredis
                self.redis = aioredis.from_url(
                    redis_url, decode_responses=True,
                    socket_connect_timeout=5, socket_timeout=5,
                )
                log.info("✔ Redis terhubung")
            except Exception as e:
                log.warning(f"Redis gagal: {e}")
                self.redis = None

        if pg_dsn:
            try:
                import psycopg2
                self.pg = psycopg2.connect(pg_dsn, connect_timeout=5)
                self.pg.autocommit = True
                self.pg.cursor().execute(
                    "CREATE TABLE IF NOT EXISTS milim_kv (key TEXT PRIMARY KEY, value TEXT)"
                )
                log.info("✔ PostgreSQL terhubung")
            except Exception as e:
                log.warning(f"PostgreSQL gagal: {e}")
                self.pg = None

        if not (self.mongo is not None or self.redis is not None or self.pg is not None):
            log.warning(
                "Tidak ada database backend aktif — memakai fallback "
                "IN-MEMORY (data hilang saat bot restart)."
            )

    @property
    def backends(self):
        b = [b for b in ("mongo", "redis", "pg") if getattr(self, b) is not None]
        return b or ["memory"]

    async def set(self, key: str, value: str):
        async with self.lock:
            self._mem[key] = value
            if self.mongo is not None:
                try:
                    self.mongo.kv.update_one(
                        {"_id": key}, {"$set": {"v": value}}, upsert=True
                    )
                except Exception as e:
                    log.debug(f"mongo set err: {e}")
            if self.redis is not None:
                try:
                    await self.redis.set(key, value)
                except Exception as e:
                    log.debug(f"redis set err: {e}")
            if self.pg is not None:
                try:
                    self.pg.cursor().execute(
                        "INSERT INTO milim_kv (key, value) VALUES (%s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                        (key, value),
                    )
                except Exception as e:
                    log.debug(f"pg set err: {e}")

    async def get(self, key: str) -> Optional[str]:
        async with self.lock:
            if self.mongo is not None:
                try:
                    doc = self.mongo.kv.find_one({"_id": key})
                    if doc:
                        return doc["v"]
                except Exception as e:
                    log.debug(f"mongo get err: {e}")
            if self.redis is not None:
                try:
                    v = await self.redis.get(key)
                    if v:
                        return v
                except Exception as e:
                    log.debug(f"redis get err: {e}")
            if self.pg is not None:
                try:
                    cur = self.pg.cursor()
                    cur.execute("SELECT value FROM milim_kv WHERE key = %s", (key,))
                    row = cur.fetchone()
                    if row:
                        return row[0]
                except Exception as e:
                    log.debug(f"pg get err: {e}")
            return self._mem.get(key)
        return None

    async def delete(self, key: str):
        async with self.lock:
            self._mem.pop(key, None)
            if self.mongo is not None:
                try:
                    self.mongo.kv.delete_one({"_id": key})
                except Exception:
                    pass
            if self.redis is not None:
                try:
                    await self.redis.delete(key)
                except Exception:
                    pass
            if self.pg is not None:
                try:
                    self.pg.cursor().execute("DELETE FROM milim_kv WHERE key = %s", (key,))
                except Exception:
                    pass

    async def keys(self, prefix: str):
        out = []
        async with self.lock:
            if self.redis is not None:
                try:
                    out = [k async for k in self.redis.scan_iter(f"{prefix}*")]
                except Exception:
                    pass
            if not out and self.mongo is not None:
                try:
                    out = [d["_id"] for d in self.mongo.kv.find(
                        {"_id": {"$regex": f"^{prefix}"}})]
                except Exception:
                    pass
            if not out and self.pg is not None:
                try:
                    cur = self.pg.cursor()
                    cur.execute("SELECT key FROM milim_kv WHERE key LIKE %s", (prefix + "%",))
                    out = [r[0] for r in cur.fetchall()]
                except Exception:
                    pass
            if not out:
                out = [k for k in self._mem if k.startswith(prefix)]
        return out

    async def clear_all(self):
        for prefix in ["sess:", "hist:", "state:", "media:", "grp:", "stats:"]:
            for k in await self.keys(prefix):
                await self.delete(k)
