"""The model's beliefs: what it carries from step to step, instead of the conversation's words."""

from collections.abc import Iterable, Mapping

from glint.history import BeliefRevision, Entry


class Beliefs:
    """What the model believes now: statements it holds true, by number. Numbers are never reused."""

    def __init__(self, entries: Iterable[Entry] = ()):
        """The beliefs the entries' revisions leave, as when a saved history is loaded."""
        self._current: dict[int, str] = {}
        self._last_number = 0  # the highest added so far, dropped or not
        for entry in entries:
            if isinstance(entry, BeliefRevision):
                self.apply(entry)

    @property
    def current(self) -> Mapping[int, str]:
        """The beliefs, in the order they were added."""
        return self._current

    @property
    def next_number(self) -> int:
        """The number for the next new belief."""
        return self._last_number + 1

    def apply(self, revision: BeliefRevision) -> None:
        """Drop and add the revision's beliefs. Raises ValueError if it drops one not held."""
        unknown = set(revision.drop) - self._current.keys()
        if unknown:
            raise ValueError(f"Dropped beliefs not held: {sorted(unknown)}.")
        for number in revision.drop:
            del self._current[number]
        self._current.update(revision.add)
        self._last_number = max([self._last_number, *revision.add])
