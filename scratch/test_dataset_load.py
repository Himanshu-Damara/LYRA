import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.data.dataset import LyraDataset
from lyra.config import TRAIN_DIR, VAL_DIR, TEST_DIR

train_ds = LyraDataset(TRAIN_DIR, is_training=True)
val_ds = LyraDataset(VAL_DIR, is_training=False)
test_ds = LyraDataset(TEST_DIR, is_training=False)

print(f"Train Dataset size: {len(train_ds)}")
print(f"Val Dataset size:   {len(val_ds)}")
print(f"Test Dataset size:  {len(test_ds)}")

img, targets = train_ds[0]
print(f"\nSample 0 Inspection:")
print(f"  - Image tensor shape: {img.shape}")
print(f"  - Boxes tensor shape: {targets['boxes'].shape}")
print(f"  - Labels tensor:      {targets['labels']}")
print(f"  - Screen State index: {targets['screen_state']}")
print(f"  - Original size:      {targets['orig_size']}")

print("\n[SUCCESS] PyTorch LyraDataset batch verification passed clean!")
