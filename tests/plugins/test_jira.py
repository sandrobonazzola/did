# coding: utf-8
""" Tests for the Jira plugin """

import pytest

import did.base
import did.cli
from did.base import ReportError
from did.plugins.jira import JiraStats

CONFIG = """
[general]
email = mail@example.com
[jira]
type = jira
prefix = JBEAP
project = JBEAP
url = https://issues.redhat.com/
auth_url = https://issues.redhat.com/rest/auth/latest/session
"""


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Configuration tests
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def test_config_gss_auth():
    """  Test default authentication configuration """
    did.base.Config(CONFIG)
    JiraStats("jira")


def test_wrong_auth():
    """  Test wrong authentication type configuration """
    did.base.Config(f"""
{CONFIG}
auth_type = OAuth2
""")
    with pytest.raises(ReportError, match=r"Unsupported authentication type"):
        JiraStats("jira")


def test_config_basic_auth():
    """  Test basic authentication configuration """
    did.base.Config(f"""
{CONFIG}
auth_type = basic
auth_username = tom
auth_password = motak
""")
    JiraStats("jira")


def test_config_missing_username():
    """  Test basic auth with missing username """
    assert_conf_error(f"""
{CONFIG}
auth_type = basic
""")


def test_config_missing_password():
    """  Test basic auth with missing username """
    assert_conf_error(f"""
{CONFIG}
auth_type = basic
auth_username = tom
""")


def test_config_gss_and_username():
    """  Test gss auth with username set """
    assert_conf_error(f"""
{CONFIG}
auth_type = gss
auth_username = tom
""")


def test_config_gss_and_password():
    """  Test gss auth with password set """
    assert_conf_error(f"""
{CONFIG}
auth_type = gss
auth_password = tom
""")


def test_config_gss_and_password_file():
    """  Test gss auth with password set """
    assert_conf_error(f"""
{CONFIG}
auth_type = gss
auth_password_file = ~/.did/config
""")


def test_config_invaliad_ssl_verify():
    """  Test ssl_verify with wrong bool value """
    assert_conf_error(f"""
{CONFIG}
ssl_verify = ss
""")


def test_ssl_verify():
    """Test ssl_verify """
    did.base.Config(f"""
{CONFIG}
ssl_verify = False
""")
    with pytest.raises(ReportError, match=r"Jira authentication failed"):
        # expected to fail authentication as we are not providing valid
        # credentials
        did.cli.main("today")


def test_jira_missing_url():
    """ Missing URL """
    assert_conf_error(CONFIG.replace("url = https://issues.redhat.com/\n", ""))


def test_jira_wrong_url():
    """ Missing URL """
    did.base.Config(f"""{did.base.Config.example()}
[jira]
type = jira
prefix = JBEAP
project = JBEAP
url = https://localhost
""")
    with pytest.raises(ReportError, match=r"Failed to connect to Jira"):
        did.cli.main("today")


def test_jira_use_scriptrunner_config_error():
    """ use_scriptrunner False and missing project """
    did.base.Config(f"""{did.base.Config.example()}
[jira]
type = jira
prefix = JBEAP
use_scriptrunner = False
url = https://issues.redhat.com/
auth_url = https://issues.redhat.com/rest/auth/latest/session
""")
    with pytest.raises(ReportError,
                       match=r"When scriptrunner is disabled.*has to be defined.*."):
        JiraStats("jira")


def assert_conf_error(config, expected_error=ReportError):
    """ Test given config and check that given error type is raised """
    did.base.Config(config)
    with pytest.raises(expected_error):
        JiraStats("jira")
