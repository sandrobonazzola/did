"""
GitHub stats such as created and closed issues

Config example::

    [github]
    type = github
    url = https://api.github.com/
    token = <authentication-token>
    login = <username>

Optionally the search query can be limited to repositories owned
by the given user or organization. You can also use the full name
of the project to only search in the given repository::

    user = <repository-owner>
    org = <organization-name>
    repo = <full-project-name>

Multiple users, organization or repositories can be searched as
well. Use ``,`` as the separator, for example::

    org = one,two,three

It's also possible to exclude organizations:

    exclude_org = four,five

The authentication token is optional. However, unauthenticated
queries are limited. For more details see `GitHub API`__ docs.
Use ``login`` to override the default email address for searching.
See the :doc:`config` documentation for details on using aliases.

Alternatively to ``token`` you can use ``token_file`` to have the
token stored in a file rather than in your did config file.

__ https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token


It's also possible to set a timeout, if not specified it defaults to 60 seconds.

    timeout = 10

"""  # noqa: W505,E501 # pylint:disable=line-too-long

import json
import re
import time
from argparse import Namespace
from datetime import datetime
from http import HTTPStatus
from typing import Any, Optional

import requests
from tenacity import (RetryCallState, RetryError, Retrying,
                      retry_if_exception_type, stop_after_attempt)

from did.base import Config, Date, ReportError, User, get_token
from did.stats import Stats, StatsGroup
from did.utils import listed, log, pretty

# Identifier padding
PADDING = 3

# Number of GH items to be fetched per page
PER_PAGE = 100

# Default number of seconds waiting on GitHub before giving up
TIMEOUT = 60.0


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Investigator
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class GitHub():
    """ GitHub Investigator """
    # pylint: disable=too-few-public-methods

    def __init__(self, *,
                 url: str,
                 token: Optional[str] = None,
                 user: Optional[str] = None,
                 org: Optional[str] = None,
                 repo: Optional[str] = None,
                 exclude_org: Optional[str] = None,
                 timeout: float = TIMEOUT) -> None:
        """ Initialize url and headers """
        self.url = url.rstrip("/")
        self.timeout = timeout
        if token is not None:
            self.headers = {'Authorization': f'token {token}'}
        else:
            self.headers = {}

        # Prepare the org, user, repo filter
        def condition(key: str, names: Optional[str]) -> list[str]:
            """ Prepare one or more conditions for given key & names """
            if not names:
                return []
            return [f"{key}:{name}" for name in re.split(r"\s*,\s*", names)]

        self.filter = "".join(
            condition("+user", user) +
            condition("+org", org) +
            condition("+repo", repo) +
            condition("+-org", exclude_org)
            )

    def commented_in_range(self,
                           commented_issues: list[dict[str, Any]],
                           since: datetime,
                           until: datetime,
                           login: str) -> list[dict[str, Any]]:
        valid_issues = []
        for issue in commented_issues:
            issue_since = since
            issue_checked = False
            url = (
                f"{issue['comments_url']}"
                f"?per_page={PER_PAGE}&since={issue_since.isoformat()}"
                )
            while not issue_checked:
                try:
                    response = self.request(url)
                    comments = response.json()
                except requests.exceptions.RequestException as e:
                    log.error("Failed to fetch or parse comments from GitHub: %s", e)
                    continue
                except ValueError as e:
                    # Handles JSON decode error
                    log.error("Failed to decode JSON from response at %s: %s", url, e)
                    continue
                log.debug("%s comments fetched for %s", len(comments), url)
                log.data(pretty(comments))
                for comment in comments:
                    created_at = datetime.strptime(
                        comment["created_at"],
                        r"%Y-%m-%dT%H:%M:%SZ"
                        )
                    if created_at > until:
                        # Comments are sorted by created_at asc
                        issue_checked = True
                        break
                    if comment["user"]["login"] == login and since <= created_at:
                        valid_issues.append(issue)
                        issue_checked = True
                        break
                if 'next' in response.links:
                    url = response.links['next']['url']
                else:
                    issue_checked = True
        return valid_issues

    @staticmethod
    def until(until: Date) -> Date:
        """Issue #362: until for GH should have - delta(day=1)"""
        return Date(until - 1)

    def request(self, url: str) -> requests.Response:
        def github_before_sleep(_retry_state: RetryCallState) -> None:
            log.debug("Trying to connect to GitHUb...")
        while True:
            try:
                for attempt in Retrying(
                        stop=stop_after_attempt(3),
                        retry=retry_if_exception_type((
                            requests.exceptions.ConnectionError,
                            ConnectionResetError)),
                        before_sleep=github_before_sleep,
                        reraise=True):
                    with attempt:
                        response = requests.get(
                            url, headers=self.headers, timeout=self.timeout
                            )
                log.debug("Response headers:\n%s", response.headers)
            except (requests.exceptions.RequestException, RetryError) as error:
                log.debug(error)
                raise ReportError(f"GitHub request on {self.url} failed.") from error
            # Check if credentials are valid
            log.debug("GitHub status code: %s", response.status_code)
            if response.status_code == HTTPStatus.UNAUTHORIZED:
                raise ReportError(
                    "Defined token is not valid. "
                    "Either update it or remove it.")

            # Handle the exceeded rate limit
            if response.status_code in (
                    HTTPStatus.FORBIDDEN,
                    HTTPStatus.TOO_MANY_REQUESTS
                    ):
                if response.headers.get("X-RateLimit-Remaining") == "0":
                    reset_time = int(response.headers["X-RateLimit-Reset"])
                    sleep_time = int(max(reset_time - time.time(), 0)) + 1
                    log.warning("GitHub rate limit exceeded, use token to speed up.")
                    log.warning("Sleeping now for %s.", listed(sleep_time, 'second'))
                    time.sleep(sleep_time)
                    continue
                raise ReportError(f"GitHub query failed: {response.text}")
            # all good!
            break

        return response

    def search(self, query: str) -> list[dict[str, Any]]:
        """ Perform GitHub query """
        result = []
        url = f"{self.url}/{query}{self.filter}&per_page={PER_PAGE}"

        while True:
            # Fetch the query
            log.debug("GitHub query: %s", url)
            response = self.request(url)
            if not response.ok:
                try:
                    error = json.loads(response.text)["errors"][0]["message"]
                except KeyError:
                    error = "unknown"
                raise ReportError(
                    f"Failed to fetch GitHub data at '{url}'. "
                    f"The reason was '{response.reason}' "
                    f"and the error was '{error}'.")
            log.data(pretty(response.text))
            # Parse fetched json data
            try:
                data = json.loads(response.text)["items"]
                log.debug(data)
                result.extend(data)
            except requests.exceptions.JSONDecodeError as error:
                log.debug(error)
                raise ReportError(f"GitHub JSON failed: {response.text}.") from error

            # Update url to the next page, break if no next page
            # provided
            if 'next' in response.links:
                url = response.links['next']['url']
            else:
                break

        log.debug("Result: %s fetched", listed(len(result), "item"))
        log.data(pretty(result))
        return result


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Issue
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class Issue():
    """ GitHub Issue """

    def __init__(self, data: dict[str, Any], parent: Stats):
        if parent.options is None:
            raise RuntimeError("Issue Stats parent options not initialized")
        self.data = data
        self.title: str = data["title"]
        matched = re.search(
            r"/repos/([^/]+)/([^/]+)/issues/(\d+)", data["url"])
        if matched is None:
            raise RuntimeError("Malformed GitHub Issue data")
        self.owner: str = matched.groups()[0]
        self.project: str = matched.groups()[1]
        self.id: str = matched.groups()[2]
        self.options: Namespace = parent.options

    def __str__(self) -> str:
        """ String representation """
        label = f"{self.owner}/{self.project}#{str(self.id).zfill(PADDING)}"
        title = self.data["title"].strip() if self.data.get("title") else ""

        # Check for full-message mode
        if getattr(self.options, 'full_message', False) and self.data.get("body"):
            body = self.data["body"].strip()
            # Format body with indentation for multi-line content
            body_lines = [line for line in body.split("\n") if line.strip()]
            formatted_body = "\n        ".join(body_lines)

            if self.options.format == "markdown":
                return (f'[{label}]({self.data["html_url"]}) - {title}'
                        f'\n        {formatted_body}')
            return f'{label} - {title}\n        {formatted_body}'

        # Default: title only
        if self.options.format == "markdown":
            return f'[{label}]({self.data["html_url"]}) - {title}'
        return f'{label} - {title}'

    def __eq__(self, other: object) -> bool:
        """ Equality comparison """
        if isinstance(other, Issue):
            return (
                self.owner == other.owner
                and self.project == other.project
                and self.id == other.id)
        return False

    def __hash__(self) -> int:
        """ Hash function """
        return hash((self.owner, self.project, self.id))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class GitHubStats(Stats):
    """ GitHub Stats """

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional["GitHubStatsGroup"] = None,
                 user: Optional[User] = None):
        self.parent: GitHubStatsGroup
        self.user: User
        self.options: Namespace
        super().__init__(option, name, parent, user)

    def fetch(self) -> None:
        raise NotImplementedError("fetch() not implemented")


class IssuesCreated(GitHubStats):
    """ Issues created """

    def fetch(self) -> None:
        log.info("Searching for issues created by %s", self.user)
        login = self.user.login
        since = self.options.since
        until = GitHub.until(self.options.until)
        query = f"search/issues?q=author:{login}+created:{since}..{until}+type:issue"
        self.stats = [
            Issue(issue, self.parent) for issue in self.parent.github.search(query)]


class IssuesClosed(GitHubStats):
    """ Issues closed """

    def fetch(self) -> None:
        log.info("Searching for issues closed by %s", self.user)
        login = self.user.login
        since = self.options.since
        until = GitHub.until(self.options.until)
        query = f"search/issues?q=assignee:{login}+closed:{since}..{until}+type:issue"
        self.stats = [
            Issue(issue, self.parent) for issue in self.parent.github.search(query)]


class IssueCommented(GitHubStats):
    """ Issues commented """

    def fetch(self) -> None:
        log.info("Searching for issues commented on by %s", self.user)
        login = self.user.login
        since = self.options.since
        until = GitHub.until(self.options.until)
        query = (
            f"search/issues?q=commenter:{login}+updated:{since}..*+type:issue"
            # Filter out Issues created after 'until'
            f"+created:*..{until}"
            )
        commented_issues = self.parent.github.search(query)
        valid_issues = self.parent.github.commented_in_range(
            commented_issues, since.datetime, until.datetime, login
            )
        self.stats = [
            Issue(issue, self.parent) for issue in valid_issues]


class PullRequestsCreated(GitHubStats):
    """ Pull requests created """

    def fetch(self) -> None:
        log.info("Searching for pull requests created by %s", self.user)
        login = self.user.login
        since = self.options.since
        until = GitHub.until(self.options.until)
        query = f"search/issues?q=author:{login}+created:{since}..{until}+type:pr"
        self.stats = [
            Issue(issue, self.parent) for issue in self.parent.github.search(query)]


class PullRequestsCommented(GitHubStats):
    """ Pull requests commented """

    def fetch(self) -> None:
        log.info("Searching for pull requests commented on by %s", self.user)
        login = self.user.login
        since = self.options.since
        until = GitHub.until(self.options.until)
        query = (
            f"search/issues?q=commenter:{login}+updated:{since}..*+type:pr"
            # Filter out PRs created after 'until'
            f"+created:*..{until}"
            )
        commented_issues = self.parent.github.search(query)
        valid_issues = self.parent.github.commented_in_range(
            commented_issues, since.datetime, until.datetime, login
            )
        self.stats = [
            Issue(issue, self.parent) for issue in valid_issues]


class PullRequestsClosed(GitHubStats):
    """ Pull requests closed """

    def fetch(self) -> None:
        log.info("Searching for pull requests closed by %s", self.user)
        login = self.user.login
        since = self.options.since
        until = GitHub.until(self.options.until)
        query = f"search/issues?q=assignee:{login}+closed:{since}..{until}+type:pr"
        self.stats = [
            Issue(issue, self.parent) for issue in self.parent.github.search(query)]


class PullRequestsReviewed(GitHubStats):
    """ Pull requests reviewed """

    def fetch(self) -> None:
        log.info("Searching for pull requests reviewed by %s", self.user)
        login = self.user.login
        since = self.options.since
        until = GitHub.until(self.options.until)
        query = (
            f"search/issues?q=reviewed-by:{login}+-author:{login}"
            f"+closed:{since}..{until}+type:pr"
            )
        self.stats = [
            Issue(issue, self.parent) for issue in self.parent.github.search(query)]


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class GitHubStatsGroup(StatsGroup):
    """ GitHub work """

    # Default order
    order = 330

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional[StatsGroup] = None,
                 user: Optional[User] = None):
        StatsGroup.__init__(self, option, name, parent, user)
        config = dict(Config().section(option))

        # Check server url
        try:
            self.url: str = config["url"]
        except KeyError as keyerr:
            raise ReportError(
                f"No github url set in the [{option}] section") from keyerr

        # Check authorization token
        self.token = get_token(config)
        self.github = GitHub(
            url=self.url,
            token=self.token,
            org=config.get("org"),
            user=config.get("user"),
            repo=config.get("repo"),
            exclude_org=config.get("exclude_org"),
            timeout=float(config.get("timeout", TIMEOUT)))

        # Create the list of stats
        self.stats = [
            IssuesCreated(
                option=f"{option}-issues-created", parent=self,
                name=f"Issues created on {option}"),
            IssueCommented(
                option=f"{option}-issues-commented", parent=self,
                name=f"Issues commented on {option}"),
            IssuesClosed(
                option=f"{option}-issues-closed", parent=self,
                name=f"Issues closed on {option}"),
            PullRequestsCreated(
                option=f"{option}-pull-requests-created", parent=self,
                name=f"Pull requests created on {option}"),
            PullRequestsCommented(
                option=f"{option}-pull-requests-commented", parent=self,
                name=f"Pull requests commented on {option}"),
            PullRequestsClosed(
                option=f"{option}-pull-requests-closed", parent=self,
                name=f"Pull requests closed on {option}"),
            PullRequestsReviewed(
                option=f"{option}-pull-requests-reviewed", parent=self,
                name=f"Pull requests reviewed on {option}"),
            ]
