"""CropHarvest-data vision baseline (P16, Tier C).

Binary crop/non-crop classification on CropHarvest v14 remote-sensing
features, with classical baselines (logistic regression, random forest)
tracked in MLflow. This package is deliberately isolated from the
decision-support pipeline: its outputs must never be presented as
evidence of drought damage or of intervention effectiveness.

Heavy dependencies (``h5py``, ``scikit-learn``, ``mlflow``) are imported
lazily inside functions, so the base package and dependency-free tests
run without the vision tools installed.
"""
