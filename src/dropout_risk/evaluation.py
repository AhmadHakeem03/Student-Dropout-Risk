"""Test-set metrics, bootstrap confidence intervals, and figures."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score, average_precision_score, balanced_accuracy_score, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score, roc_auc_score, roc_curve,
)

# palette (dataviz reference instance): one hue per role, gray for de-emphasis
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#b4b2a9"
TEXT, TEXT_2, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e0"


def _style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
        "text.color": TEXT, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
        "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
    })


_style()

METRICS = {
    "f1": lambda y, p, s: f1_score(y, p, zero_division=0),
    "roc_auc": lambda y, p, s: roc_auc_score(y, s),
    "average_precision": lambda y, p, s: average_precision_score(y, s),
    "recall": lambda y, p, s: recall_score(y, p, zero_division=0),
    "precision": lambda y, p, s: precision_score(y, p, zero_division=0),
    "accuracy": lambda y, p, s: accuracy_score(y, p),
    "balanced_accuracy": lambda y, p, s: balanced_accuracy_score(y, p),
}


def test_metrics(y_true, proba, threshold: float = 0.5) -> dict:
    y_true, pred = np.asarray(y_true), (np.asarray(proba) >= threshold).astype(int)
    return {name: fn(y_true, pred, proba) for name, fn in METRICS.items()}


def bootstrap_ci(y_true, proba, metrics=("f1", "roc_auc"), n: int = 2000, seed: int = 0,
                 threshold: float = 0.5) -> dict:
    """95% percentile CIs. The test set is small (~46 rows), so these intervals are wide."""
    rng = np.random.default_rng(seed)
    y_true, proba = np.asarray(y_true), np.asarray(proba)
    pred = (proba >= threshold).astype(int)
    draws = {m: [] for m in metrics}
    for _ in range(n):
        idx = rng.integers(0, len(y_true), len(y_true))
        if len(np.unique(y_true[idx])) < 2:
            continue
        for m in metrics:
            draws[m].append(METRICS[m](y_true[idx], pred[idx], proba[idx]))
    return {f"{m}_ci": tuple(np.percentile(v, [2.5, 97.5])) for m, v in draws.items()}


def plot_model_comparison(results: pd.DataFrame, metric: str, best: str, path: Path,
                          baseline: float | None = None):
    """CV mean +/- std (blue) next to test score with bootstrap CI (orange), per model.
    `baseline` = the test score of always predicting "drop", drawn as a dashed reference line."""
    df = results.sort_values(f"cv_{metric}", ascending=True)
    y = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(7.5, 0.6 * len(df) + 1.8))
    cv, std = df[f"cv_{metric}"], df[f"cv_{metric}_std"]
    cv_err = np.vstack([np.minimum(std, cv), np.minimum(std, 1 - cv)])  # keep bars inside [0, 1]
    ax.errorbar(cv, y + 0.13, xerr=cv_err, fmt="o", ms=8,
                color=BLUE, ecolor=BLUE, elinewidth=2, capsize=0, label=f"CV mean ± std (train)")
    if f"test_{metric}_ci" in df:
        lo = df[f"test_{metric}"] - df[f"test_{metric}_ci"].map(lambda t: t[0])
        hi = df[f"test_{metric}_ci"].map(lambda t: t[1]) - df[f"test_{metric}"]
        xerr = np.vstack([lo, hi])
    else:
        xerr = None
    ax.errorbar(df[f"test_{metric}"], y - 0.13, xerr=xerr, fmt="o", ms=8, color=ORANGE,
                ecolor=ORANGE, elinewidth=2, capsize=0, label="Test (95% bootstrap CI)")
    ax.set_yticks(y, [f"{lbl}  ★" if n == best else lbl for n, lbl in zip(df["model"], df["label"])])
    ax.set_xlabel(metric.replace("_", " "))
    ax.grid(axis="y", visible=False)
    if baseline is not None:
        ax.axvline(baseline, ls="--", lw=1, color=TEXT_2, label='Test: always predict "drop"')
    ax.set_xlim(max(0, min(ax.get_xlim()[0], 0.4)), 1.02)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8.5)
    ax.set_title(f"Model comparison — {metric.replace('_', ' ')}  (★ = selected by CV)")
    fig.savefig(path)
    plt.close(fig)


def plot_curves(curves: dict, labels: dict, best: str, path: Path):
    """ROC and precision-recall on the test set; best model highlighted, others in gray."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    order = [m for m in curves if m != best] + [best]
    for name in order:
        y_true, proba = curves[name]
        is_best = name == best
        style = dict(color=BLUE if is_best else GRAY, lw=2.4 if is_best else 1.4,
                     zorder=3 if is_best else 2)
        fpr, tpr, _ = roc_curve(y_true, proba)
        axes[0].plot(fpr, tpr, label=f"{labels[name]} (AUC {roc_auc_score(y_true, proba):.3f})", **style)
        prec, rec, _ = precision_recall_curve(y_true, proba)
        axes[1].plot(rec, prec, label=f"{labels[name]} (AP {average_precision_score(y_true, proba):.3f})",
                     drawstyle="steps-post", **style)
    axes[0].plot([0, 1], [0, 1], ls="--", lw=1, color=TEXT_2, zorder=1)
    axes[0].set(xlabel="False positive rate", ylabel="True positive rate", title="ROC curve (test set)")
    base = np.mean(next(iter(curves.values()))[0])
    axes[1].axhline(base, ls="--", lw=1, color=TEXT_2, zorder=1)
    axes[1].set(xlabel="Recall", ylabel="Precision", title="Precision–recall curve (test set)")
    for ax in axes:
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.04)
        handles, lbls = ax.get_legend_handles_labels()
        ax.legend(handles[::-1], lbls[::-1], loc="lower right" if ax is axes[0] else "lower left",
                  fontsize=8.5)
    fig.savefig(path)
    plt.close(fig)


def plot_confusion_matrices(cms: dict, labels: dict, best: str, path: Path):
    fig, axes = plt.subplots(1, len(cms), figsize=(2.7 * len(cms), 3.0))
    vmax = max(cm.max() for cm in cms.values())
    for ax, (name, cm) in zip(np.atleast_1d(axes), cms.items()):
        ax.imshow(cm, cmap="Blues", vmin=0, vmax=vmax)
        for (i, j), v in np.ndenumerate(cm):
            ax.text(j, i, str(v), ha="center", va="center", fontsize=12, fontweight="bold",
                    color="white" if v > vmax * 0.55 else TEXT)
        ax.set_xticks([0, 1], ["no", "drop"])
        ax.set_yticks([0, 1], ["no", "drop"])
        ax.set_xlabel("Predicted")
        ax.grid(False)
        ax.set_title(labels[name] + ("  ★" if name == best else ""), fontsize=10)
    np.atleast_1d(axes)[0].set_ylabel("Actual")
    fig.suptitle("Confusion matrices — test set", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_feature_selection(report: pd.DataFrame, path: Path, max_rows: int = 30):
    df = report.dropna(subset=["score"]).head(max_rows).iloc[::-1]
    colors = [BLUE if s == "selected" else GRAY for s in df["status"]]
    fig, ax = plt.subplots(figsize=(7.5, 0.26 * len(df) + 1.2))
    ax.barh(df.index, df["score"], color=colors, height=0.7)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Combined rank score (mean of MI and RF-importance percentiles)")
    ax.set_title("Feature selection — blue = selected, gray = dropped")
    ax.tick_params(axis="y", labelsize=8.5)
    fig.savefig(path)
    plt.close(fig)


def plot_permutation_importance(imp: pd.DataFrame, title: str, path: Path, max_rows: int = 15):
    df = imp.head(max_rows).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 0.32 * len(df) + 1.2))
    ax.barh(df.index, df["mean"], xerr=df["std"], color=BLUE, height=0.65,
            error_kw={"ecolor": TEXT_2, "elinewidth": 1})
    ax.axvline(0, color=TEXT_2, lw=0.8)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Drop in test ROC-AUC when the survey answer is shuffled")
    ax.set_title(title)
    fig.savefig(path)
    plt.close(fig)


def confusion(y_true, proba, threshold: float = 0.5):
    return confusion_matrix(y_true, (np.asarray(proba) >= threshold).astype(int), labels=[0, 1])
