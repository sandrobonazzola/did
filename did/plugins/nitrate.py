"""
Nitrate stats such as created test plans, runs, cases

Config example::

    [nitrate]
    type = nitrate
"""

from argparse import Namespace
from typing import Optional

import nitrate  # type: ignore[import-untyped]

from did.base import User
from did.stats import Stats, StatsGroup
from did.utils import log

TEST_CASE_COPY_TAG = "TestCaseCopy"


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Nitrate Stats
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class NitrateStats(Stats):
    """ Nitrate stats """

    def __init__(self,
                 option: str,
                 name: Optional[str] | None = None,
                 parent: Optional["NitrateStatsGroup"] = None,
                 user: Optional[User] = None) -> None:
        self.parent: NitrateStatsGroup
        self.user: User
        self.options: Namespace
        Stats.__init__(self, option, name, parent, user)

    def fetch(self) -> None:
        raise NotImplementedError("Subclasses must implement fetch")


class NitratePlans(NitrateStats):
    """ Test plans created """

    def fetch(self) -> None:
        log.info("Searching for test plans created by %s", self.user)
        self.stats.extend(nitrate.TestPlan.search(
            is_active=True,
            author__email=self.user.email,
            create_date__gt=str(self.options.since),
            create_date__lt=str(self.options.until)))


class NitrateRuns(NitrateStats):
    """ Test runs finished """

    def fetch(self) -> None:
        log.info("Searching for test runs finished by %s", self.user)
        self.stats.extend(nitrate.TestRun.search(
            default_tester__email=self.user.email,
            stop_date__gt=str(self.options.since),
            stop_date__lt=str(self.options.until)))


class AutomatedCases(NitrateStats):
    """ Automated cases created """

    def fetch(self) -> None:
        self.stats = [
            case for case in self.parent.cases
            if case.automated and case not in self.parent.copies]


class AutoproposedCases(NitrateStats):
    """ Cases proposed for automation """

    def fetch(self) -> None:
        self.stats = [
            case for case in self.parent.cases
            if case.autoproposed and not case.automated and
            case not in self.parent.copies]


class ManualCases(NitrateStats):
    """ Manual cases created """

    def fetch(self) -> None:
        self.stats = [
            case for case in self.parent.cases
            if not case.automated and case not in self.parent.copies]


class CopiedCases(NitrateStats):
    """ Test cases copied """

    def fetch(self) -> None:
        self.stats = self.parent.copies[:]


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Stats Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class NitrateStatsGroup(StatsGroup):
    """ Nitrate stats """

    # Default order
    order = 100

    def __init__(self,
                 option: str,
                 name: Optional[str] = None,
                 parent: Optional[StatsGroup] = None,
                 user: Optional[User] = None) -> None:
        StatsGroup.__init__(self, option, name, parent, user)
        self._cases: Optional[list[nitrate.TestCase]] = None
        self._copies: Optional[list[nitrate.TestCase]] = None
        self.stats = [
            NitratePlans(option=f"{option}-plans", parent=self),
            NitrateRuns(option=f"{option}-runs", parent=self),
            AutomatedCases(option=f"{option}-automated", parent=self),
            ManualCases(option=f"{option}-manual", parent=self),
            AutoproposedCases(option=f"{option}-proposed", parent=self),
            CopiedCases(option=f"{option}-copied", parent=self),
            ]

    @property
    def cases(self) -> list[nitrate.TestCase]:
        """ All test cases created by the user """
        if self.user is None:
            raise ValueError("User is required")
        if self.options is None:
            raise ValueError("Options are required")
        if self._cases is None:
            log.info("Searching for cases created by %s", self.user)
            disabled_status = nitrate.CaseStatus("DISABLED")
            self._cases = [
                case for case in nitrate.TestCase.search(
                    author__email=self.user.email,
                    create_date__gt=str(self.options.since),
                    create_date__lt=str(self.options.until))
                if case.status != disabled_status]
        return self._cases

    @property
    def copies(self) -> list[nitrate.TestCase]:
        """ All test case copies created by the user """
        if self._copies is None:
            if self.user is None:
                raise ValueError("User is required")
            if self.options is None:
                raise ValueError("Options are required")
            log.info("Searching for cases copied by %s", self.user)
            self._copies = list(nitrate.TestCase.search(
                author__email=self.user.email,
                create_date__gt=str(self.options.since),
                create_date__lt=str(self.options.until),
                tag__name=TEST_CASE_COPY_TAG))
        return self._copies
