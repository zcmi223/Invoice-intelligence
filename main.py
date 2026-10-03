"""
invoice-intelligence: invoice images -> Roboflow vision -> spend report.

Usage:
    python main.py --input images/ --output output/report.md        # demo mode
    python main.py --input /path/to/invoices --output report.md     # live mode
                                                                   # (needs .env)

Pipeline:  extract (Roboflow) -> normalize -> analyze -> report.
"""

import argparse
import glob
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # reads .env into the environment; src.config picks it up

from src import config
from src.extract import extract_invoice
from src.normalize import normalize
from src.analyze import analyze
from src.report import render


def main():
    parser = argparse.ArgumentParser(description="Invoice intelligence pipeline")
    parser.add_argument("--input", default="images/",
                        help="folder of invoice images (png/jpg)")
    parser.add_argument("--output", default="output/report.md",
                        help="where to write the Markdown report")
    parser.add_argument("--demo", action="store_true",
                        help="force demo mode even if a Roboflow key is set")
    args = parser.parse_args()

    if args.demo:
        config.LIVE_MODE = False

    paths = sorted(glob.glob(os.path.join(args.input, "*.png")) +
                   glob.glob(os.path.join(args.input, "*.jpg")) +
                   glob.glob(os.path.join(args.input, "*.jpeg")))
    if not paths and not config.LIVE_MODE:
        # Demo mode with no images (e.g. a fresh clone -- PNGs are generated,
        # not committed): create the synthetic samples automatically.
        default_in = os.path.abspath("images")
        if os.path.abspath(args.input) == default_in:
            print("  no sample images found -- generating them ...")
            import runpy
            gen = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "scripts", "generate_samples.py")
            runpy.run_path(gen, run_name="__main__")
            paths = sorted(glob.glob(os.path.join(args.input, "*.png")) +
                           glob.glob(os.path.join(args.input, "*.jpg")) +
                           glob.glob(os.path.join(args.input, "*.jpeg")))
    if not paths:
        sys.exit(f"No invoice images found in {args.input}")

    mode = "live (Roboflow API)" if config.LIVE_MODE else "demo (mocked extraction)"
    print(f"invoice-intelligence | mode: {mode} | {len(paths)} image(s)")

    records = []
    for p in paths:
        print(f"  extracting  {os.path.basename(p)} ...")
        records.append(normalize(extract_invoice(p)))

    parsed = sum(1 for r in records if r["total"] is not None)
    print(f"  normalized  {parsed}/{len(records)} invoice(s)")

    analysis = analyze(records)
    print(f"  anomalies   {len(analysis['anomalies'])} flag(s)")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w") as f:
        f.write(render(analysis, mode))
    print(f"  report      {args.output}")


if __name__ == "__main__":
    main()
