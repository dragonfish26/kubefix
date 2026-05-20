from dataclasses import dataclass

@dataclass
class Warning:
    resource_kind: str
    resource_name: str
    message: str