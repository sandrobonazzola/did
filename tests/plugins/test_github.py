# coding: utf-8
""" Tests for the GitHub plugin """

import logging
import os
import time
from tempfile import NamedTemporaryFile

import pytest
from _pytest.logging import LogCaptureFixture

import did.base
import did.cli

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Constants
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

INTERVAL = "--since 2015-09-05 --until 2015-09-06"

CONFIG_NOTOKEN = """
[general]
email = "Petr Splichal" <psplicha@redhat.com>

[gh]
type = github
url = https://api.github.com/
login = psss
"""

CONFIG = f"""
{CONFIG_NOTOKEN}
token = {os.getenv(key="GITHUB_TOKEN", default="NoTokenSpecified")}
"""

# GitHub has quite strict limits for unauthenticated searches
# https://developer.github.com/v3/search/#rate-limit
# Let's have a short nap after each test


def teardown_function() -> None:
    time.sleep(7)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_issues_created() -> None:
    """ Created issues """
    did.base.Config(CONFIG)
    option = "--gh-issues-created "
    stats = did.cli.main(option + INTERVAL)[0][0].stats[0].stats[0].stats
    assert any(
        "psss/did#017 - What did you do" in str(stat) for stat in stats)


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_issues_closed() -> None:
    """ Closed issues """
    did.base.Config(CONFIG)
    option = "--gh-issues-closed "
    stats = did.cli.main(option + INTERVAL)[0][0].stats[0].stats[2].stats
    assert any(
        "psss/did#017 - What did you do" in str(stat) for stat in stats)


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_pull_requests_created() -> None:
    """ Created pull requests """
    did.base.Config("[gh]\ntype = github\nurl = https://api.github.com/")
    option = ("--gh-pull-requests-created "
              "--since 2016-10-26 --until 2016-10-26 "
              "--email mfrodl@redhat.com")
    stats = did.cli.main(option)[0][0].stats[0].stats[3].stats
    assert any(
        "psss/did#112 - Fixed test for Trac plugin" in str(stat)
        for stat in stats)


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_pull_requests_closed() -> None:
    """ Closed pull requests """
    did.base.Config(CONFIG)
    option = "--gh-pull-requests-closed --since 2015-09-22 --until 2015-09-22"
    stats = did.cli.main(option)[0][0].stats[0].stats[5].stats
    assert any(
        "psss/did#037 - Skip CI users" in str(stat) for stat in stats)


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_pull_requests_reviewed() -> None:
    """ Reviewed pull requests """
    did.base.Config(CONFIG.replace('psss', 'evgeni'))
    option = "--gh-pull-requests-reviewed --since 2017-02-22 --until 2017-02-23"
    stats = did.cli.main(option)[0][0].stats[0].stats[6].stats
    assert any("Katello/katello-client-bootstrap#164" in str(stat)
               for stat in stats)


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_pull_requests_commented() -> None:
    """ Commented pull requests """
    did.base.Config(CONFIG)
    option = "--gh-pull-requests-commented --since 2023-01-10 --until 2023-01-23"
    stats = did.cli.main(option)[0][0].stats[0].stats[4].stats
    for stat in stats:
        print(stat)
    assert any(
        "psss/did#285 - Fix error when building SRPM in copr"
        in str(stat) for stat in stats)


def test_github_invalid_token(caplog: LogCaptureFixture) -> None:
    """ Invalid token """
    did.base.Config(f"{CONFIG_NOTOKEN}\ntoken = bad-token")
    with caplog.at_level(logging.ERROR):
        did.cli.main(INTERVAL)
        assert "Defined token is not valid" in caplog.text


def test_github_missing_url(caplog: LogCaptureFixture) -> None:
    """ Missing url """
    did.base.Config("""
                    [general]
                    email = "Petr Splichal" <psplicha@redhat.com>
                    [gh]
                    type = github
                    """)
    with caplog.at_level(logging.ERROR):
        did.cli.main(INTERVAL)
        assert "Skipping section gh due to error: No github url set" in caplog.text


def test_github_wrong_user(caplog: LogCaptureFixture) -> None:
    """
    Test non existing user error reporting
    @see: https://github.com/psss/did/issues/101
    """
    did.base.Config("""
                    [general]
                    email = "Petr Splichal" <psplicha@redhat.com>

                    [gh]
                    type = github
                    url = https://api.github.com/
                    login = nonexistantuser
                    """)
    with caplog.at_level(logging.ERROR):
        did.cli.main(INTERVAL)
        assert "The listed users cannot be searched" in caplog.text


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_unicode() -> None:
    """ Created issues with Unicode characters """
    did.base.Config(f"""
        [gh]
        type = github
        url = https://api.github.com/
        token = {os.getenv(key="GITHUB_TOKEN")}
        """)
    option = ("--gh-pull-requests-created "
              "--since 2016-02-23 --until 2016-02-23 "
              "--email hasys@example.org")
    stats = did.cli.main(option)[0][0].stats[0].stats[3].stats
    assert any(
        "Boundary events lose it’s documentation" in str(stat)
        for stat in stats)


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_issues_created_with_token_file() -> None:
    """ Created issues (config with token_file)"""
    token = os.getenv(key="GITHUB_TOKEN", default="")
    with NamedTemporaryFile(mode="w+", encoding="utf-8") as file_handle:
        file_handle.writelines([token])
        file_handle.flush()
        config = CONFIG_NOTOKEN + f"\ntoken_file = {file_handle.name}"
        did.base.Config(config)
        option = "--gh-issues-created "
        stats = did.cli.main(option + INTERVAL)[0][0].stats[0].stats[0].stats
        assert any(
            "psss/did#017 - What did you do" in str(stat) for stat in stats)


@pytest.mark.skipif("GITHUB_TOKEN" not in os.environ,
                    reason="No GITHUB_TOKEN environment variable found")
def test_github_issues_commented() -> None:
    """
    Commented issues.
    Requires the use of a GitHub token due to the amount
    of queries needed.
    """
    did.base.Config(CONFIG)
    option = "--gh-issues-commented --since 2023-01-10 --until 2023-01-23"
    stats = did.cli.main(option)[0][0].stats[0].stats[1].stats
    assert any(
        "teemtee/tmt#1787 - tmt does not run test with local changes applied"
        in str(stat) for stat in stats)
