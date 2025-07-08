"""
Sentry stats such as commented and resolved issues.

Configuration example::

    [sentry]
    type = sentry
    url = https://sentry.io/api/0/
    organization = team
    token = ...

You need to generate authentication token at the server. The only
scope you need to enable is `org:read`. If you prefer to store the
token in a file, use ``token_file`` to point to the file that has
your token.

It's also possible to set a timeout, if not specified it defaults to
60 seconds.

    timeout = 10
"""

import re
from argparse import Namespace
from typing import Any, Optional

import dateutil
import dateutil.parser
import requests

from did.base import Config, ConfigError, ReportError, User, get_token
from did.stats import Stats, StatsGroup
from did.utils import listed, log, pretty

NEXT_PAGE = re.compile('<([^>]+)>; rel="next"; results="true"')

# Default number of seconds waiting on Sentry before giving up
TIMEOUT = 60.0


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Issue & Activity
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class Issue():
    """ Sentry Issue """
    # pylint: disable=too-few-public-methods

    def __init__(self, issue: dict[str, str]) -> None:
        """ Initialize issue """
        self.identifier = issue["shortId"]
        self.title = issue["title"]

    def __str__(self) -> str:
        """ Unicode representation """
        return f"{self.identifier} - {self.title}"


class Activity():
    """ Sentry Activity """
    # pylint: disable=too-few-public-methods

    def __init__(self, activity: dict[str, Any]) -> None:
        """ Initialize issue """
        self.issue: Issue = Issue(activity['issue'])
        self.user = activity['user']
        self.kind = activity['type']
        # Parse creation date
        self.created = dateutil.parser.parse(activity["dateCreated"]).date()

    def __str__(self) -> str:
        """ Unicode representation """
        return f"{self.created} [{self.kind}] {self.issue}"


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Sentry Investigator
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class Sentry():
    """ Sentry API """

    def __init__(self,
                 config: dict[str, str],
                 stats: "SentryStatsGroup",
                 timeout: float = TIMEOUT) -> None:
        """ Initialize API """
        self.url = config['url'].rstrip('/')
        self.organization = config['organization']
        self.headers = {'Authorization': f'Bearer {config["token"]}'}
        self._activities: Optional[list[Activity]] = None
        self.stats: SentryStatsGroup = stats
        self.timeout: float = timeout
        if self.stats.options is None:
            raise RuntimeError("options not initialized for SentryStatsGroup")

    def activities(self) -> list[Activity]:
        """ Return all activities (fetch only once) """
        if self._activities is None:
            self._activities = self._fetch_activities()
        return self._activities

    def issues(self, kind: str, email: str) -> list[str]:
        """ Filter unique issues for given activity type and email """
        return list({
            str(activity.issue)
            for activity in self.activities()
            if kind == activity.kind and activity.user['email'] == email})

    def _fetch_activities(self) -> list[Activity]:
        """ Get organization activity, handle pagination """
        if self.stats.options is None:
            raise RuntimeError("options not initialized for SentryStatsGroup")
        activities: list[Activity] = []
        # Prepare url of the first page
        url: Optional[str] = f'{self.url}/organizations/{self.organization}/activity/'
        while url:
            # Fetch one page of activities
            try:
                log.debug('Fetching activity data: %s', url)
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
                if not response.ok:
                    log.error(response.text)
                    raise ReportError('Failed to fetch Sentry activities.')
                data = response.json()
                log.data(f"Response headers:\n{pretty(response.headers)}")
                log.debug("Fetched %s.", listed(len(data), 'activity'))
                log.data(pretty(data))
                for activity in [Activity(item) for item in data]:
                    # We've reached the last page, older records not
                    # relevant
                    if activity.created < self.stats.options.since.date:
                        return activities
                    # Store only relevant activities (before until date)
                    if activity.created < self.stats.options.until.date:
                        log.details(f"Activity: {activity}")
                        activities.append(activity)
            except requests.RequestException as error:
                log.debug(error)
                raise ReportError(
                    f'Failed to fetch Sentry activities from {url}') from error
            # Check for possible next page
            try:
                match = NEXT_PAGE.search(response.headers['Link'])
                url = match.groups()[0] if match else None
            except AttributeError:
                url = None
        return activities

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class SentryStats(Stats):
    """ Sentry stats """

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional["SentryStatsGroup"] = None,
                 user: Optional[User] = None) -> None:
        self.parent: SentryStatsGroup
        self.user: User
        self.options: Namespace
        Stats.__init__(self, option, name, parent, user)

    def fetch(self) -> None:
        raise NotImplementedError("Not implemented")


class ResolvedIssues(SentryStats):
    """ Issues resolved """

    def fetch(self) -> None:
        log.info("Searching for issues resolved by %s", self.user)
        self.stats = self.parent.sentry.issues(
            kind='set_resolved', email=self.user.email)


class CommentedIssues(SentryStats):
    """ Issues commented """

    def fetch(self) -> None:
        log.info("Searching issues commented by %s", self.user)
        self.stats = self.parent.sentry.issues(
            kind='note', email=self.user.email)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class SentryStatsGroup(StatsGroup):
    """ Sentry stats """

    # Default order
    order = 650

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional[StatsGroup] = None,
                 user: Optional[User] = None) -> None:
        StatsGroup.__init__(self, option, name, parent, user)
        # Check config for required fields
        config = dict(Config().section(option))
        for field in ['url', 'organization']:
            if field not in config:
                raise ConfigError(f"No {field} set in the [{option}] section")
        token = get_token(config)
        if token is None:
            raise ConfigError(
                f"No token or token_file set in the [{option}] section")
        config["token"] = token
        # Set up the Sentry API and construct the list of stats
        if self.options is not None:
            # options is not initialized with --help
            self.sentry = Sentry(
                config=config,
                stats=self,
                timeout=float(config.get("timeout", TIMEOUT)))
        self.stats = [
            ResolvedIssues(option=option + '-resolved', parent=self),
            CommentedIssues(option=option + '-commented', parent=self),
            ]
