## Video-Index → Harbor Adapter

## Overview

Video-Index is a curated meta-benchmark of hard multiple-choice questions about videos. Every question asks about a
silent video and offers 4 to 16 lettered options; the score is accuracy. The questions come from 76 public video
benchmarks and were selected because shortcut attackers (options alone, question text, earlier items, single frames,
shuffled frames) could not answer them.

- **Dataset size:** 840 Harbor tasks, one per question of the released Video-Index test set
  ([Video-Index/Video-Index](https://huggingface.co/datasets/Video-Index/Video-Index), `items/test.jsonl`), 210 per
  capability group (perception, temporal, spatial / physical, reasoning / knowledge). No question is excluded.
- **Optional blind set:** `--protocol blind` writes 3,360 tasks (each question under four fixed option permutations,
  no video), the text-only control of the paper.
- **Provenance:** paper [arXiv:2610.00960](https://arxiv.org/abs/2610.00960), code
  [Espere-1119-Song/Video-Index](https://github.com/Espere-1119-Song/Video-Index). The videos keep the licenses of
  their source benchmarks; see `LICENSE.md` in the dataset repository.
- **Main adaptations:** the prompt is the one of the paper's agentic runs; the answer letter is written to
  `/app/answer.txt` instead of being returned as structured JSON; paths are absolute under `/app`.

## What is Video-Index?

Video-Index ([Song et al., 2026](https://arxiv.org/abs/2610.00960)) audits 115 video benchmarks with an "attack
pyramid" of shortcut attacks and keeps the items that no attacker solves. Its released set holds the 840 hardest
verified items, 210 per capability group and one per video, from 76 sources. The paper evaluates open-source video
models on sampled frames and proprietary agents (Claude Code, Codex, Gemini CLI) that inspect the video file with
their own tools. The metric is accuracy: an item counts as correct when the chosen letter is the marked option.
Runs that time out or fail count as wrong.

## Adapter Features

- Loads the questions from the Hugging Face dataset at a pinned revision (`--revision`, default: current commit).
- Video delivery at image build time from the pinned dataset revision (`ADD`), or embedded into each task with
  `--embed-videos` for offline registries; the task container ships ffmpeg, ffprobe, OpenCV, Pillow and NumPy.
- Prompt taken from the paper's agentic runs (system and user prompt merged into `instruction.md`), including the
  per-video description (duration, resolution, frame rate, frame count) stored in `src/video_index/data/video_meta.json`.
- Deterministic verifier: reward 1 when `/app/answer.txt` starts with the marked letter (`B`, `(B)`, `b.` and
  `B. text` are accepted), else 0.
- Oracle solution that writes the marked letter.
- `task.toml` metadata for analysis: source benchmark, item id, capability group, fine category, duration, chance.
- Network: the agent may reach model API hosts only (`allowlist`); the verifier runs without network.

## Generated Task Structure

```
video-index/
├── {task_id}/
│   ├── task.toml                 # Task configuration and metadata
│   ├── instruction.md            # Question, options, video description, answer location
│   ├── environment/
│   │   └── Dockerfile            # python:3.12-slim + ffmpeg/OpenCV/Pillow/NumPy; video at /app/video.mp4
│   ├── solution/
│   │   └── solve.sh              # Oracle: writes the marked letter
│   └── tests/
│       └── test.sh               # Writes 1 or 0 to /logs/verifier/reward.txt
```

Adapter code:

```
src/video-index/
├── README.md
├── adapter_metadata.json
├── parity_experiment.json
├── pyproject.toml
├── run_video-index.yaml
└── src/video_index/
    ├── __init__.py
    ├── adapter.py
    ├── main.py
    ├── data/
    │   └── video_meta.json
    └── task-template/
        ├── task.toml
        ├── instruction.md
        ├── instruction_blind.md
        ├── environment/
        │   ├── Dockerfile
        │   └── Dockerfile.blind
        ├── solution/
        │   └── solve.sh
        └── tests/
            └── test.sh
```

## Run Evaluation / Harness

### Running with Datasets Registry

After the dataset is published:

```bash
# Oracle agent (reference solution)
harbor run -d video-index/video-index

# A specific agent and model
harbor run -d video-index/video-index -a claude-code -m "<model_name>"
```

### Using Job Configurations

```bash
# From the repository root, after generating the tasks into datasets/video-index
harbor run -c src/video-index/run_video-index.yaml
harbor run -p datasets/video-index -a claude-code -m "<model_name>"

# Resume a previously started job
harbor job resume -p /path/to/jobs/directory
```

Results are saved in `jobs/` by default (`jobs_dir` in the YAML config). Accuracy is the mean reward; for a
per-group breakdown, group the rewards by `metadata.capability_group` of each `task.toml`. For the blind set,
average the four tasks of each question (`metadata.item_id`) first, then average over questions.

### Running Individual Trial

```bash
harbor trial start -p datasets/video-index/<task_id>
harbor trial start -p datasets/video-index/<task_id> -a claude-code -m "<model_name>"
```

## Usage: Create Task Directories

```bash
cd src/video-index
uv sync
uv run video-index --output-dir ../../datasets/video-index
uv run video-index --output-dir ../../datasets/video-index-blind --protocol blind
```

Available flags:
- `--output-dir`: directory to write generated tasks (default `datasets/video-index` at the repository root)
- `--limit`: generate only the first N tasks
- `--overwrite`: overwrite existing tasks
- `--task-ids`: only generate these task ids (item ids or sanitized task ids)
- `--protocol`: `video` (default) or `blind`
- `--source`: dataset id on the Hugging Face Hub (default `Video-Index/Video-Index`) or a local directory with
  `items/test.jsonl` and `videos/`
- `--revision`: dataset revision to pin
- `--embed-videos`: copy each video into its task instead of downloading it at build time

## Comparison with Original Benchmark (Parity)

Parity has not been run yet; the plan will be agreed with the Harbor team before any run. The paper's agentic
results come from Claude Code and Codex CLI sessions, one per question, so the original side can use the same
agents (scenario 1). The original-side runner will be released in the Video-Index repository.

| Agent | Model | Metric | Number of Runs | Dataset Size | Original Benchmark Performance | Harbor Adapter Performance |
|-------|-------|--------|------------------|--------------|------------------------------|----------------------------|
| pending | pending | Accuracy (%) | pending | 840 | pending | pending |

Reproduction (Harbor side):

```bash
cd src/video-index && uv run video-index --output-dir ../../datasets/video-index
cd ../.. && harbor run -c src/video-index/run_video-index.yaml -a claude-code -m "<model_name>"
```

## Notes & Caveats

- **Prompt.** `instruction.md` reproduces the system prompt and user prompt of the paper's Claude Code runs. Changes:
  the working directory is named (`/app`); "image viewing (Read)" is written as "image viewing" so that it also
  fits agents without a `Read` tool; the answer letter goes to `/app/answer.txt` instead of a JSON object with
  `answer_letter` and `reason`.
- **Video descriptions.** The user prompt describes each video (duration, resolution, frame rate, frame count).
  For 738 questions the descriptions are copied from the original prompts; the other 102 questions were replaced
  after the agentic runs, and their descriptions were computed with ffprobe using the same rule (checked against 30
  original prompts).
- **Original agent settings.** The paper's Claude Code runs restricted the tools to `Bash` and `Read`, used maximum
  reasoning effort, a 1,800-second limit per question, and a bubblewrap sandbox. Parity runs should restrict the
  agent's tools in the same way on both sides.
- **Images are required.** The agent must be able to look at the frames it extracts (Claude Code `Read`, Codex
  `view_image`, Gemini CLI). Text-only agents cannot see the video and score near the blind level.
- **Network.** The agent phase uses an allowlist of model API hosts (`api.anthropic.com`, `api.openai.com`,
  `chatgpt.com`, `generativelanguage.googleapis.com`) because the answers are public; extend `allowed_hosts` if an
  agent needs another endpoint. The environment must support Harbor's `allowlist` mode.
- **Downloads.** The 840 videos total 9.2 GB (median 1.4 MB, largest 98 MB); each image downloads its own video.

## Installation / Prerequisites

- Docker installed and running
- Harbor installed (`uv tool install harbor`)
- Python environment:
  ```bash
  cd src/video-index
  uv sync
  ```
- Agent credentials, for example `ANTHROPIC_API_KEY`, or a Claude subscription token from `claude setup-token`
  exported as `CLAUDE_CODE_OAUTH_TOKEN` (with `CLAUDE_FORCE_OAUTH=1` when an API key is also set); Codex can reuse a
  ChatGPT login with `CODEX_FORCE_AUTH_JSON=1`.

## Troubleshooting

- **Image build fails while downloading the video:** retry, pin `--revision`, or generate with `--embed-videos`.
- **Trial rejected because of the network mode:** the environment does not support `allowlist`; use an environment
  that does (Docker on Linux with nftables, Daytona, Modal, E2B).
- **Agent cannot reach its model:** add the model endpoint to `allowed_hosts` in `task-template/task.toml` and
  regenerate the tasks.

## Citation

```bibtex
@article{song2026videoindex,
  title   = {Video-Index: A Curated Meta-Benchmark for Video Understanding},
  author  = {Song, Enxin and Xu, Yinuo and Yang, Shusheng and Chai, Wenhao and Gu, Jiatao},
  journal = {arXiv preprint arXiv:2610.00960},
  year    = {2026}
}
```

## Authors & Contributions

This adapter is developed and maintained by [Enxin Song](mailto:enxin.song.dut@gmail.com), first author of Video-Index.

**Issues and Contributions:**
- Submit Issues and Pull Requests to the main repository
- Follow the project's coding style and commit guidelines

## Acknowledgement

If the parity experiments use API keys provided through the Harbor team, the following acknowledgement applies:

> API inference compute for running parity tests is generously supported by [2077AI](https://www.2077ai.com/) (https://www.2077ai.com/).
