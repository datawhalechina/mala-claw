"""Exercise scheduled skills with the real Flask and APScheduler runtimes."""

from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import inspect
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler


class ScheduledAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "app.py"
        spec = importlib.util.spec_from_file_location("mala_scheduler_test_app", source)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        cls.addClassCleanup(sys.modules.pop, spec.name)
        # Import without reading a user's config.json or starting the server.
        previous_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                spec.loader.exec_module(cls.module)
            finally:
                os.chdir(previous_dir)

    def setUp(self):
        self.module.jobs.clear()
        self.module.execution_logs.clear()
        self.scheduler = BackgroundScheduler()
        self.module.scheduler = self.scheduler
        self.scheduler.start(paused=True)
        self.addCleanup(self.scheduler.shutdown, wait=True)
        self.client = self.module.app.test_client()

    def create_job(self, job_id, skill="hello", agent="content_agent", **params):
        response = self.client.post("/api/jobs", json={
            "id": job_id, "name": job_id, "agent_id": agent,
            "skill_id": skill, "cron": "0 0 1 1 *", "params": params,
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.json["status"], "success")

    def run_jobs(self, *job_ids):
        finished = threading.Event()
        events = []

        def on_finished(event):
            if event.job_id not in job_ids:
                return
            events.append(event)
            # The old thread executor returned an unawaited coroutine. Close
            # that object after recording the event, without executing it.
            result = getattr(event, "retval", None)
            if inspect.iscoroutine(result):
                result.close()
            if len(events) == len(job_ids):
                finished.set()

        self.scheduler.add_listener(on_finished, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        for job_id in job_ids:
            # Advance the actual CronTrigger job's due time; do not sleep until
            # the next calendar occurrence or call its function directly.
            self.scheduler.modify_job(job_id, next_run_time=datetime.now(self.scheduler.timezone))
        self.scheduler.resume()
        self.assertTrue(finished.wait(5), "The real scheduler did not finish its jobs")
        self.assertTrue(all(event.exception is None for event in events), events)
        return self.client.get("/api/logs").json

    def test_two_jobs_execute_their_own_skills_and_parameters(self):
        self.create_job("first", message="first greeting")
        self.create_job("second", agent="data_agent", message="second greeting")
        logs = self.run_jobs("first", "second")
        self.assertEqual(len(logs), 2)
        by_job = {entry["job"]: entry for entry in logs}
        for job_id, greeting, agent in (
            ("first", "first greeting", "内容助手"),
            ("second", "second greeting", "数据助手"),
        ):
            with self.subTest(job=job_id):
                self.assertEqual(by_job[job_id]["status"], "success")
                self.assertEqual(by_job[job_id]["type"], "scheduled")
                self.assertEqual(by_job[job_id]["agent"], agent)
                self.assertIn(greeting, by_job[job_id]["result"])

    def test_scheduled_api_skill_awaits_a_real_http_response(self):
        requested_paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requested_paths.append(self.path)
                content = b'{"message":"local async response"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.create_job("http", skill="api_call", agent="data_agent",
                        url=f"http://127.0.0.1:{server.server_port}/fixture")
        logs = self.run_jobs("http")
        self.assertEqual(requested_paths, ["/fixture"])
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["status"], "success")
        self.assertIn("local async response", logs[0]["result"])

    def test_skill_failure_is_logged(self):
        self.create_job("unknown", skill="does_not_exist")
        logs = self.run_jobs("unknown")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["status"], "error")
        self.assertIn("does_not_exist", logs[0]["result"])

    def test_job_listing_tracks_pause_and_resume(self):
        self.create_job("controlled")
        for action, expected_status in ((None, "running"), ("pause", "paused"), ("resume", "running")):
            with self.subTest(action=action):
                if action:
                    response = self.client.post(f"/api/jobs/controlled/{action}")
                    self.assertEqual(response.status_code, 200)
                response = self.client.get("/api/jobs")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json[0]["status"], expected_status)
                self.assertEqual(response.json[0]["id"], "controlled")
                scheduled = self.scheduler.get_job("controlled").next_run_time
                self.assertEqual(scheduled is not None, expected_status == "running")
        self.assertEqual(self.client.delete("/api/jobs/controlled").status_code, 200)
        self.assertEqual(self.client.get("/api/jobs").json, [])


if __name__ == "__main__":
    unittest.main()
