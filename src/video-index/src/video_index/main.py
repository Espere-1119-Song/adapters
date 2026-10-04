"""
Main entry point for the Video-Index adapter.

Constructs the VideoIndexAdapter defined in adapter.py and calls run() to generate tasks
in the Harbor format at the configured output directory.
"""

import argparse
from pathlib import Path

from .adapter import PROTOCOLS, REPO, VideoIndexAdapter

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[4] / "datasets" / "video-index"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write generated tasks",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate only the first N tasks",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing tasks",
    )
    parser.add_argument(
        "--task-ids",
        nargs="+",
        default=None,
        help="Only generate these task IDs",
    )
    parser.add_argument(
        "--protocol",
        choices=PROTOCOLS,
        default="video",
        help="video: the agent inspects /app/video.mp4 (default); blind: question and options only, four option permutations per question",
    )
    parser.add_argument(
        "--source",
        default=REPO,
        help="Hugging Face dataset id, or a local directory with items/test.jsonl and videos/",
    )
    parser.add_argument(
        "--revision",
        default=None,
        help="Dataset revision to pin (default: the current commit of the dataset repository)",
    )
    parser.add_argument(
        "--embed-videos",
        action="store_true",
        help="Copy each video into its task instead of downloading it when the image is built",
    )
    args = parser.parse_args()

    adapter = VideoIndexAdapter(
        args.output_dir,
        overwrite=args.overwrite,
        limit=args.limit,
        task_ids=args.task_ids,
        source=args.source,
        revision=args.revision,
        protocol=args.protocol,
        embed_videos=args.embed_videos,
    )

    adapter.run()


if __name__ == "__main__":
    main()
