"""Verification tools for Houdini — screenshot compare, scene diff."""

from __future__ import annotations

import json
from pathlib import Path

from houdini_mcp.server import mcp, houdini
from houdini_mcp.utils import obtain, obtain_list, node_to_dict


@mcp.tool()
def compare_screenshots(image_a: str, image_b: str) -> dict:
    """Compare two images using SSIM (structural similarity).

    Args:
        image_a: Path to the first image.
        image_b: Path to the second image.

    Returns:
        Dict with SSIM score (1.0 = identical) and difference info.
    """
    from PIL import Image
    import numpy as np
    from skimage.metrics import structural_similarity as ssim

    img_a = np.array(Image.open(image_a).convert("RGB"))
    img_b = np.array(Image.open(image_b).convert("RGB"))

    if img_a.shape != img_b.shape:
        img_b_resized = np.array(Image.open(image_b).convert("RGB").resize(
            (img_a.shape[1], img_a.shape[0])
        ))
        img_b = img_b_resized

    score = ssim(img_a, img_b, channel_axis=2)

    return {
        "ssim": round(score, 4),
        "identical": score > 0.99,
        "image_a": image_a,
        "image_b": image_b,
    }


@mcp.tool()
def export_node_network(path: str = "/obj", output_file: str | None = None) -> dict:
    """Export node network structure to JSON.

    Args:
        path: Root path to export from.
        output_file: Optional file path to save JSON.

    Returns:
        Dict with the node network structure.
    """
    hou = houdini.hou
    node = hou.node(path)
    if node is None:
        raise ValueError(f"Node not found: {path}")

    def _export_node(n, depth=0):
        result = node_to_dict(n)
        result["inputs"] = []
        for i, inp in enumerate(n.inputs()):
            if inp is not None:
                result["inputs"].append({"index": i, "path": obtain(inp.path())})
        result["outputs"] = [obtain(o.path()) for o in n.outputs()]

        if depth < 10:
            children = [_export_node(c, depth + 1) for c in n.children()]
            if children:
                result["children"] = children
        return result

    network = _export_node(node)

    if output_file:
        Path(output_file).write_text(
            json.dumps(network, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"exported": output_file, "root": path}

    return network


@mcp.tool()
def get_scene_diff(state_a: str, state_b: str) -> dict:
    """Compare two exported scene states (JSON files).

    Args:
        state_a: Path to the first scene state JSON.
        state_b: Path to the second scene state JSON.

    Returns:
        Dict with added, removed, and modified nodes.
    """
    a = json.loads(Path(state_a).read_text(encoding="utf-8"))
    b = json.loads(Path(state_b).read_text(encoding="utf-8"))

    def _flatten(node, result=None):
        if result is None:
            result = {}
        path = node.get("path", "")
        result[path] = {k: v for k, v in node.items() if k != "children"}
        for child in node.get("children", []):
            _flatten(child, result)
        return result

    flat_a = _flatten(a)
    flat_b = _flatten(b)

    added = [p for p in flat_b if p not in flat_a]
    removed = [p for p in flat_a if p not in flat_b]
    modified = []
    for p in flat_a:
        if p in flat_b and flat_a[p] != flat_b[p]:
            modified.append({"path": p, "before": flat_a[p], "after": flat_b[p]})

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "total_changes": len(added) + len(removed) + len(modified),
    }
