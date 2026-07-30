"""评估框架与项目运行时之间的适配层。"""

from .project_rag import (
    REQUIRED_COLUMNS,
    ProjectRagAdapter,
    build_isolated_engine,
    load_evaluation_rows,
)

__all__ = [
    "REQUIRED_COLUMNS",
    "ProjectRagAdapter",
    "build_isolated_engine",
    "load_evaluation_rows",
]
