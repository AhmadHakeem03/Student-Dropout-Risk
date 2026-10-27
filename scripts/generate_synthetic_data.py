"""Write encoded real data and the SMOTEN-augmented training set to data/processed/.

    uv run python scripts/generate_synthetic_data.py
"""

from dropout_risk.config import load_config
from dropout_risk.synthetic import write_processed_datasets

if __name__ == "__main__":
    for name, path in write_processed_datasets(load_config()).items():
        print(f"{name:<16} {path}")
