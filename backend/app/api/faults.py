"""装袋相关失败的统一响应形状。

全仓固定为 {"fault", "detail", "at"} 三个键：
- fault：同类失败的稳定标识（连续两次同类失败完全相同）
- detail：面向操作员的具体说明
- at：失败位置，只能是 "route" / "stop" / "pack"
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

FaultAt = Literal["route", "stop", "pack"]

ROUTE_NOT_FOUND = "route_not_found"  # 路线找不到
INVALID_STOP = "invalid_stop"  # 订户点字段不合法
PACK_REJECTED = "pack_rejected"  # 装袋过程业务拒绝


class PackFault(Exception):
    """装袋流程的业务失败；fault/at 是同类失败的稳定标识，detail 面向操作员。"""

    def __init__(self, fault: str, detail: str, at: FaultAt, status_code: int) -> None:
        super().__init__(detail)
        self.fault = fault
        self.detail = detail
        self.at = at
        self.status_code = status_code


def route_not_found(route_id: int) -> PackFault:
    return PackFault(ROUTE_NOT_FOUND, f"路线 {route_id} 不存在", "route", 404)


def invalid_stop(detail: str) -> PackFault:
    return PackFault(INVALID_STOP, detail, "stop", 422)


def pack_rejected(detail: str) -> PackFault:
    return PackFault(PACK_REJECTED, detail, "pack", 409)


async def _pack_fault_handler(_request: Request, exc: PackFault) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"fault": exc.fault, "detail": exc.detail, "at": exc.at},
    )


def install_fault_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PackFault, _pack_fault_handler)
