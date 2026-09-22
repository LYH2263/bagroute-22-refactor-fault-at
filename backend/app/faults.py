"""装袋相关失败的统一响应形状：{"fault", "detail", "at"}。

全仓固定这三个键；at 只能取 route / stop / pack。
fault 是稳定机器码：同类失败重复出现时必须逐字节相同，不得嵌入变量数据
（变量信息只放 detail）。
"""

from fastapi import HTTPException

AT_ROUTE = "route"
AT_STOP = "stop"
AT_PACK = "pack"
_AT_VALUES = frozenset({AT_ROUTE, AT_STOP, AT_PACK})

FAULT_ROUTE_NOT_FOUND = "route_not_found"
FAULT_STOP_INVALID = "stop_invalid"
FAULT_PACK_REJECTED = "pack_rejected"


class PackFault(HTTPException):
    """装袋相关失败。main.py 的异常处理器把它渲染成 fault/detail/at 三键 JSON。"""

    def __init__(self, status_code: int, fault: str, detail: str, at: str) -> None:
        if at not in _AT_VALUES:
            raise ValueError(f"at 只能是 route/stop/pack，收到 {at!r}")
        super().__init__(status_code=status_code, detail=detail)
        self.fault = fault
        self.at = at
