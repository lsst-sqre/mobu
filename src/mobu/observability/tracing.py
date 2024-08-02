from enum import StrEnum


class Spans(StrEnum):
    """All of the spans that are traced by this application."""

    tap_query = "tap.query"

    notebook_cell = "notebook.cell"
    notebook_clone = "notebook.clone"
    notebook_find = "notebook.find"
    notebook_execute = "notebook.execute"
    notebook_read = "notebook.read"
    notebook_read_metadata = "notebook.read_metadata"
