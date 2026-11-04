"""The Gold store's read model, assembled from one group of reads per module. [RM-19]"""
from __future__ import annotations

from infrastructure.persistence.gold_reader.reader_base import ReaderBase
from infrastructure.persistence.gold_reader.reads_employee import EmployeeReads
from infrastructure.persistence.gold_reader.reads_risk import RiskReads
from infrastructure.persistence.gold_reader.reads_run_series import RunSeriesReads
from infrastructure.persistence.gold_reader.reads_unit_figures import UnitFigureReads
from infrastructure.persistence.gold_reader.reads_unit_page import UnitPageReads
from infrastructure.persistence.gold_reader.reads_unit_people import UnitPeopleReads


class GoldReader(
    UnitPageReads, UnitFigureReads, UnitPeopleReads, RunSeriesReads, RiskReads, EmployeeReads, ReaderBase
):
    """Reads one client's figures from `tcc_gold`, and nothing else.

    It satisfies `application.gold_read_port.GoldReadPort`. The groups are separate
    classes only to keep each module to one read model; they share `ReaderBase`, and a
    subclass that replaces `_many` or `_batch` (the offline tests run the real
    statements on SQLite that way) changes every group at once.
    """
