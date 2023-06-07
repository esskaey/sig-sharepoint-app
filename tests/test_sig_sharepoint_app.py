#!/usr/bin/env python

"""Tests for `sig_sharepoint_app` package."""


import unittest
from click.testing import CliRunner

from sig_sharepoint_app import sig_sharepoint_app
from sig_sharepoint_app import cli


class TestSig_sharepoint_app(unittest.TestCase):
    """Tests for `sig_sharepoint_app` package."""

    def setUp(self):
        """Set up test fixtures, if any."""

    def tearDown(self):
        """Tear down test fixtures, if any."""

    def test_000_something(self):
        """Test something."""

    def test_command_line_interface(self):
        """Test the CLI."""
        runner = CliRunner()
        result = runner.invoke(cli.main)
        assert result.exit_code == 0
        assert 'sig_sharepoint_app.cli.main' in result.output
        help_result = runner.invoke(cli.main, ['--help'])
        assert help_result.exit_code == 0
        assert '--help  Show this message and exit.' in help_result.output
