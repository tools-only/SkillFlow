"""Event Queue management for async webhook event processing.

This module provides an in-memory queue for processing webhook events
asynchronously with support for retry logic and backoff.
"""

import logging
import time
import threading
from queue import Queue, Empty
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable, Dict, Any

from .config import Config
from .tracker import Tracker


logger = logging.getLogger(__name__)


# ========== Data Classes ==========

@dataclass
class QueuedEvent:
    """An event in the processing queue."""
    event_type: str
    repo_name: str
    payload: Dict[str, Any]
    received_at: str
    retry_count: int = 0
    max_retries: int = 3


# ========== Event Queue ==========

class AsyncEventQueue:
    """Asynchronous event queue with retry logic."""

    def __init__(self, config: Config, tracker: Tracker):
        """Initialize async event queue.

        Args:
            config: Configuration object
            tracker: Tracker instance
        """
        self.config = config
        self.tracker = tracker

        self.queue: Queue[QueuedEvent] = Queue()
        self.max_size = config.get("webhook.queue.max_size", 1000)
        self.max_retries = config.get("health_check.max_retries", 3)
        self.workers = config.get("webhook.queue.workers", 2)

        self.worker_threads = []
        self.running = False

        # Event handler callback
        self.event_handler: Optional[Callable] = None

        logger.info(f"AsyncEventQueue initialized (workers={self.workers})")

    def set_event_handler(self, handler: Callable) -> None:
        """Set event handler callback.

        Args:
            handler: Function to call for each event
                     (QueuedEvent) -> Dict[str, Any]
        """
        self.event_handler = handler

    def start(self) -> None:
        """Start worker threads."""
        if self.running:
            logger.warning("Event queue already running")
            return

        self.running = True

        for i in range(self.workers):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"EventQueueWorker-{i}",
                daemon=True
            )
            thread.start()
            self.worker_threads.append(thread)

        logger.info(f"Started {self.workers} event queue worker threads")

    def stop(self) -> None:
        """Stop worker threads."""
        if not self.running:
            return

        logger.info("Stopping event queue workers...")
        self.running = False

        # Wait for workers to finish
        for thread in self.worker_threads:
            thread.join(timeout=5)

        self.worker_threads = []
        logger.info("Event queue workers stopped")

    def _worker_loop(self) -> None:
        """Worker thread loop."""
        logger.info(f"Worker thread {threading.current_thread().name} started")

        while self.running:
            try:
                # Get event with timeout
                try:
                    event = self.queue.get(timeout=1)
                except Empty:
                    continue

                # Process event
                self._process_event(event)

                # Mark task done
                self.queue.task_done()

            except Exception as e:
                logger.error(f"Error in worker loop: {e}")

        logger.info(f"Worker thread {threading.current_thread().name} stopped")

    def _process_event(self, event: QueuedEvent) -> None:
        """Process a single event.

        Args:
            event: QueuedEvent to process
        """
        logger.debug(f"Processing event: {event.event_type} from {event.repo_name}")

        try:
            if self.event_handler:
                # Call handler with event context
                from .webhook_handler import WebhookContext
                context = WebhookContext(
                    event_type=event.event_type,
                    repo_name=event.repo_name,
                    payload=event.payload,
                    received_at=event.received_at,
                )

                result = self.event_handler(context)

                if not result.get("success"):
                    raise Exception(result.get("error", "Handler failed"))

                logger.debug(f"Event processed successfully: {event.event_type}")

            else:
                logger.warning("No event handler set, event ignored")

        except Exception as e:
            logger.error(f"Error processing event: {e}")

            # Retry if max retries not exceeded
            if event.retry_count < event.max_retries:
                event.retry_count += 1
                # Exponential backoff
                delay = min(2 ** event.retry_count, 60)
                time.sleep(delay)

                logger.info(f"Retrying event (attempt {event.retry_count}/{event.max_retries})")
                self.queue.put(event)
            else:
                logger.error(f"Event exceeded max retries: {event.event_type} from {event.repo_name}")

    def add_event(self, event_type: str, repo_name: str,
                  payload: Dict[str, Any], received_at: str) -> bool:
        """Add event to queue.

        Args:
            event_type: Type of event
            repo_name: Repository name
            payload: Event payload
            received_at: Timestamp

        Returns:
            True if event was queued
        """
        if self.queue.qsize() >= self.max_size:
            logger.error(f"Event queue full ({self.max_size}), dropping event")
            return False

        event = QueuedEvent(
            event_type=event_type,
            repo_name=repo_name,
            payload=payload,
            received_at=received_at,
            max_retries=self.max_retries,
        )

        self.queue.put(event)
        logger.debug(f"Added event to queue: {event_type} from {repo_name} (size={self.queue.qsize()})")
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics.

        Returns:
            Dictionary with queue stats
        """
        return {
            "queue_size": self.queue.qsize(),
            "max_size": self.max_size,
            "workers": len(self.worker_threads),
            "running": self.running,
        }


# ========== Backoff Utilities ==========

class ExponentialBackoff:
    """Exponential backoff with jitter."""

    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0,
                 multiplier: float = 2.0, jitter: bool = True):
        """Initialize backoff calculator.

        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            multiplier: Multiplier for each retry
            jitter: Add random jitter to delay
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self.attempt = 0

    def get_delay(self) -> float:
        """Get delay for current attempt.

        Returns:
            Delay in seconds
        """
        delay = min(self.base_delay * (self.multiplier ** self.attempt), self.max_delay)

        if self.jitter:
            import random
            delay *= (0.5 + random.random())

        self.attempt += 1
        return delay

    def reset(self) -> None:
        """Reset attempt counter."""
        self.attempt = 0
