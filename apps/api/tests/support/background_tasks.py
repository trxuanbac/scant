import asyncio


class BackgroundTaskTracker:
    def __init__(self):
        self.tasks = set()

    def create_task(self, coroutine, *, name=None, context=None):
        task = asyncio.create_task(coroutine, name=name, context=context)
        self.tasks.add(task)
        return task

    async def wait(self):
        tasks = tuple(self.tasks)
        if tasks:
            await asyncio.gather(*tasks)

    async def close(self):
        tasks = tuple(self.tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
