from . import config

# 必须在导入 llm 之前把 .env 灌进 os.environ，否则 llm 模块级读到的
# API_KEY 是空值，整条大模型链路永远不会启用。
config.load()

from . import data, rag, llm
from .agent import Agent
from .letters import class_report, counselor_brief, parent_letter, student_letter
from .risk import DEFAULT_CONFIG, RiskEngine

__all__ = ["data", "rag", "llm", "config", "Agent", "RiskEngine", "DEFAULT_CONFIG",
           "student_letter", "parent_letter", "counselor_brief", "class_report"]
