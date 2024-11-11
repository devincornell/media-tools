import dataclasses


from .big_helper import big_helper

@dataclasses.dataclass
class BigType:
    x: int
    y: int
    z: int

    def helper(self) -> None:
        return big_helper()

