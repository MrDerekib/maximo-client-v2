"""Default native numerical workers before importing Pandas/NumPy."""
import os


def configure_numerical_threads():
    """MD imports tables, not large matrix workloads; respect explicit overrides."""
    os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
