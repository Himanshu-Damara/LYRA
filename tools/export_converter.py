"""
export_converter.py — Convert Roboflow / CVAT / LabelImg exports to LYRA annotation format.

Supported input formats:
1. CVAT 1.1 XML format (supports both frame tags for screen states and bounding boxes for UI elements)
2. YOLO txt format (normalized x_center, y_center, width, height + classes.txt)
3. Pascal VOC xml format
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lyra.config import (
    RAW_SCREENSHOTS_DIR,
    ANNOTATIONS_DIR,
    UI_ELEMENT_CLASSES,
    SCREEN_STATE_CLASSES,
)


def convert_cvat_xml_to_lyra(
    xml_file: Path,
    output_dir: Path = ANNOTATIONS_DIR,
) -> int:
    """
    Converts CVAT 1.1 for Images XML annotation export file to LYRA JSON files.
    Parses both image-level <tag label="..."> for screen state and <box label="..."> for UI elements.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    converted_count = 0
    
    for img_elem in root.findall("image"):
        img_name = img_elem.attrib.get("name", "")
        base_name = Path(img_name).stem
        width = int(img_elem.attrib.get("width", 720))
        height = int(img_elem.attrib.get("height", 1600))
        
        # Parse screen state classification tag (whole-image label)
        screen_state = "UNKNOWN"
        for tag_elem in img_elem.findall("tag"):
            tag_label = tag_elem.attrib.get("label", "")
            if tag_label in SCREEN_STATE_CLASSES:
                screen_state = tag_label
                break
                
        # Parse bounding boxes
        objects = []
        for box_elem in img_elem.findall("box"):
            label = box_elem.attrib.get("label", "")
            xtl = float(box_elem.attrib.get("xtl", 0))
            ytl = float(box_elem.attrib.get("ytl", 0))
            xbr = float(box_elem.attrib.get("xbr", 0))
            ybr = float(box_elem.attrib.get("ybr", 0))
            
            xmin = max(0, min(int(round(xtl)), width))
            ymin = max(0, min(int(round(ytl)), height))
            xmax = max(0, min(int(round(xbr)), width))
            ymax = max(0, min(int(round(ybr)), height))
            
            objects.append({
                "label": label,
                "bbox": [xmin, ymin, xmax, ymax]
            })
            
        annotation = {
            "filename": f"{base_name}.png",
            "resolution": {"width": width, "height": height},
            "screen_state_tag": screen_state,
            "objects": objects
        }
        
        out_path = output_dir / f"{base_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(annotation, f, indent=2)
            
        converted_count += 1
        
    return converted_count


def convert_yolo_to_lyra(
    yolo_dir: Path,
    classes_file: Optional[Path] = None,
    output_dir: Path = ANNOTATIONS_DIR,
) -> int:
    """
    Converts YOLO format (.txt files) to LYRA JSON annotation files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    class_names = UI_ELEMENT_CLASSES
    if classes_file and classes_file.exists():
        with open(classes_file, "r", encoding="utf-8") as f:
            class_names = [line.strip() for line in f if line.strip()]

    converted_count = 0
    txt_files = list(yolo_dir.glob("*.txt"))
    
    for txt_path in txt_files:
        if txt_path.name == "classes.txt":
            continue
            
        base_name = txt_path.stem
        width, height = 720, 1600
        
        meta_sidecar = RAW_SCREENSHOTS_DIR / f"{base_name}.json"
        screen_state = "UNKNOWN"
        if meta_sidecar.exists():
            with open(meta_sidecar, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                res = meta_data.get("resolution", {})
                width = res.get("width", width)
                height = res.get("height", height)
                screen_state = meta_data.get("screen_state_tag", "UNKNOWN")

        objects = []
        with open(txt_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                
                class_id = int(parts[0])
                xc, yc, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                
                label = class_names[class_id] if class_id < len(class_names) else f"unknown_{class_id}"
                
                xmin = int((xc - w / 2.0) * width)
                ymin = int((yc - h / 2.0) * height)
                xmax = int((xc + w / 2.0) * width)
                ymax = int((yc + h / 2.0) * height)
                
                xmin = max(0, min(xmin, width))
                ymin = max(0, min(ymin, height))
                xmax = max(0, min(xmax, width))
                ymax = max(0, min(ymax, height))
                
                objects.append({
                    "label": label,
                    "bbox": [xmin, ymin, xmax, ymax]
                })
        
        annotation = {
            "filename": f"{base_name}.png",
            "resolution": {"width": width, "height": height},
            "screen_state_tag": screen_state,
            "objects": objects
        }
        
        out_path = output_dir / f"{base_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(annotation, f, indent=2)
            
        converted_count += 1

    return converted_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LYRA Export Converter Utility")
    parser.add_argument("--format", choices=["cvat", "yolo"], default="cvat", help="Input annotation format")
    parser.add_argument("--input", type=str, required=True, help="CVAT annotations.xml file path OR YOLO txt directory")
    parser.add_argument("--classes", type=str, default=None, help="Path to classes.txt file (for YOLO)")
    args = parser.parse_args()

    in_path = Path(args.input)
    cls_path = Path(args.classes) if args.classes else None

    if args.format == "cvat":
        n = convert_cvat_xml_to_lyra(in_path)
        print(f"[CONVERTER] Successfully converted {n} images from CVAT XML export into {ANNOTATIONS_DIR}")
    elif args.format == "yolo":
        n = convert_yolo_to_lyra(in_path, classes_file=cls_path)
        print(f"[CONVERTER] Successfully converted {n} YOLO annotation files to {ANNOTATIONS_DIR}")
