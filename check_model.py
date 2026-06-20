import joblib
from pathlib import Path

model_path = Path(__file__).resolve().parent / "ml" / "xgboost_model.pkl"

try:
    clf = joblib.load(model_path)
    print("\n=== XGBOOST INTERNAL BRAIN SCAN ===")
    print(f"Model Type: {type(clf)}")
    print(f"Internal Classes: {clf.classes_}")
    print("===================================\n")
except Exception as e:
    print(f"Failed to load model: {e}")