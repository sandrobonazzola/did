"""
Jira stats such as created, updated or resolved issues

Configuration example (token)::

    [issues]
    type = jira
    url = https://issues.redhat.com/
    auth_type = token
    token_file = ~/.did/jira-token
    token_expiration = 7
    token_name = did-token

Either ``token`` or ``token_file`` has to be defined.

token
    Token string directly included in the config.
    Has a higher priority over ``token_file``.

token_file
    Path to the file where the token is stored.

token_expiration
    Print warning if token with provided ``token_name`` expires within
    specified number of ``days``.

token_name
    Name of the token to check for expiration in ``token_expiration``
    days. This has to match the name as seen in your Jira profile.

Configuration example (GSS authentication)::

    [issues]
    type = jira
    url = https://issues.redhat.org/
    ssl_verify = true

Configuration example (basic authentication)::

    [issues]
    type = jira
    url = https://issues.redhat.org/
    auth_url = https://issues.redhat.org/rest/auth/latest/session
    auth_type = basic
    auth_username = username
    auth_password = password
    auth_password_file = ~/.did/jira_password

Keys ``auth_username``, ``auth_password`` and ``auth_password_file`` are
only valid for ``basic`` authentication. Either ``auth_password`` or
``auth_password_file`` must be provided, ``auth_password`` has a higher
priority.

Configuration example limiting report only to a single project, using an
alternative username and a custom identifier prefix::

    [issues]
    type = jira
    project = ORG
    prefix = JIRA
    login = alt_username
    url = https://issues.redhat.org/
    ssl_verify = true

Notes:

* If your JIRA does not have scriptrunner installed you must set
  ``use_scriptrunner`` to false.
* You must provide ``login`` variable that matches username if it
  doesn't match email/JIRA account.
* Optional parameter ``ssl_verify`` can be used to enable/disable
  SSL verification (default: true).
* ``auth_url`` parameter is optional. If not provided,
  ``/step-auth-gss`` endpoint on ``url`` will be used
  for authentication.
  Its value is ignored for ``token`` auth_type.
* The ``auth_type`` parameter is optional, default value is ``gss``.
  Other values are ``basic`` and ``token``.
"""

import os
import re
import urllib.parse

import dateutil.parser
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests_gssapi import DISABLED, HTTPSPNEGOAuth

from did.base import Config, ReportError, get_token
from did.stats import Stats, StatsGroup
from did.utils import listed, log, pretty, strtobool

# Maximum number of results fetched at once
MAX_RESULTS = 1000

# Maximum number of batches
MAX_BATCHES = 100

# Supported authentication types
AUTH_TYPES = ["gss", "basic", "token"]

# Enable ssl verify
SSL_VERIFY = True

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Issue Investigator
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class Issue():
    """ Jira issue investigator """

    def __init__(self, issue=None, parent=None):
        """ Initialize issue """
        if issue is None:
            return
        self.parent = parent
        self.options = parent.options
        self.issue = issue
        self.key = issue["key"]
        self.summary = issue["fields"]["summary"]
        self.comments = issue["fields"]["comment"]["comments"]
        matched = re.match(r"(\w+)-(\d+)", self.key)
        self.identifier = matched.groups()[1]
        if parent.prefix is not None:
            self.prefix = parent.prefix
        else:
            self.prefix = matched.groups()[0]

    def __str__(self):
        """ Jira key and summary for displaying """
        label = f"{self.prefix}-{self.identifier}"
        if self.options.format == "markdown":
            href = f"{self.parent.url}/browse/{self.issue['key']}"
            return f"[{label}]({href}) - {self.summary}"
        return f"{label} - {self.summary}"

    def __eq__(self, other):
        """ Compare issues by key """
        return self.key == other.key

    @staticmethod
    def search(query, stats):
        """ Perform issue search for given stats instance """
        log.debug("Search query: %s", query)
        issues = []
        # Fetch data from the server in batches of MAX_RESULTS issues
        for batch in range(MAX_BATCHES):
            encoded_query = urllib.parse.urlencode(
                {
                    "jql": query,
                    "fields": "summary,comment",
                    "maxResults": MAX_RESULTS,
                    "startAt": batch * MAX_RESULTS
                    }
                )
            response = stats.parent.session.get(
                f"{stats.parent.url}/rest/api/latest/search?{encoded_query}")
            data = response.json()
            if not response.ok:
                try:
                    error = " ".join(data["errorMessages"])
                except KeyError:
                    error = "unknown"
                raise ReportError(
                    f"Failed to fetch jira issues for query '{query}'. "
                    f"The reason was '{response.reason}' "
                    f"and the error was '{error}'.")
            log.debug(
                "Batch %s result: %s fetched",
                batch,
                listed(
                    data["issues"],
                    "issue"))
            log.data(pretty(data))
            issues.extend(data["issues"])
            # If all issues fetched, we're done
            if len(issues) >= data["total"]:
                break
        # Return the list of issue objects
        return [
            Issue(issue, parent=stats.parent)
            for issue in issues
            ]

    def updated(self, user, options):
        """ True if the issue was commented by given user """
        for comment in self.comments:
            created = dateutil.parser.parse(comment["created"]).date()
            try:
                if (comment["author"]["emailAddress"] == user.email and
                        created >= options.since.date and
                        created < options.until.date):
                    return True
            except KeyError:
                pass
        return False


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class JiraCreated(Stats):
    """ Created issues """

    def fetch(self):
        log.info(
            "Searching for issues created in %s by %s",
            self.parent.project,
            self.user)
        query = f"creator = '{
            self.user.login or self.user.email}' AND created >= {
            self.options.since} AND created <= {
            self.options.until}"
        if self.parent.project:
            query = query + f" AND project = '{self.parent.project}'"
        self.stats = Issue.search(query, stats=self)


class JiraUpdated(Stats):
    """ Updated issues """

    def fetch(self):
        log.info(
            "Searching for issues updated in %s by %s",
            self.parent.project,
            self.user)
        if self.parent.use_scriptrunner:
            query = f"issueFunction in commented('by {
                self.user.login or self.user.email} after {
                self.options.since} before {
                self.options.until}')"
            if self.parent.project:
                query = query + f" AND project = '{self.parent.project}'"
            self.stats = Issue.search(query, stats=self)
        else:
            query = f"project = '{
                self.parent.project}' AND updated >= {
                self.options.since} AND created <= {
                self.options.until}"
            # Filter only issues commented by given user
            self.stats = [
                issue for issue in Issue.search(query, stats=self)
                if issue.updated(self.user, self.options)]


class JiraResolved(Stats):
    """ Resolved issues """

    def fetch(self):
        log.info(
            "Searching for issues resolved in %s by %s",
            self.parent.project,
            self.user)
        query = f"assignee = '{
            self.user.login or self.user.email}' AND resolved >= {
            self.options.since} AND resolved <= {
            self.options.until}"
        if self.parent.project:
            query = query + f" AND project = '{self.parent.project}'"
        self.stats = Issue.search(query, stats=self)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class JiraStats(StatsGroup):
    """ Jira stats """

    # Default order
    order = 600

    def _basic_auth(self, option, config):
        if "auth_username" not in config:
            raise ReportError(f"`auth_username` not set in the [{option}] section")
        self.auth_username = config["auth_username"]
        if "auth_password" in config:
            self.auth_password = config["auth_password"]
        elif "auth_password_file" in config:
            file_path = os.path.expanduser(config["auth_password_file"])
            with open(file_path, encoding="utf-8") as password_file:
                self.auth_password = password_file.read().strip()
        else:
            raise ReportError(
                "`auth_password` or `auth_password_file` must be set "
                f"in the [{option}] section.")

    def _token_auth(self, option, config):
        self.token = get_token(config)
        if self.token is None:
            raise ReportError(
                "The `token` or `token_file` key must be set "
                f"in the [{option}] section.")
        if "token_expiration" in config or "token_name" in config:
            try:
                self.token_expiration = int(config["token_expiration"])
                self.token_name = config["token_name"]
            except KeyError as key_err:
                raise ReportError(
                    "The ``token_name`` and ``token_expiration`` must be set at"
                    f" the same time in [{option}] section.") from key_err
            except ValueError as val_err:
                raise ReportError(
                    "The ``token_expiration`` must contain number, "
                    f"used in [{option}] section.") from val_err
        else:
            self.token_expiration = self.token_name = None

    def _set_ssl_verification(self, config):
        # SSL verification
        if "ssl_verify" in config:
            try:
                self.ssl_verify = strtobool(
                    config["ssl_verify"])
            except Exception as error:
                raise ReportError(
                    f"Error when parsing 'ssl_verify': {error}") from error
        else:
            self.ssl_verify = SSL_VERIFY

    def _handle_scriptrunner(self, config):
        if "use_scriptrunner" in config:
            self.use_scriptrunner = strtobool(
                config["use_scriptrunner"])
        else:
            self.use_scriptrunner = True

        if not self.use_scriptrunner and not self.project:
            raise ReportError(
                "When scriptrunner is disabled with 'use_scriptrunner=False', "
                "'project' has to be defined for each JIRA section.")

    def __init__(self, option, name=None, parent=None, user=None):
        StatsGroup.__init__(self, option, name, parent, user)
        self._session = None
        # Make sure there is an url provided
        config = dict(Config().section(option))
        if "url" not in config:
            raise ReportError(f"No Jira url set in the [{option}] section")
        self.url = config["url"].rstrip("/")
        # Optional authentication url
        if "auth_url" in config:
            self.auth_url = config["auth_url"]
        else:
            self.auth_url = f"{self.url}/step-auth-gss"
        # Authentication type
        if "auth_type" in config:
            if config["auth_type"] not in AUTH_TYPES:
                raise ReportError(
                    f"Unsupported authentication type: {
                        config["auth_type"]}")
            self.auth_type = config["auth_type"]
        else:
            self.auth_type = "gss"
        # Authentication credentials
        if self.auth_type == "basic":
            self._basic_auth(option, config)
        else:
            if "auth_username" in config:
                raise ReportError(
                    "`auth_username` is only valid for basic authentication "
                    f"(section [{option}])")
            if "auth_password" in config or "auth_password_file" in config:
                raise ReportError(
                    "`auth_password` and `auth_password_file` are only valid for"
                    f" basic authentication (section [{option}])")
        # Token
        if self.auth_type == "token":
            self._token_auth(option, config)
        self._set_ssl_verification(config)

        # Make sure we have project set
        self.project = config.get("project", None)
        self._handle_scriptrunner(config)
        self.login = config.get("login", None)

        # Check for custom prefix
        self.prefix = config["prefix"] if "prefix" in config else None
        # Create the list of stats
        self.stats = [
            JiraCreated(
                option=f"{option}-created", parent=self,
                name=f"Issues created in {option}"),
            JiraUpdated(
                option=f"{option}-updated", parent=self,
                name=f"Issues updated in {option}"),
            JiraResolved(
                option=f"{option}-resolved", parent=self,
                name=f"Issues resolved in {option}"),
            ]

    @property
    def session(self):
        """ Initialize the session """
        if self._session is None:
            self._session = requests.Session()
            log.debug("Connecting to %s", self.auth_url)
            # Disable SSL warning when ssl_verify is False
            if not self.ssl_verify:
                requests.packages.urllib3.disable_warnings(
                    InsecureRequestWarning)
            if self.auth_type == 'basic':
                basic_auth = (self.auth_username, self.auth_password)
                response = self._session.get(
                    self.auth_url, auth=basic_auth, verify=self.ssl_verify)
            elif self.auth_type == "token":
                self.session.headers["Authorization"] = f"Bearer {self.token}"
                response = self._session.get(
                    f"{self.url}/rest/api/2/myself",
                    verify=self.ssl_verify)
            else:
                gssapi_auth = HTTPSPNEGOAuth(mutual_authentication=DISABLED)
                response = self._session.get(
                    self.auth_url, auth=gssapi_auth, verify=self.ssl_verify)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as error:
                log.error(error)
                raise ReportError(
                    "Jira authentication failed. Check credentials or kinit."
                    ) from error
            if self.token_expiration:
                response = self._session.get(
                    f"{self.url}/rest/pat/latest/tokens",
                    verify=self.ssl_verify)
                try:
                    response.raise_for_status()
                    token_found = None
                    for token in response.json():
                        if token["name"] == self.token_name:
                            token_found = token
                            break
                    if token_found is None:
                        raise ValueError(
                            f"Can't check validity for the '{self.token_name}' "
                            f"token as it doesn't exist.")
                    from datetime import datetime
                    expiring_at = datetime.strptime(
                        token_found["expiringAt"], r"%Y-%m-%dT%H:%M:%S.%f%z")
                    delta = (
                        expiring_at.astimezone() - datetime.now().astimezone())
                    if delta.days < self.token_expiration:
                        log.warning("Jira token '%s' expires in %s days.",
                                    self.token_name, delta.days)
                except (requests.exceptions.HTTPError,
                        KeyError, ValueError) as error:
                    log.warning(error)
        return self._session
