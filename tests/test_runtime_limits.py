import tests
import os
from unittest import TestCase
from unittest.mock import patch

from runtime_limits import configure_numerical_threads


class NumericalThreadDefaultsTests(TestCase):
    def test_default_is_one_and_does_not_limit_other_workers(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_numerical_threads()
            configure_numerical_threads()
            self.assertEqual(dict(os.environ), {'OPENBLAS_NUM_THREADS': '1'})

    def test_explicit_native_thread_setting_is_preserved(self):
        with patch.dict(os.environ, {'OPENBLAS_NUM_THREADS': '4', 'OMP_NUM_THREADS': '8'}, clear=True):
            configure_numerical_threads()
            self.assertEqual(os.environ['OPENBLAS_NUM_THREADS'], '4')
            self.assertEqual(os.environ['OMP_NUM_THREADS'], '8')
