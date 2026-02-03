"""Webhook HTTP Server for GitHub webhook events.

This module provides a Flask-based HTTP server to receive
GitHub webhook events.
"""

import logging
from typing import Optional

from flask import Flask, request, jsonify

from .config import Config
from .tracker import Tracker
from .webhook_handler import WebhookEventHandler, EventQueue
from .webhook_integration import setup_webhook_integration


logger = logging.getLogger(__name__)


# ========== Webhook Server ==========

def create_webhook_server(config: Config, tracker: Tracker) -> Flask:
    """Create Flask app for webhook handling.

    Args:
        config: Configuration object
        tracker: Tracker instance

    Returns:
        Flask application
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.webhook_secret or "skillflow-webhook"

    # Initialize event queue with webhook handler
    event_queue = EventQueue(config, tracker)

    # Setup webhook integration for real-time processing
    repo_name = config.get("issues.repo_name") or config.get("pull_requests.repo_name")
    integration = setup_webhook_integration(
        config=config,
        tracker=tracker,
        webhook_handler=event_queue.handler,
        repo_name=repo_name,
    )
    logger.info("Webhook integration configured")

    @app.route("/webhook/github", methods=["POST"])
    def handle_github_webhook():
        """Handle GitHub webhook events."""
        try:
            # Get headers
            headers = {
                "X-GitHub-Event": request.headers.get("X-GitHub-Event", ""),
                "X-GitHub-Delivery": request.headers.get("X-GitHub-Delivery", ""),
                "X-Hub-Signature-256": request.headers.get("X-Hub-Signature-256", ""),
                "X-GitHub-Event-Type": request.headers.get("X-GitHub-Event-Type", ""),
            }

            # Get raw payload
            payload = request.get_data()

            # Process event
            result = event_queue.add_event(headers, payload)

            # Return response
            status_code = 200 if result.get("success", result.get("status") != "error") else 400
            return jsonify(result), status_code

        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/webhook/health", methods=["GET"])
    def health_check():
        """Health check endpoint."""
        stats = integration.get_stats()
        return jsonify({
            "status": "healthy",
            "service": "skillflow-webhook",
            "stats": stats,
        })

    @app.route("/webhook/pending", methods=["GET"])
    def get_pending():
        """Get pending events count."""
        pending = tracker.get_pending_events()
        return jsonify({
            "pending_count": len(pending),
        })

    @app.route("/webhook/stats", methods=["GET"])
    def get_stats():
        """Get processing statistics."""
        return jsonify(integration.get_stats())

    @app.route("/webhook/process", methods=["POST"])
    def process_events():
        """Process pending events (manual trigger)."""
        result = event_queue.process_pending_events()
        return jsonify(result)

    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors."""
        return jsonify({"status": "error", "error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        logger.error(f"Internal error: {error}")
        return jsonify({"status": "error", "error": "Internal server error"}), 500

    logger.info("Webhook server routes configured")

    return app


# ========== Server Runner ==========

class WebhookServer:
    """Webhook server manager."""

    def __init__(self, config: Config, tracker: Tracker):
        """Initialize webhook server.

        Args:
            config: Configuration object
            tracker: Tracker instance
        """
        self.config = config
        self.tracker = tracker
        self.app = None
        self.host = config.webhook_host
        self.port = config.webhook_port

    def create_app(self) -> Flask:
        """Create Flask application.

        Returns:
            Flask app
        """
        if self.app is None:
            self.app = create_webhook_server(self.config, self.tracker)
        return self.app

    def run(self, debug: bool = False) -> None:
        """Run the webhook server.

        Args:
            debug: Enable debug mode
        """
        if not self.config.webhook_enabled:
            logger.warning("Webhook server is disabled in config")
            return

        app = self.create_app()

        logger.info(f"Starting webhook server on {self.host}:{self.port}")
        logger.info(f"Webhook endpoint: http://{self.host}:{self.port}/webhook/github")

        try:
            app.run(
                host=self.host,
                port=self.port,
                debug=debug,
                use_reloader=False,
            )
        except KeyboardInterrupt:
            logger.info("Webhook server stopped by user")
        except Exception as e:
            logger.error(f"Webhook server error: {e}")
            raise

    def runInBackground(self) -> None:
        """Run webhook server in background thread."""
        import threading

        def _run():
            self.run(debug=False)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        logger.info(f"Webhook server started in background on port {self.port}")


# ========== Standalone Functions ==========

def start_webhook_server(config: Config, debug: bool = False) -> None:
    """Start webhook server (standalone function).

    Args:
        config: Configuration object
        debug: Enable debug mode
    """
    tracker = Tracker(config)
    server = WebhookServer(config, tracker)
    server.run(debug=debug)


if __name__ == "__main__":
    import sys
    from .config import Config

    # Simple command-line interface
    config = Config()

    if "--debug" in sys.argv:
        start_webhook_server(config, debug=True)
    else:
        start_webhook_server(config, debug=False)
