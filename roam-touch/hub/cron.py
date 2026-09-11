"""Scheduled jobs for the hub -- the "Automations" capability, ported in design
(not code) from openclaw's `src/cron`.

★ A job fires a prompt into a channel on a schedule. It does NOT re-implement
  delivery: it records a held `SENT` event and enqueues the text exactly the way
  `send_endpoint` does for a busy pane, so the existing flush + outcome-hook +
  "reply where the last message came from" machinery carries the answer back.
  A scheduled turn is therefore indistinguishable, downstream, from a typed one.

⚠️ Firing goes through the QUEUE, never a direct `channels.send`. A scheduled
   prompt must never be typed into a pane that is mid-reply or showing a
   selector -- `_flush_idle_queues` already skips both and delivers when the
   pane is free. Bypassing it is the exact bug (typing into a menu) the queue
   exists to prevent.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from starlette.concurrency import run_in_threadpool

import channels as channels_mod
from store import EventKind

log = logging.getLogger("roam.hub.cron")

#: How often the scheduler wakes to look for due jobs. A job fires within this
#: window of its scheduled time -- fine for minute-granularity schedules, and
#: cheap (one indexed query per tick).
TICK_S = 15.0

_INTERVAL_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)
_UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86400}


# ----------------------------------------------------------------- schedule math

def parse_interval(expr: str) -> float:
    """`30s` / `10m` / `1h` / `1d` -> seconds. Raises on anything else."""
    m = _INTERVAL_RE.match(expr or "")
    if not m:
        raise ValueError(f"bad interval {expr!r} -- use 30s, 10m, 1h or 1d")
    return int(m.group(1)) * _UNIT_S[m.group(2).lower()]


def _zone(tz: str) -> timezone | ZoneInfo:
    if not tz:
        return timezone.utc
    try:
        return ZoneInfo(tz)
    except Exception as exc:  # bad IANA name
        raise ValueError(f"unknown timezone {tz!r}") from exc


def _parse_at(expr: str, base: float) -> float:
    """An `at` target: a relative offset (`20m`) from `base`, or an ISO 8601
    timestamp (naive is treated as UTC)."""
    expr = (expr or "").strip()
    if _INTERVAL_RE.match(expr):
        return base + parse_interval(expr)
    dt = datetime.fromisoformat(expr.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def first_run(kind: str, expr: str, tz: str, now: float) -> float:
    """When this job should first fire. Doubles as validation -- it raises
    ValueError on a malformed expr/tz, which the API surfaces as a 400."""
    kind = (kind or "").lower()
    if kind == "at":
        return _parse_at(expr, now)
    if kind == "every":
        return now + parse_interval(expr)
    if kind == "cron":
        base = datetime.fromtimestamp(now, _zone(tz))
        return croniter(expr, base).get_next(datetime).timestamp()
    raise ValueError(f"unknown schedule kind {kind!r} (use at, every or cron)")


def advance(kind: str, expr: str, tz: str, after: float) -> float | None:
    """The next fire strictly after `after`, or None when the job is spent
    (a one-shot `at` has no next)."""
    kind = (kind or "").lower()
    if kind == "at":
        return None
    if kind == "every":
        return after + parse_interval(expr)
    if kind == "cron":
        base = datetime.fromtimestamp(after, _zone(tz))
        return croniter(expr, base).get_next(datetime).timestamp()
    raise ValueError(f"unknown schedule kind {kind!r}")


def describe(job: dict) -> str:
    """A one-line human phrasing of a job's schedule, for the app + logs."""
    kind, expr, tz = job.get("kind"), job.get("expr"), job.get("tz") or ""
    suffix = f" ({tz})" if tz else ""
    if kind == "at":
        return f"once at {expr}"
    if kind == "every":
        return f"every {expr}"
    if kind == "cron":
        return f"cron {expr}{suffix}"
    return f"{kind} {expr}"


# ----------------------------------------------------------------- the runner

async def deliver(app, job: dict) -> tuple[bool, str]:
    """Fire the job's prompt into its channel and record the run. Does NOT touch
    the schedule -- shared by the scheduler and by a manual "run now"."""
    store = app.state.store
    now = time.time()
    job_id = int(job["id"])
    pane_id = job.get("pane_id") or ""
    prompt = job.get("prompt") or ""

    run_id = await run_in_threadpool(store.record_run, job_id, now, "fired", "")

    if not pane_id or not prompt:
        detail = "job has no target channel or prompt"
    else:
        live = await run_in_threadpool(channels_mod.get, pane_id)
        if live is None:
            detail = f"channel {pane_id} is not live"
        else:
            # Record the SENT event now (so it shows in the thread immediately)
            # and enqueue the text; the poll-driven flush types it once the pane
            # is free and the outcome hook delivers the answer -- the same path a
            # message from Nexus takes when the pane is busy.
            store.remember_channel(pane_id, live.label, live.session)
            event = store.append(
                pane_id, EventKind.SENT, prompt,
                meta={"origin": "cron", "job_id": job_id,
                      "job_name": job.get("name") or "", "held": True},
            )
            app.state.broadcaster.publish({"type": "event", "event": event.to_dict()})
            app.state.queued.setdefault(pane_id, []).append(prompt)
            await run_in_threadpool(
                store.finish_run, run_id, "ok", "queued", event.id, None
            )
            log.info("cron job %s (%s) fired into %s", job_id,
                     job.get("name") or "unnamed", pane_id)
            return True, "queued"

    await run_in_threadpool(store.finish_run, run_id, "skipped", detail, None, None)
    log.warning("cron job %s skipped: %s", job_id, detail)
    return False, detail


async def _fire(app, job: dict) -> None:
    """A scheduled firing: deliver, then advance (or delete) the job."""
    store = app.state.store
    now = time.time()
    job_id = int(job["id"])
    await deliver(app, job)

    # Advance the job past this firing. A spent one-shot is deleted when the job
    # asked for it, otherwise it stays (next_run_at NULL = inert but visible).
    try:
        nxt = advance(job.get("kind"), job.get("expr"), job.get("tz") or "", now)
    except ValueError:
        nxt = None  # a job that no longer parses stops firing rather than looping
    if nxt is None and job.get("delete_after_run"):
        await run_in_threadpool(store.delete_job, job_id)
        app.state.broadcaster.publish({"type": "cron", "action": "deleted", "id": job_id})
    else:
        await run_in_threadpool(store.mark_job_ran, job_id, now, nxt)
        updated = await run_in_threadpool(store.get_job, job_id)
        if updated is not None:
            app.state.broadcaster.publish({"type": "cron", "action": "ran", "job": updated})


async def run_scheduler(app) -> None:
    """Wake every TICK_S, fire everything due. One tick's failure never stops
    the loop -- a scheduler that dies silently is worse than a late job."""
    store = app.state.store
    log.info("scheduler started (tick %.0fs)", TICK_S)
    while True:
        try:
            due = await run_in_threadpool(store.due_jobs, time.time())
            for job in due:
                try:
                    await _fire(app, job)
                except Exception:
                    log.exception("cron job %s failed to fire", job.get("id"))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_S)
