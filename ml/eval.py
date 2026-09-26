"""Accuracy evaluation shared by train.py / quantize.py. Also runnable: python ml/eval.py <variant>.

Metrics per test condition (clean, noisy): 3-class accuracy, keyword hit rate, and false accepts
(non-keyword clips, i.e. unknown words + silence, that fire the keyword). The "per hour" figure is
clip-level: FA-fraction x 3600 one-second clips, which is only an approximation of streaming false
accepts; the streaming figure comes from the Renode corpus run (Phase 6).
"""
import json, pathlib, sys
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from model_config import *  # noqa: F401,F403

THRESHOLDS = [0.5, 0.7, 0.8, 0.9, 0.95, 0.99]


def load_cache():
    z = np.load(CACHE)
    return {k: z[k] for k in z.files}


def normalise(x, mean, std):
    return ((x - mean) / std).astype(np.float32)[..., None]


def softmax(z):
    z = z - z.max(-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(-1, keepdims=True)


def predict_keras(model, x, batch=512):
    return softmax(np.concatenate([model.predict(x[i:i + batch], verbose=0) for i in range(0, len(x), batch)]))


def predict_tflite(path, x):
    """int8 TFLite model on float inputs (quantised with the model's own input params)."""
    import tensorflow as tf
    it = tf.lite.Interpreter(model_path=str(path))
    it.allocate_tensors()
    i, o = it.get_input_details()[0], it.get_output_details()[0]
    s_in, z_in = i["quantization"]; s_out, z_out = o["quantization"]
    out = np.empty((len(x), o["shape"][-1]), np.float32)
    for n in range(len(x)):
        q = np.clip(np.round(x[n:n + 1] / s_in + z_in), -128, 127).astype(np.int8)
        it.set_tensor(i["index"], q)
        it.invoke()
        out[n] = (it.get_tensor(o["index"])[0].astype(np.float32) - z_out) * s_out
    return softmax(out)      # the model's output layer is logits (softmax is applied here / on-device)


def metrics(prob, y):
    pred = prob.argmax(-1)
    key, neg = y == KEY, y != KEY
    m = {"acc": float((pred == y).mean()), "hit_argmax": float((pred[key] == KEY).mean()),
         "fa_argmax": float((pred[neg] == KEY).mean()), "n_key": int(key.sum()), "n_neg": int(neg.sum())}
    m["thr"] = {str(t): {"hit": float((prob[key, KEY] >= t).mean()),
                         "fa_frac": float((prob[neg, KEY] >= t).mean()),
                         "fa_per_hour_clip_level": float((prob[neg, KEY] >= t).mean() * 3600)} for t in THRESHOLDS}
    return m


def report(name, prob_clean, prob_noisy, y):
    res = {"clean": metrics(prob_clean, y), "noisy": metrics(prob_noisy, y)}
    print(f"\n== {name} ==")
    for cond in ("clean", "noisy"):
        r = res[cond]
        print(f"  {cond:5s}: acc={r['acc']*100:.2f}%  hit(argmax)={r['hit_argmax']*100:.1f}%  "
              f"FA(argmax)={r['fa_argmax']*100:.3f}%  (n_key={r['n_key']}, n_neg={r['n_neg']})")
    print("  thr    hit clean  hit noisy   FA/h clean  FA/h noisy   (clip-level FA per hour of 1 s clips)")
    for t in THRESHOLDS:
        c, n = res["clean"]["thr"][str(t)], res["noisy"]["thr"][str(t)]
        print(f"  {t:<5}  {c['hit']*100:8.1f}%  {n['hit']*100:8.1f}%  {c['fa_per_hour_clip_level']:10.1f}  {n['fa_per_hour_clip_level']:10.1f}")
    return res


if __name__ == "__main__":
    import keras
    v = sys.argv[1]
    d = load_cache()
    model = keras.models.load_model(ARTIFACTS / f"{KEYWORD}_{v}.keras")
    xc = normalise(d["x_test"], float(d["mean"]), float(d["std"]))
    xn = normalise(d["x_test_noisy"], float(d["mean"]), float(d["std"]))
    report(f"{v} float", predict_keras(model, xc), predict_keras(model, xn), d["y_test"])
