"""ai-worker-ds services package.

Services are async coroutines that supervise side-effects: publishing
embeddings to Redis, syncing track lifecycle events, etc. Each runs
as a long-lived asyncio task spawned from app.main during startup.
"""
