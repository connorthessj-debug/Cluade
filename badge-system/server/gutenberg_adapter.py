"""
Adapter for sending badge print jobs to Gutenberg.

Gutenberg is a commercial badge printing application. Since different
installations may have different interfaces, this adapter supports
multiple strategies for communicating with it:

1. WATCHED FOLDER: Drop a JSON file into a directory that Gutenberg monitors.
   This is the most universally compatible approach.

2. CLI: Invoke Gutenberg's command-line interface directly.

3. API: Call Gutenberg's REST/SOAP API if available.

4. PRINT: Render a badge image and send it to a printer directly,
   bypassing Gutenberg entirely (fallback).

Configure via the GUTENBERG_MODE environment variable.
"""

import json
import logging
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuration
GUTENBERG_MODE = os.environ.get("GUTENBERG_MODE", "watched_folder")
GUTENBERG_WATCH_DIR = os.environ.get("GUTENBERG_WATCH_DIR", "./badge_queue")
GUTENBERG_CLI_PATH = os.environ.get("GUTENBERG_CLI_PATH", "gutenberg")
GUTENBERG_API_URL = os.environ.get("GUTENBERG_API_URL", "http://localhost:9100")
GUTENBERG_TEMPLATE = os.environ.get("GUTENBERG_TEMPLATE", "visitor_badge")


class GutenbergAdapter:
    """Interface to the Gutenberg badge printing system."""

    def __init__(self):
        self.mode = GUTENBERG_MODE
        self.watch_dir = Path(GUTENBERG_WATCH_DIR)
        self.cli_path = GUTENBERG_CLI_PATH
        self.api_url = GUTENBERG_API_URL
        self.template = GUTENBERG_TEMPLATE

        if self.mode == "watched_folder":
            self.watch_dir.mkdir(parents=True, exist_ok=True)

    def print_badge(self, employee_id: str, name: str, department: str,
                    confidence: float, **extra) -> str:
        """Send a badge print job to Gutenberg.

        Returns a job ID string for tracking.
        """
        job_id = f"j-{uuid.uuid4().hex[:12]}"

        badge_data = {
            "job_id": job_id,
            "template": self.template,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "fields": {
                "employee_id": employee_id,
                "name": name,
                "department": department,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M"),
                **extra,
            },
        }

        if self.mode == "watched_folder":
            return self._print_via_watched_folder(badge_data)
        elif self.mode == "cli":
            return self._print_via_cli(badge_data)
        elif self.mode == "api":
            return self._print_via_api(badge_data)
        elif self.mode == "direct_print":
            return self._print_direct(badge_data)
        else:
            logger.error(f"Unknown Gutenberg mode: {self.mode}")
            raise ValueError(f"Unknown GUTENBERG_MODE: {self.mode}")

    def _print_via_watched_folder(self, badge_data: dict) -> str:
        """Drop a JSON file into Gutenberg's watched folder.

        Gutenberg monitors this directory and picks up new .json files
        to process as print jobs. This is the most reliable integration
        method and works with most commercial badge software.
        """
        job_id = badge_data["job_id"]
        filename = f"{job_id}.json"
        filepath = self.watch_dir / filename

        filepath.write_text(json.dumps(badge_data, indent=2))
        logger.info(f"Badge job {job_id} written to {filepath}")

        return job_id

    def _print_via_cli(self, badge_data: dict) -> str:
        """Invoke Gutenberg's command-line interface.

        Adjust the command and arguments to match your Gutenberg
        installation's CLI syntax.
        """
        job_id = badge_data["job_id"]
        fields = badge_data["fields"]

        cmd = [
            self.cli_path,
            "--template", self.template,
            "--name", fields["name"],
            "--id", fields["employee_id"],
            "--department", fields["department"],
            "--output", f"badge_{job_id}.pdf",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                logger.info(f"Badge job {job_id} printed via CLI")
            else:
                logger.error(f"Gutenberg CLI error: {result.stderr}")
        except FileNotFoundError:
            logger.error(f"Gutenberg CLI not found at {self.cli_path}")
        except subprocess.TimeoutExpired:
            logger.error(f"Gutenberg CLI timed out for job {job_id}")

        return job_id

    def _print_via_api(self, badge_data: dict) -> str:
        """Call Gutenberg's REST API.

        Adjust the endpoint and payload format to match your
        Gutenberg installation's API specification.
        """
        import requests

        job_id = badge_data["job_id"]

        try:
            resp = requests.post(
                f"{self.api_url}/api/print",
                json=badge_data,
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Badge job {job_id} sent via API")
            else:
                logger.error(f"Gutenberg API error {resp.status_code}: {resp.text}")
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot reach Gutenberg API at {self.api_url}")

        return job_id

    def _print_direct(self, badge_data: dict) -> str:
        """Render and print a badge image directly, bypassing Gutenberg.

        Uses badge_template.py to render the badge as a PNG, then
        sends it to the system's default printer.
        """
        from badge_template import render_badge

        job_id = badge_data["job_id"]
        fields = badge_data["fields"]
        output_dir = Path("./output")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{job_id}.png"

        render_badge(
            name=fields["name"],
            employee_id=fields["employee_id"],
            department=fields["department"],
            output_path=str(output_path),
        )

        # Attempt to print (platform-dependent)
        try:
            import platform
            if platform.system() == "Windows":
                os.startfile(str(output_path), "print")
            elif platform.system() == "Darwin":
                subprocess.run(["lpr", str(output_path)], check=True)
            else:
                subprocess.run(["lp", str(output_path)], check=True)
            logger.info(f"Badge {job_id} sent to printer")
        except Exception as e:
            logger.warning(f"Could not auto-print {job_id}: {e}")
            logger.info(f"Badge image saved to {output_path}")

        return job_id
