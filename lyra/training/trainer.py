"""
trainer.py — Training loop with checkpointing, logging, and validation.
"""

import sys
import torch
from torch.utils.data import DataLoader
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.config import (
    TRAIN_DIR,
    VAL_DIR,
    RAW_SCREENSHOTS_DIR,
    CHECKPOINTS_DIR,
)
from lyra.data.dataset import LyraDataset
from lyra.model.model import LyraNet
from lyra.model.losses import LyraLoss
from lyra.training.evaluator import evaluate_model
from lyra.training.visualizer import visualize_predictions


def collate_fn(batch):
    """
    Custom collate function to handle variable number of bounding boxes per screenshot.
    """
    images = []
    targets = {
        "boxes": [],
        "labels": [],
        "screen_state": [],
        "orig_size": []
    }
    
    for img, target in batch:
        images.append(img)
        targets["boxes"].append(target["boxes"])
        targets["labels"].append(target["labels"])
        targets["screen_state"].append(target["screen_state"])
        targets["orig_size"].append(target["orig_size"])
        
    return torch.stack(images, dim=0), {
        "boxes": targets["boxes"],
        "labels": targets["labels"],
        "screen_state": torch.stack(targets["screen_state"], dim=0),
        "orig_size": torch.stack(targets["orig_size"], dim=0)
    }


def train_model(epochs: int = 40, batch_size: int = 8, lr: float = 1e-3):
    # Determine execution device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[TRAINER] Using device: {device}")
    if device.type == "cuda":
        print(f"[TRAINER] GPU: {torch.cuda.get_device_name(0)}")

    # Ensure checkpoints directory exists
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Initialize Datasets & DataLoaders
    print("[TRAINER] Initializing datasets...")
    train_dataset = LyraDataset(data_dir=TRAIN_DIR, raw_images_dir=RAW_SCREENSHOTS_DIR, is_training=True)
    val_dataset = LyraDataset(data_dir=VAL_DIR, raw_images_dir=RAW_SCREENSHOTS_DIR, is_training=False)

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate_fn,
        drop_last=True
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=collate_fn
    )

    print(f"[TRAINER] Train samples: {len(train_dataset)} ({len(train_loader)} batches)")
    print(f"[TRAINER] Val samples:   {len(val_dataset)} ({len(val_loader)} batches)")

    # 2. Instantiate Model, Loss, Optimizer & Scheduler
    model = LyraNet().to(device)
    criterion = LyraLoss().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_val_loss = float("inf")

    # 3. Main Training Loop
    print("\n[TRAINER] Starting training loop...")
    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        epoch_bbox = 0.0
        epoch_conf = 0.0
        epoch_class = 0.0
        epoch_state = 0.0

        for images, targets in train_loader:
            images = images.to(device)
            # Move non-list targets to device
            targets["screen_state"] = targets["screen_state"].to(device)
            # Leave boxes and labels as lists of tensors, but move each individual tensor to device
            targets["boxes"] = [b.to(device) for b in targets["boxes"]]
            targets["labels"] = [l.to(device) for l in targets["labels"]]

            optimizer.zero_grad()
            det_out, state_out = model(images)
            
            loss, loss_details = criterion(det_out, state_out, targets)
            loss.backward()
            optimizer.step()

            epoch_loss += loss_details["loss"]
            epoch_bbox += loss_details["bbox_loss"]
            epoch_conf += loss_details["conf_loss"]
            epoch_class += loss_details["class_loss"]
            epoch_state += loss_details["state_loss"]

        scheduler.step()

        # Compute average training losses for the epoch
        n_batches = len(train_loader)
        avg_loss = epoch_loss / n_batches
        avg_bbox = epoch_bbox / n_batches
        avg_conf = epoch_conf / n_batches
        avg_class = epoch_class / n_batches
        avg_state = epoch_state / n_batches

        # 4. Validation step
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for images, targets in val_loader:
                images = images.to(device)
                targets["screen_state"] = targets["screen_state"].to(device)
                targets["boxes"] = [b.to(device) for b in targets["boxes"]]
                targets["labels"] = [l.to(device) for l in targets["labels"]]

                det_out, state_out = model(images)
                _, loss_details = criterion(det_out, state_out, targets)
                val_loss += loss_details["loss"]

        avg_val_loss = val_loss / len(val_loader) if len(val_loader) > 0 else 0.0

        # Evaluate performance metrics
        metrics = evaluate_model(model, val_loader, device)

        print(
            f"Epoch {epoch:02d}/{epochs:02d} | "
            f"Loss: {avg_loss:.4f} (BBox: {avg_bbox:.4f}, Conf: {avg_conf:.4f}, Class: {avg_class:.4f}, State: {avg_state:.4f}) | "
            f"Val Loss: {avg_val_loss:.4f} | "
            f"State Acc: {metrics['screen_accuracy']:.2%} | "
            f"Det F1: {metrics['det_f1']:.2%}"
        )

        # Save best model checkpoint
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            best_path = CHECKPOINTS_DIR / "best_model.pth"
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "loss": best_val_loss,
            }, best_path)

    # Save latest model checkpoint
    latest_path = CHECKPOINTS_DIR / "latest_model.pth"
    torch.save({
        "epoch": epochs,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "loss": avg_val_loss,
    }, latest_path)

    print(f"\n[TRAINER] Training complete! Best Validation Loss: {best_val_loss:.4f}")
    print(f"[TRAINER] Checkpoints saved to {CHECKPOINTS_DIR}")

    # 5. Run visualizer to inspect final predictions on val set
    print("[TRAINER] Rendering visualization previews...")
    visualize_predictions(model, val_dataset, device, max_images=5)


if __name__ == "__main__":
    train_model(epochs=40, batch_size=8, lr=1e-3)

