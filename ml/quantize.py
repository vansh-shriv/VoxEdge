"""Full-int8 post-training quantisation + float-vs-int8 comparison.  python ml/quantize.py [variant ...]

Writes ml/artifacts/<keyword>_<variant>_int8.tflite (int8 in / int8 out, static shapes) and
<keyword>_results_int8.json. The int8 model is evaluated with the TFLite interpreter on exactly
the same test features as the float model, so the accuracy cost of quantisation is measured
directly. (On-device parity against TFLite-Micro is Phase 4, spec section 4.3.)
"""
import json, pathlib, sys
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import keras
import tensorflow as tf
import eval as ev
from model_config import *  # noqa: F401,F403

N_CALIB = 1000


def to_int8_tflite(model, calib):
    def rep():
        for i in range(len(calib)):
            yield [calib[i:i + 1]]
    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = rep
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8
    conv.inference_output_type = tf.int8
    return conv.convert()


def main(variants):
    d = ev.load_cache()
    mean, std = float(d["mean"]), float(d["std"])
    xt = ev.normalise(d["x_train"], mean, std); yt = d["y_train"]
    xc = ev.normalise(d["x_test"], mean, std);  xn = ev.normalise(d["x_test_noisy"], mean, std)
    # Calibrate on a class-balanced random subset of training features.
    rng = np.random.default_rng(1)
    idx = np.concatenate([rng.permutation(np.flatnonzero(yt == c))[:N_CALIB // 3] for c in range(3)])
    calib = xt[rng.permutation(idx)]

    out = {}
    for v in variants:
        model = keras.models.load_model(ARTIFACTS / f"{KEYWORD}_{v}.keras")
        blob = to_int8_tflite(model, calib)
        path = ARTIFACTS / f"{KEYWORD}_{v}_int8.tflite"
        path.write_bytes(blob)
        it = tf.lite.Interpreter(model_content=blob); it.allocate_tensors()
        i, o = it.get_input_details()[0], it.get_output_details()[0]
        ops = sorted({op["op_name"] for op in it._get_ops_details()})
        print(f"\n{v}: {len(blob)/1024:.1f} KB  in={i['dtype'].__name__} scale/zp={i['quantization']}  "
              f"out scale/zp={o['quantization']}  ops={ops}", flush=True)
        pf_c, pf_n = ev.predict_keras(model, xc), ev.predict_keras(model, xn)
        pq_c, pq_n = ev.predict_tflite(path, xc), ev.predict_tflite(path, xn)
        res = ev.report(f"{v} int8", pq_c, pq_n, d["y_test"])
        agree = float((pf_c.argmax(-1) == pq_c.argmax(-1)).mean())
        print(f"  float/int8 argmax agreement (clean test): {agree*100:.2f}%   "
              f"max |p_key float - int8|: {np.abs(pf_c[:, KEY] - pq_c[:, KEY]).max():.3f}")
        out[v] = {"tflite_bytes": len(blob), "ops": ops, "input_quant": [float(i["quantization"][0]), int(i["quantization"][1])],
                  "output_quant": [float(o["quantization"][0]), int(o["quantization"][1])],
                  "int8": res, "float_int8_argmax_agreement": agree}
        (ARTIFACTS / f"{KEYWORD}_results_int8.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:] or list(VARIANTS))
