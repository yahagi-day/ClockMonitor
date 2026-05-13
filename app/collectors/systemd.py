import asyncio

from app import config
from app.collectors.base import PeriodicCollector


class SystemdCollector(PeriodicCollector):
    name = "systemd"
    interval = config.SYSTEMD_INTERVAL

    async def tick(self, storage) -> None:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", *config.SERVICES,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        lines = stdout.decode().strip().splitlines()

        services = {
            svc: (lines[i].strip() if i < len(lines) else "unknown")
            for i, svc in enumerate(config.SERVICES)
        }

        non_active = [s for s, st in services.items() if st != "active"]
        if len(non_active) == 0:
            health = "green"
        elif len(non_active) == 1:
            health = "amber"
        else:
            health = "red"

        storage.set_snapshot("systemd", {"services": services}, health)
