"""
Step 1 -- Extraction.

Sends each invoice image through a Roboflow Workflow and returns a canonical
extraction dict:

    {
        "source_image": str,   # path that was processed
        "mode": "live" | "demo",
        "ocr_text": str,       # full-page OCR text from the workflow
        "regions": [           # detected regions of interest (may be empty)
            {"label": str, "text": str, "bbox": [x, y, w, h]}, ...
        ],
    }

Live mode uses the Roboflow Inference SDK:

    from inference_sdk import InferenceHTTPClient
    client = InferenceHTTPClient(api_url="https://serverless.roboflow.com",
                                 api_key=ROBOFLOW_API_KEY)
    result = client.run_workflow(
        workspace_name=ROBOFLOW_WORKSPACE,
        workflow_id=ROBOFLOW_WORKFLOW_ID,   # e.g. "invoice-extraction"
        images={"image": image_path},       # local path, base64, or https:// URL
        parameters={"confidence": 0.35},
    )

`run_workflow` returns a list with one entry per input image; each entry is a
dict keyed by whatever output names the workflow author declared. We read
`output.keys()` instead of hard-coding names, then map the pieces we need.

Demo mode loads the pre-baked mock in demo/mock_outputs/<name>.json, which has
the same shape a real workflow response would be normalized to -- so the rest
of the pipeline cannot tell the difference.
"""

import json
import os

from . import config

# Where demo mock outputs live, relative to the project root.
_MOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "demo", "mock_outputs")


def _extract_live(image_path):
    """Run the real Roboflow workflow on one image."""
    from inference_sdk import InferenceHTTPClient  # pip install inference-sdk

    client = InferenceHTTPClient(
        api_url=config.ROBOFLOW_API_URL,
        api_key=config.ROBOFLOW_API_KEY,
    )
    result = client.run_workflow(
        workspace_name=config.ROBOFLOW_WORKSPACE,
        workflow_id=config.ROBOFLOW_WORKFLOW_ID,
        images={"image": image_path},
        parameters={"confidence": 0.35},
    )
    output = result[0] if isinstance(result, list) else result

    # Map the workflow's declared outputs onto our canonical shape.
    # Don't hard-code output names: read what the workflow actually returned.
    ocr_text = ""
    regions = []
    for name, value in output.items():
        lname = name.lower()
        if isinstance(value, str) and ("ocr" in lname or "text" in lname):
            ocr_text = value
        elif isinstance(value, list) and ("predict" in lname or "detect" in lname
                                         or "region" in lname):
            for pred in value:
                regions.append({
                    "label": pred.get("class", pred.get("label", "field")),
                    "text": pred.get("text", ""),
                    "bbox": [pred.get("x", 0), pred.get("y", 0),
                             pred.get("width", 0), pred.get("height", 0)],
                })
    # Fallback: some workflows return the OCR string under a generic key.
    if not ocr_text:
        for value in output.values():
            if isinstance(value, str) and len(value) > 50:
                ocr_text = value
                break

    return {
        "source_image": image_path,
        "mode": "live",
        "ocr_text": ocr_text,
        "regions": regions,
    }


def _extract_demo(image_path):
    """Load the pre-baked mock workflow output for a sample image."""
    name = os.path.splitext(os.path.basename(image_path))[0] + ".json"
    mock_path = os.path.join(_MOCK_DIR, name)
    if not os.path.exists(mock_path):
        raise FileNotFoundError(
            f"No mock output for {image_path} ({mock_path}). "
            "Run scripts/generate_samples.py or add your own sample pair."
        )
    with open(mock_path) as f:
        mock = json.load(f)
    outputs = mock["outputs"]
    return {
        "source_image": image_path,
        "mode": "demo",
        "ocr_text": outputs["ocr_text"],
        "regions": outputs.get("regions", []),
    }


def extract_invoice(image_path):
    """Extract one invoice image. Live Roboflow if configured, else demo mock."""
    if config.LIVE_MODE:
        return _extract_live(image_path)
    return _extract_demo(image_path)
