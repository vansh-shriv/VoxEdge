"""DS-CNN keyword-spotting model family (host side).

Only ops with TFLite-Micro int8 kernels: Conv2D, DepthwiseConv2D, Mean (global average pool),
FullyConnected, Softmax. BatchNorm folds into the convs at conversion. Input is the normalised
log-mel patch [N_FRAMES, 40, 1]; normalisation (mean/std from training data) happens outside the
model so the firmware does one affine op before int8 quantisation.
"""
import pathlib, sys
import keras
from keras import layers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from model_config import *  # noqa: F401,F403


def _bn_relu(x):
    return layers.ReLU()(layers.BatchNormalization()(x))


def build_dscnn(width, n_blocks, n_classes=len(CLASSES), input_shape=INPUT_SHAPE, dropout=0.2, name=None):
    inp = keras.Input(shape=input_shape, name="logmel")
    # Strided front end shrinks 98x40 -> 25x20 before the separable blocks (bounds MACs/RAM).
    x = layers.Conv2D(width, (10, 4), strides=(4, 2), padding="same", use_bias=False)(inp)
    x = _bn_relu(x)
    for _ in range(n_blocks):
        x = layers.DepthwiseConv2D((3, 3), padding="same", use_bias=False)(x)
        x = _bn_relu(x)
        x = layers.Conv2D(width, (1, 1), use_bias=False)(x)
        x = _bn_relu(x)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(dropout)(x)
    out = layers.Dense(n_classes, name="logits")(x)
    return keras.Model(inp, out, name=name or f"dscnn_{width}x{n_blocks}")


def count_macs(model):
    """Multiply-accumulates per inference for Conv2D / DepthwiseConv2D / Dense."""
    macs = 0
    for l in model.layers:
        if isinstance(l, layers.Conv2D):
            _, h, w, _ = l.output.shape
            kh, kw = l.kernel_size
            macs += h * w * kh * kw * l.input.shape[-1] * l.filters
        elif isinstance(l, layers.DepthwiseConv2D):
            _, h, w, c = l.output.shape
            kh, kw = l.kernel_size
            macs += h * w * kh * kw * c
        elif isinstance(l, layers.Dense):
            macs += l.input.shape[-1] * l.units
    return macs
