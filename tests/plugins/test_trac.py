# coding: utf-8
""" Tests for the trac plugin """

import logging

import pytest
from _pytest.logging import LogCaptureFixture

import did.base
import did.cli

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Constants
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CONFIG = f"""
{did.base.Config.example()}
[trac]
type = trac
"""


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def test_trac_missing_url(caplog: LogCaptureFixture):
    """ Missing url """
    did.base.Config(CONFIG)
    with caplog.at_level(logging.ERROR):
        did.cli.main("today")
        assert "Skipping section trac due to error: No trac url set" in caplog.text


def test_trac_missing_prefix(caplog: LogCaptureFixture):
    """ Missing prefix """
    did.base.Config(f"""
{CONFIG}
url = https://localhost
    """)
    with caplog.at_level(logging.ERROR):
        did.cli.main("today")
        assert "Skipping section trac due to error: No prefix set" in caplog.text


def test_wrong_url():
    """ Connecting to wrong URL """
    did.base.Config(f"""
{CONFIG}
url = https://localhost
prefix = DT
    """)
    with pytest.raises(did.base.ReportError, match=r".*Is the url above correct?"):
        did.cli.main("today")
