"""
Tests for python
"""
from unittest import TestCase


class TestMain(TestCase):
    """Unit tests for main module."""

    def test_one_plus_one(self):
        """Does 1+1 = 2?"""
        self.assertEqual(1 + 1, 2)
