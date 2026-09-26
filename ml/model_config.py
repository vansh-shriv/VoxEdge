"""Keyword-spotting task and model configuration (host side, Phase 3+)."""
import pathlib

KEYWORD = "marvin"                       # Speech Commands v0.02 word
CLASSES = ["silence", "unknown", KEYWORD]
SILENCE, UNKNOWN, KEY = 0, 1, 2

CLIP_SAMPLES = 16000                     # 1 s clips
N_FRAMES = 98                            # windows per clip = CLIP_SAMPLES // HOP - 2 (see features.logmel)
INPUT_SHAPE = (N_FRAMES, 40, 1)          # (time, mel, 1); 40 == feature_config.N_MELS

# Not in the repo: the raw dataset and the cached feature arrays are large.
DATA_ROOT = pathlib.Path("D:/EmbeddedProjects/datasets")
DATASET_DIR = DATA_ROOT / "speech_commands_v0.02"
CACHE = DATA_ROOT / f"kws_{KEYWORD}_features.npz"

# Model variants: (width, n_depthwise_separable_blocks). Names are used for artifact filenames.
VARIANTS = {"xs": (16, 2), "s": (24, 3), "m": (48, 4)}

ARTIFACTS = pathlib.Path(__file__).resolve().parent / "artifacts"
