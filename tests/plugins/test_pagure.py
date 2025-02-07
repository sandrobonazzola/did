# coding: utf-8
"""
Tests for the Pagure plugin

Test project: https://pagure.io/did
"""

import pytest

import did.base
import did.cli

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Constants
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

INTERVAL = "--since 2018-11-26 --until 2018-11-26"
BEFORE = "--since 2018-11-20 --until 2018-11-25"
AFTER = "--since 2018-11-27 --until 2018-11-30"

CONFIG = """
[general]
email = "Petr Splichal" <psplicha@redhat.com>

[pagure]
type = pagure
url = https://pagure.io/api/0/
login = psss
"""

# Indexes within stats
ISSUE_CREATED = 0
ISSUE_CLOSED = 1
PR_CREATED = 2
COMMENTS = 3


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def test_pagure_issues_created():
    """ Created issues """
    did.base.Config(CONFIG)
    option = "--pagure-issues-created "
    stats = did.cli.main(option + INTERVAL)[0][0].stats[0].stats[ISSUE_CREATED].stats
    assert any(["did#1 - Open Issue" in str(stat) for stat in stats])
    stats = did.cli.main(option + BEFORE)[0][0].stats[0].stats[ISSUE_CREATED].stats
    assert not stats
    stats = did.cli.main(option + AFTER)[0][0].stats[0].stats[ISSUE_CREATED].stats
    assert not stats


def test_pagure_issues_closed():
    """ Closed issues """
    did.base.Config(CONFIG)
    option = "--pagure-issues-closed "
    stats = did.cli.main(option + INTERVAL)[0][0].stats[0].stats[ISSUE_CLOSED].stats
    assert any(["did#2 - Closed Issue" in str(stat) for stat in stats])
    stats = did.cli.main(option + BEFORE)[0][0].stats[0].stats[ISSUE_CLOSED].stats
    assert not stats
    stats = did.cli.main(option + AFTER)[0][0].stats[0].stats[ISSUE_CLOSED].stats
    assert not stats


def test_pagure_pull_requests_created():
    """ Created pull requests """
    did.base.Config(CONFIG)
    option = "--pagure-pull-requests-created "
    stats = did.cli.main(option + INTERVAL)[0][0].stats[0].stats[PR_CREATED].stats
    assert any(
        ["did#3 - Open Pull Request" in str(stat) for stat in stats])
    stats = did.cli.main(option + BEFORE)[0][0].stats[0].stats[PR_CREATED].stats
    assert not stats
    stats = did.cli.main(option + AFTER)[0][0].stats[0].stats[PR_CREATED].stats
    assert not stats


def test_pagure_comments():
    """ Comments """
    did.base.Config(CONFIG)
    option = "--pagure-commented "
    stats = did.cli.main(option + INTERVAL)[0][0].stats[0].stats[COMMENTS].stats
    assert any(
        ["2018-11-26 - psss commented on PR" in str(stat) for stat in stats])
    stats = did.cli.main(option + BEFORE)[0][0].stats[0].stats[COMMENTS].stats
    assert any(
        ["2018-11-22 - psss commented on PR" in str(stat) for stat in stats])
    stats = did.cli.main(option + AFTER)[0][0].stats[0].stats[COMMENTS].stats
    assert any(
        ["2018-11-27 - psss commented on issue" in str(stat) for stat in stats])


def test_pagure_missing_url():
    """ Missing url """
    did.base.Config("[pagure]\ntype = pagure")
    with pytest.raises(did.base.ReportError):
        did.cli.main(INTERVAL)
