"""
Project configuration.

Live Roboflow mode activates when ROBOFLOW_API_KEY is set (see .env.example).
ROBOFLOW_WORKSPACE and ROBOFLOW_WORKFLOW_ID identify *your* workflow in
*your* workspace -- create the "invoice-extraction" workflow in the Roboflow
app (Input -> OCR block -> Dynamic Crop on detected fields -> Output), then
paste the workspace slug and workflow ID here. Until then, demo mode runs the
full pipeline on the bundled samples.
"""

import os

ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "").strip()
ROBOFLOW_API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com").strip()
ROBOFLOW_WORKSPACE = os.getenv("ROBOFLOW_WORKSPACE", "").strip()
ROBOFLOW_WORKFLOW_ID = os.getenv("ROBOFLOW_WORKFLOW_ID", "invoice-extraction").strip()

LIVE_MODE = bool(ROBOFLOW_API_KEY and ROBOFLOW_WORKSPACE)
