"""APScheduler background job scheduler for AURA daily server jobs."""

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

_scheduler: Any = None


def get_scheduler():
    """Return the global BackgroundScheduler instance if running."""
    global _scheduler
    return _scheduler


def setup_scheduler(app, config: dict):
    """Set up and start APScheduler for daily paper fetching, metadata refresh, and email digests."""
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print("Warning: apscheduler not installed. Install with: pip install apscheduler")
        logger.warning("apscheduler not installed. Daily server job scheduler unavailable.")
        return None

    sched_config = config.get("scheduler", {})
    enabled = sched_config.get("enabled", False) or "--scheduler" in sys.argv

    # Stop existing scheduler if running
    if _scheduler is not None:
        try:
            if _scheduler.running:
                _scheduler.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"Error shutting down existing scheduler: {e}")
        _scheduler = None

    if not enabled:
        logger.info("Scheduler is currently disabled in configuration.")
        return None

    try:
        scheduler = BackgroundScheduler()
        hour = int(sched_config.get("fetch_hour", 6))
        minute = int(sched_config.get("fetch_minute", 0))

        def daily_job():
            with app.app_context():
                from aura.web.app import engine

                if not engine:
                    logger.warning("Engine not initialized during scheduled daily job")
                    return

                fetch_config = config.get("fetch", {})
                summaries_config = config.get("summaries", {})
                gen_summaries = summaries_config.get("generate_on_fetch", False)

                max_results = fetch_config.get("max_results", 200)
                days_back = fetch_config.get("days_back", 2)

                logger.info(
                    f"Daily server job starting: fetching max {max_results} papers, days_back={days_back}, categories={engine.categories}"
                )
                count = engine.fetch_new_papers(
                    max_results=max_results,
                    days_back=days_back,
                    generate_summaries=gen_summaries,
                )
                logger.info(f"Daily server job completed: fetched {count} new papers.")

                # Daily email digest execution if email configured
                try:
                    email_conf = config.get("email", {})
                    if email_conf and any(email_conf.values()):
                        from aura.email_digest import send_daily_digest

                        send_daily_digest(engine, config)
                        logger.info("Daily email digest sent successfully.")
                except Exception as e:
                    logger.error(f"Scheduled daily email digest error: {e}")

        scheduler.add_job(
            daily_job,
            "cron",
            hour=hour,
            minute=minute,
            id="daily_fetch_job",
            replace_existing=True,
        )

        # Scheduled ADS metadata refresh
        ads_hour = sched_config.get("ads_refresh_hour")
        if ads_hour is None:
            ads_hour = (hour + 1) % 24
        ads_minute = sched_config.get("ads_refresh_minute", minute)

        def daily_ads_refresh():
            with app.app_context():
                try:
                    from aura.tasks import refresh_ads_metadata_task

                    refresh_ads_metadata_task.delay()
                except Exception as e:
                    logger.error(f"Daily ADS refresh error: {e}")

        scheduler.add_job(
            daily_ads_refresh,
            "cron",
            hour=ads_hour,
            minute=ads_minute,
            id="daily_ads_job",
            replace_existing=True,
        )

        # Scheduled GitHub metadata refresh
        gh_hour = sched_config.get("github_refresh_hour")
        if gh_hour is None:
            gh_hour = (hour + 2) % 24
        gh_minute = sched_config.get("github_refresh_minute", minute)

        def daily_github_refresh():
            with app.app_context():
                try:
                    from aura.tasks import refresh_github_metadata_task

                    refresh_github_metadata_task.delay()
                except Exception as e:
                    logger.error(f"Daily GitHub refresh error: {e}")

        scheduler.add_job(
            daily_github_refresh,
            "cron",
            hour=gh_hour,
            minute=gh_minute,
            id="daily_gh_job",
            replace_existing=True,
        )

        scheduler.start()
        _scheduler = scheduler
        logger.info(
            f"APScheduler started successfully: Daily fetch job set for {hour:02d}:{minute:02d} UTC."
        )
        return _scheduler
    except Exception as e:
        logger.error(f"Failed to initialize APScheduler: {e}")
        return None


def update_scheduler(app, config: dict):
    """Reconfigure and restart scheduler when settings are updated."""
    return setup_scheduler(app, config)
