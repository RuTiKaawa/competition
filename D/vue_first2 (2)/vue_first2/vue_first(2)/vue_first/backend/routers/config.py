import os
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from database import (
    DB_PASSWORD,
    delete_database_workspace,
    get_database_config,
    get_database_profiles,
    save_db_config_to_env,
    switch_database_workspace,
    test_database_connection,
)

router = APIRouter(prefix="/api/config", tags=["配置"])


class DBConfigRequest(BaseModel):
    db_type: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    name: str = "postgres"
    user: str = "postgres"
    password: str = "root"
    test_connection: bool = True


def _active_db_config() -> Dict[str, Any]:
    config = get_database_config()
    return {
        "db_type": config["db_type"],
        "host": config["host"],
        "port": config["port"],
        "name": config["name"],
        "user": config["user"],
        "password": DB_PASSWORD,
    }


@router.get("/databases")
def list_databases() -> Dict[str, Any]:
    config = get_database_config()
    return {"active": config["name"], "databases": get_database_profiles()}


@router.post("/databases/{database_name}/activate")
def activate_database(database_name: str) -> Dict[str, Any]:
    try:
        # 切换工作区：已存在的库直接切换，不存在的库自动创建
        result = switch_database_workspace(database_name, create_if_missing=True)
        return {"success": True, "message": f"已切换到数据库 {result['name']}", "active": result["name"], **result}
    except Exception as exc:
        return {"success": False, "message": f"切换数据库失败: {exc}"}


@router.delete("/databases/{database_name}")
def remove_database(database_name: str) -> Dict[str, Any]:
    try:
        result = delete_database_workspace(database_name)
        return {"success": True, "message": f"数据库 {result['name']} 已删除", **result}
    except Exception as exc:
        return {"success": False, "message": f"删除数据库失败: {exc}"}


@router.get("/db")
def get_db_config() -> Dict[str, Any]:
    return _active_db_config()


@router.post("/db")
def save_db_config(payload: DBConfigRequest) -> Dict[str, Any]:
    try:
        save_db_config_to_env(payload.model_dump())
        # 同步 agent 的连接池
        try:
            from db.executor import reload_pool
            from db.connection_manager import clear_active_cache
            clear_active_cache()
            reload_pool()
        except Exception:
            pass
        if payload.test_connection:
            try:
                test_database_connection(payload.model_dump())
                return {"success": True, "message": "数据库配置已保存并连接成功", "config": _active_db_config()}
            except Exception as exc:
                return {"success": False, "message": f"配置已保存，但测试连接失败: {exc}", "config": _active_db_config()}
        return {"success": True, "message": "数据库配置已保存", "config": _active_db_config()}
    except Exception as exc:
        return {"success": False, "message": f"保存配置失败: {exc}"}
