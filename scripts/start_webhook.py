#!/usr/bin/env python3
"""Start Webhook Server script.

This script starts the webhook server for GitHub events.

Usage:
    python scripts/start_webhook.py [--debug] [--port PORT] [--health-check]

Environment Variables:
    GITHUB_TOKEN: GitHub API token (optional, for posting comments)
    WEBHOOK_SECRET: Secret for webhook signature verification
    WEBHOOK_HOST: Host to bind to (default: 0.0.0.0)
    WEBHOOK_PORT: Port to bind to (default: 8765)
"""

import sys
import logging
import signal
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.tracker import Tracker
from src.webhook_server import start_webhook_server


def setup_logging(level: str = "INFO", debug: bool = False) -> None:
    """Setup logging configuration."""
    log_level = logging.DEBUG if debug else getattr(logging, level.upper())

    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "webhook_server.log")
        ]
    )


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Start SkillFlow Webhook Server for real-time GitHub event processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/start_webhook.py
  python scripts/start_webhook.py --debug
  python scripts/start_webhook.py --port 9000
  python scripts/start_webhook.py --health-check

Event Types Processed:
  - issues: Repository requests, bug reports, feature requests
  - pull_request: Skill submissions
  - issue_comment: Comments on issues
  - pull_request_review: PR reviews for approval
        """
    )
    parser.add_argument("--config", default="config/config.yaml", help="Config file path")
    parser.add_argument("--host", help="Server host (overrides config)")
    parser.add_argument("--port", type=int, help="Server port (overrides config)")
    parser.add_argument("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--health-check", action="store_true", help="Run health check and exit")

    args = parser.parse_args()

    setup_logging(args.log_level, args.debug)

    logger = logging.getLogger(__name__)

    # Load configuration
    config = Config(args.config)

    # Override host/port if specified
    if args.host:
        config._config["webhook"]["host"] = args.host
    if args.port:
        config._config["webhook"]["port"] = args.port

    # Check if webhook is enabled
    if not config.webhook_enabled:
        logger.error("Webhook server is disabled in config. Set webhook.enabled: true")
        sys.exit(1)

    # Get host and port
    host = config.webhook_host
    port = config.webhook_port

    # Health check mode
    if args.health_check:
        try:
            import requests
            health_url = f"http://{host}:{port}/webhook/health"
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Webhook server is healthy")
                print(f"  Status: {data.get('status')}")
                print(f"  Service: {data.get('service')}")
                return 0
            else:
                print(f"✗ Webhook server returned status {response.status_code}")
                return 1
        except requests.exceptions.ConnectionError:
            print(f"✗ Cannot connect to webhook server at {health_url}")
            print(f"  Is the server running? Start it with: python scripts/start_webhook.py")
            return 1
        except Exception as e:
            print(f"✗ Health check failed: {e}")
            return 1

    # Check webhook secret
    webhook_secret = os.getenv("WEBHOOK_SECRET") or config.webhook_secret
    if not webhook_secret:
        logger.warning("WEBHOOK_SECRET not set. Webhook signature verification will be disabled.")
        logger.warning("Set WEBHOOK_SECRET environment variable for security.")
    else:
        logger.info("Webhook secret configured - signature verification enabled")

    # Print startup banner
    logger.info("=" * 60)
    logger.info("SkillFlow Webhook Server")
    logger.info("=" * 60)
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"Webhook URL: http://{host}:{port}/webhook/github")
    logger.info(f"Health check: http://{host}:{port}/webhook/health")
    logger.info("")
    logger.info("Event types configured:")
    for event_type in config.get("webhook.event_types", []):
        logger.info(f"  - {event_type}")
    logger.info("")
    logger.info("Event Categories:")
    logger.info("  - repo-request: Repository addition requests")
    logger.info("  - skill-submission: Pull requests with new skills")
    logger.info("  - bug: Bug reports")
    logger.info("  - feature: Feature requests/enhancements")
    logger.info("")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    try:
        start_webhook_server(config, debug=args.debug)
        return 0
    except KeyboardInterrupt:
        logger.info("")
        logger.info("Webhook server stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Webhook server error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
