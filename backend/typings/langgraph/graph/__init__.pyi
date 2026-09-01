from collections.abc import Callable, Mapping, Sequence
from typing import Generic, TypeVar

_State = TypeVar("_State")

START: str
END: str

class CompiledStateGraph(Generic[_State]):
    def invoke(self, input: _State) -> _State: ...

class StateGraph(Generic[_State]):
    def __init__(self, state_schema: type[_State]) -> None: ...
    def add_node(
        self, node: str, action: Callable[[_State], Mapping[str, object]]
    ) -> None: ...
    def add_edge(self, start_key: str, end_key: str) -> None: ...
    def add_conditional_edges(
        self,
        source: str,
        path: Callable[[_State], str],
        path_map: Sequence[str],
    ) -> None: ...
    def compile(self) -> CompiledStateGraph[_State]: ...
