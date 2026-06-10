from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ParsedDocument:
    text: str
    pages: list[dict]
    metadata: dict


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        raise NotImplementedError
