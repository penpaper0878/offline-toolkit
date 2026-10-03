#!/usr/bin/env python3
"""Fetch the AI models into models/ (build time only; the app never downloads).

    python scripts/fetch_models.py

- Real-ESRGAN "realesr-general-x4v3" (BSD-3-Clause), 4x super-resolution for small or blurry images.
  Published only as PyTorch weights; this script reads the checkpoint without PyTorch and writes the
  same network as ONNX (convolutions, PReLU, pixel shuffle, nearest-neighbour skip), which
  onnxruntime runs. tests check the ONNX graph against a NumPy implementation of the network.
- MediaPipe selfie segmenter (Apache-2.0), person masks for cut-outs; OpenCV's DNN module reads it.

Downloads are pinned by SHA-256. models/manifest.json records what was fetched.
"""

from __future__ import annotations

import hashlib
import io
import json
import pickle
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

ESRGAN_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"
ESRGAN_SHA256 = "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292"
SELFIE_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/1/"
              "selfie_segmenter.tflite")
SELFIE_SHA256 = "191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b"


def log(msg: str) -> None:
    print(f"[models] {msg}", flush=True)


def download(url: str, sha256: str, attempts: int = 5) -> bytes:
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
            break
        except Exception as exc:
            if i == attempts - 1:
                raise RuntimeError(f"download failed: {url}: {exc}") from exc
            time.sleep(2 ** (i + 1))
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        sys.exit(f"SHA-256 mismatch for {url}: {got}")
    return data


# ------------------------------------------------------------------ PyTorch checkpoint without PyTorch
_DTYPES = {"FloatStorage": np.float32, "HalfStorage": np.float16, "DoubleStorage": np.float64,
           "LongStorage": np.int64, "IntStorage": np.int32}


def read_torch_checkpoint(data: bytes) -> dict[str, np.ndarray]:
    """state_dict of a zip-format .pth as NumPy arrays (tensors are rebuilt from their storages)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    prefix = z.namelist()[0].split("/")[0]

    class _Storage:
        def __init__(self, name: str):
            self.name = name

    def rebuild(storage, offset, size, stride, *_):
        key, dtype = storage
        raw = np.frombuffer(z.read(f"{prefix}/data/{key}"), dtype=dtype)
        item = raw.itemsize
        return np.lib.stride_tricks.as_strided(raw[offset:], shape=tuple(size),
                                               strides=tuple(s * item for s in stride)).copy()

    class _Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if module == "torch._utils" and name == "_rebuild_tensor_v2":
                return rebuild
            if module == "torch" and name in _DTYPES:
                return _Storage(name)
            if module == "collections" and name == "OrderedDict":
                import collections
                return collections.OrderedDict
            raise pickle.UnpicklingError(f"unexpected object in checkpoint: {module}.{name}")

        def persistent_load(self, pid):
            _, storage_type, key, _location, _numel = pid
            return key, _DTYPES[storage_type.name]

    obj = _Unpickler(io.BytesIO(z.read(f"{prefix}/data.pkl"))).load()
    for k in ("params_ema", "params"):
        if isinstance(obj, dict) and k in obj:
            obj = obj[k]
            break
    return dict(obj)


def srvgg_layers(state: dict[str, np.ndarray]) -> list[tuple[str, tuple]]:
    """SRVGGNetCompact: conv, PReLU, (conv, PReLU) x N, conv -> pixel shuffle(4) + nearest-upsampled input."""
    idx = sorted({int(k.split(".")[1]) for k in state if k.startswith("body.")})
    layers = []
    for i in idx:
        w = state.get(f"body.{i}.weight")
        if w is not None and w.ndim == 4:
            layers.append(("conv", (w.astype(np.float32), state[f"body.{i}.bias"].astype(np.float32))))
        elif w is not None and w.ndim == 1:
            layers.append(("prelu", (w.astype(np.float32),)))
    return layers


def srvgg_numpy(layers, x: np.ndarray, scale: int = 4) -> np.ndarray:
    """Reference forward pass (NCHW float32), used by the tests to check the ONNX graph."""
    out = x
    for kind, params in layers:
        if kind == "conv":
            w, b = params
            n, c, h, wd = out.shape
            pad = np.pad(out, ((0, 0), (0, 0), (1, 1), (1, 1)))
            cols = np.stack([pad[:, :, dy:dy + h, dx:dx + wd] for dy in range(3) for dx in range(3)], axis=2)
            # cols: n, c, 9, h, w ; w: o, c, 3, 3
            out = np.einsum("nckhw,ock->nohw", cols, w.reshape(w.shape[0], w.shape[1], 9)) + b[None, :, None, None]
        else:
            (a,) = params
            out = np.where(out >= 0, out, out * a[None, :, None, None])
    n, c, h, w = out.shape
    r = scale
    out = out.reshape(n, c // (r * r), r, r, h, w).transpose(0, 1, 4, 2, 5, 3).reshape(n, c // (r * r), h * r, w * r)
    base = x.repeat(r, axis=2).repeat(r, axis=3)
    return out + base


def srvgg_onnx(layers, scale: int = 4) -> bytes:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    nodes, inits = [], []
    cur = "input"
    for i, (kind, params) in enumerate(layers):
        if kind == "conv":
            w, b = params
            inits += [numpy_helper.from_array(w, f"w{i}"), numpy_helper.from_array(b, f"b{i}")]
            nodes.append(helper.make_node("Conv", [cur, f"w{i}", f"b{i}"], [f"t{i}"], pads=[1, 1, 1, 1], kernel_shape=[3, 3]))
        else:
            (a,) = params
            inits.append(numpy_helper.from_array(a.reshape(-1, 1, 1), f"a{i}"))
            nodes.append(helper.make_node("PRelu", [cur, f"a{i}"], [f"t{i}"]))
        cur = f"t{i}"
    nodes.append(helper.make_node("DepthToSpace", [cur], ["shuffled"], blocksize=scale, mode="CRD"))
    inits.append(numpy_helper.from_array(np.array([1, 1, scale, scale], np.float32), "scales"))
    nodes.append(helper.make_node("Resize", ["input", "", "scales"], ["base"], mode="nearest"))
    nodes.append(helper.make_node("Add", ["shuffled", "base"], ["output"]))
    graph = helper.make_graph(
        nodes, "realesr_general_x4v3",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, ["n", 3, "h", "w"])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, ["n", 3, "h4", "w4"])], inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], producer_name="offline-toolkit")
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


def main() -> None:
    dest = ROOT / "models"
    dest.mkdir(exist_ok=True)
    manifest = {}
    target = dest / "realesr-general-x4v3.onnx"
    log("Real-ESRGAN realesr-general-x4v3")
    state = read_torch_checkpoint(download(ESRGAN_URL, ESRGAN_SHA256))
    layers = srvgg_layers(state)
    target.write_bytes(srvgg_onnx(layers))
    manifest["superres"] = {"file": target.name, "model": "Real-ESRGAN realesr-general-x4v3", "licence": "BSD-3-Clause",
                            "source": ESRGAN_URL, "sourceSha256": ESRGAN_SHA256, "scale": 4,
                            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    log(f"  {sum(k == 'conv' for k, _ in layers)} convolutions -> {target.name} ({target.stat().st_size / 1e6:.1f} MB)")
    target = dest / "selfie_segmenter.tflite"
    log("MediaPipe selfie segmenter")
    target.write_bytes(download(SELFIE_URL, SELFIE_SHA256))
    manifest["person"] = {"file": target.name, "model": "MediaPipe Selfie Segmenter (float16)", "licence": "Apache-2.0",
                          "source": SELFIE_URL, "sha256": SELFIE_SHA256}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"models in {dest}: {sum(p.stat().st_size for p in dest.iterdir()) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
