"""Convert Video-Index questions into Harbor task directories.

Video-Index (arXiv:2610.00960) is a curated meta-benchmark of 840 hard multiple-choice
questions about videos, drawn from 76 public video benchmarks. The questions, options,
answers and videos are released at https://huggingface.co/datasets/Video-Index/Video-Index.

Two protocols are supported:

* ``video`` (default): one task per question. The video is placed at ``/app/video.mp4``
  together with ffmpeg, OpenCV, Pillow and NumPy; the agent inspects it with its own
  tools and writes one option letter to ``/app/answer.txt``.
* ``blind``: question and options only, four option permutations per question fixed by
  ``random.Random(f"42|{item_id}")``. The item score is the mean reward of its four tasks.

Video delivery: by default each task's Dockerfile downloads its video from the dataset
repository at a pinned revision when the image is built; the agent and the verifier run
without network. ``embed_videos=True`` copies the mp4 into the task's ``environment/``
directory instead, for offline registries.
"""

from __future__ import annotations

import ast
import json
import os
import random
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent / "task-template"
VIDEO_META = Path(__file__).parent / "data" / "video_meta.json"
LETTERS = "ABCDEFGHIJKLMNOP"
REPO = "Video-Index/Video-Index"
N_PERM, SEED = 4, 42
PROTOCOLS = ("video", "blind")


def permutations_for(item_id: str, k: int, n_perm: int = N_PERM, seed: int = SEED) -> list[list[int]]:
    rng = random.Random(f"{seed}|{item_id}")
    return [rng.sample(range(k), k) for _ in range(n_perm)]


def sanitize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class Item:
    item_id: str
    benchmark: str
    capability_group: str
    fine_category: str
    question: str
    options: list[str]
    answer_idx: int
    chance: float
    video: str
    duration_s: float

    @classmethod
    def from_row(cls, row: dict) -> "Item":
        options = row["options"]
        if isinstance(options, str):
            options = ast.literal_eval(options)
        return cls(
            item_id=str(row["item_id"]),
            benchmark=row["benchmark"],
            capability_group=row["capability_group"],
            fine_category=row.get("fine_category", ""),
            question=row["question"].strip(),
            options=[str(o).strip() for o in options],
            answer_idx=int(row["answer_idx"]),
            chance=float(row["chance"]),
            video=row["video"],
            duration_s=float(row.get("duration_s") or 0),
        )


def load_items(source: str, revision: str | None) -> tuple[list[Item], str | None, str]:
    """Return (items, local video root or None, resolved revision).

    ``source`` is either a local directory holding ``items/test.jsonl`` and ``videos/``,
    or a dataset repository id on the Hugging Face Hub.
    """
    if os.path.isdir(source):
        path = Path(source) / "items" / "test.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        return [Item.from_row(r) for r in rows], str(Path(source)), revision or "main"
    from huggingface_hub import HfApi, hf_hub_download

    resolved = revision or HfApi().repo_info(source, repo_type="dataset").sha
    path = hf_hub_download(source, "items/test.jsonl", repo_type="dataset", revision=resolved)
    with open(path) as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return [Item.from_row(r) for r in rows], None, resolved


def render(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


class VideoIndexAdapter:
    def __init__(
        self,
        output_dir: Path,
        limit: int | None = None,
        overwrite: bool = False,
        task_ids: list[str] | None = None,
        source: str = REPO,
        revision: str | None = None,
        protocol: str = "video",
        embed_videos: bool = False,
        **kwargs,
    ):
        if protocol not in PROTOCOLS:
            raise ValueError(f"protocol must be one of {PROTOCOLS}")
        self.output_dir = Path(output_dir)
        self.limit = limit
        self.overwrite = overwrite
        self.task_ids = task_ids
        self.source = source
        self.protocol = protocol
        self.embed_videos = embed_videos
        self.items, self.video_root, self.revision = load_items(source, revision)
        self.repo = REPO if os.path.isdir(source) else source
        self.video_meta = json.loads(VIDEO_META.read_text())

    def units(self):
        wanted = set(self.task_ids or [])
        items = [
            it
            for it in self.items
            if not wanted or it.item_id in wanted or self.task_id(it.item_id) in wanted
        ]
        if self.limit:
            items = items[: self.limit]
        for it in items:
            if self.protocol == "video":
                yield it, list(range(len(it.options))), self.task_id(it.item_id)
            else:
                for k, perm in enumerate(permutations_for(it.item_id, len(it.options))):
                    yield it, perm, self.task_id(it.item_id, f"-p{k}")

    @staticmethod
    def task_id(item_id: str, suffix: str = "") -> str:
        return sanitize(item_id) + suffix

    def run(self) -> None:
        written = 0
        for it, perm, task_id in self.units():
            out = self.output_dir / task_id
            if out.exists():
                if not self.overwrite:
                    continue
                shutil.rmtree(out)
            self.write_task(it, perm, task_id, out)
            written += 1
        print(f"wrote {written} task(s) to {self.output_dir} (protocol {self.protocol}, dataset revision {self.revision})")

    def write_task(self, it: Item, perm: list[int], task_id: str, out: Path) -> None:
        (out / "environment").mkdir(parents=True)
        (out / "solution").mkdir()
        (out / "tests").mkdir()
        options = [it.options[j] for j in perm]
        letters = LETTERS[: len(options)]
        answer = letters[perm.index(it.answer_idx)]
        benchmark_name = "video-index" if self.protocol == "video" else "video-index-blind"
        values = dict(
            benchmark_name=benchmark_name,
            task_id=task_id,
            item_id=it.item_id,
            source_benchmark=it.benchmark.replace('"', "'"),
            capability_group=it.capability_group,
            fine_category=it.fine_category,
            duration_s=it.duration_s,
            chance=it.chance,
            protocol=self.protocol,
            answer=answer,
            letters=", ".join(letters),
            letters_compact=letters,
            question=it.question,
            video_meta=self.describe_video(it.item_id),
            options="\n".join(f"{letters[i]}. {o}" for i, o in enumerate(options)),
            keywords=json.dumps(["video-index", "multiple-choice", "video", it.capability_group]),
        )
        instruction = "instruction.md" if self.protocol == "video" else "instruction_blind.md"
        (out / "task.toml").write_text(render((TEMPLATE_DIR / "task.toml").read_text(), values))
        (out / "instruction.md").write_text(render((TEMPLATE_DIR / instruction).read_text(), values))
        for rel in ("solution/solve.sh", "tests/test.sh"):
            (out / rel).write_text(render((TEMPLATE_DIR / rel).read_text(), values))
            os.chmod(out / rel, 0o755)
        dockerfile = "Dockerfile" if self.protocol == "video" else "Dockerfile.blind"
        docker = (TEMPLATE_DIR / "environment" / dockerfile).read_text()
        if self.protocol == "video":
            docker = docker.replace("{video_step}", self.video_step(it, out))
        (out / "environment" / "Dockerfile").write_text(docker)

    def describe_video(self, item_id: str) -> str:
        """Video description used in the prompt of the original agentic runs, e.g.
        "duration 20.0 s, 596x336, 2.0 fps, 40 frames, no audio"."""
        if item_id not in self.video_meta:
            raise KeyError(f"{item_id} has no entry in {VIDEO_META.name}; add its video description first")
        return self.video_meta[item_id]

    def video_step(self, it: Item, out: Path) -> str:
        if not self.embed_videos:
            url = f"https://huggingface.co/datasets/{self.repo}/resolve/{self.revision}/{it.video}"
            return f"ADD {url} /app/video.mp4"
        if self.video_root:
            src = os.path.join(self.video_root, it.video)
        else:
            from huggingface_hub import hf_hub_download

            src = hf_hub_download(self.repo, it.video, repo_type="dataset", revision=self.revision)
        shutil.copy2(os.path.realpath(src), out / "environment" / "video.mp4")
        return "COPY video.mp4 /app/video.mp4"
