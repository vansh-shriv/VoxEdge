"""Train DS-CNN variants on the cached features.  python ml/train.py [variant ...]  (default: all)"""
import json, pathlib, sys, time
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import keras
from model import build_dscnn, count_macs
import eval as ev
from model_config import *  # noqa: F401,F403

EPOCHS, BATCH, LR = 40, 128, 2e-3
SEED = 20260927


def main(variants):
    d = ev.load_cache()
    mean, std = float(d["mean"]), float(d["std"])
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / f"{KEYWORD}_norm.json").write_text(json.dumps({"mean": mean, "std": std}, indent=2))
    xt = ev.normalise(d["x_train"], mean, std); yt = d["y_train"].astype(np.int32)
    xv = ev.normalise(d["x_val"], mean, std);   yv = d["y_val"].astype(np.int32)
    xc = ev.normalise(d["x_test"], mean, std);  xn = ev.normalise(d["x_test_noisy"], mean, std)
    print(f"train {xt.shape} classes {np.bincount(yt)}  val {xv.shape} {np.bincount(yv)}")
    steps = EPOCHS * int(np.ceil(len(xt) / BATCH))

    summary = {}
    for v in variants:
        width, blocks = VARIANTS[v]
        keras.utils.set_random_seed(SEED)
        model = build_dscnn(width, blocks, name=f"{KEYWORD}_{v}")
        macs = count_macs(model)
        print(f"\n### {v}: width={width} blocks={blocks} params={model.count_params()} MACs={macs/1e6:.2f}M", flush=True)
        model.compile(
            optimizer=keras.optimizers.Adam(keras.optimizers.schedules.CosineDecay(LR, steps, alpha=0.01)),
            loss=keras.losses.SparseCategoricalCrossentropy(from_logits=True), metrics=["accuracy"])
        ckpt = keras.callbacks.ModelCheckpoint(ARTIFACTS / f"{KEYWORD}_{v}.keras", monitor="val_accuracy",
                                               save_best_only=True, verbose=0)
        t0 = time.time()
        hist = model.fit(xt, yt, validation_data=(xv, yv), epochs=EPOCHS, batch_size=BATCH, shuffle=True,
                         class_weight={SILENCE: 1.0, UNKNOWN: 1.0, KEY: 2.0}, callbacks=[ckpt], verbose=2)
        print(f"training time {time.time() - t0:.0f} s; best val acc {max(hist.history['val_accuracy']):.4f}")
        best = keras.models.load_model(ARTIFACTS / f"{KEYWORD}_{v}.keras")
        res = ev.report(f"{v} float (width={width}, blocks={blocks}, {macs/1e6:.2f}M MACs)",
                        ev.predict_keras(best, xc), ev.predict_keras(best, xn), d["y_test"])
        summary[v] = {"width": width, "blocks": blocks, "params": int(model.count_params()), "macs": int(macs),
                      "best_val_acc": float(max(hist.history["val_accuracy"])), "float": res}
        (ARTIFACTS / f"{KEYWORD}_results_float.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:] or list(VARIANTS))
