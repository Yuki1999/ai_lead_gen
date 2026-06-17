"""Single source of truth for the RBAC permission catalog.

The frontend pulls this catalog via GET /permissions/registry — never hard-code
permission strings or labels in TypeScript. Adding a permission means adding one
row here; both backend enforcement and the role editor UI pick it up automatically.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Permission:
    """One atomic permission. ``key`` is the wire format (``domain:action``)."""

    key: str
    group: str          # group key, used for UI clustering — e.g. "leads"
    group_label: str    # group label shown in UI — e.g. "线索"
    label: str          # this permission's label — e.g. "查看线索"
    description: str    # tooltip / help text


# ── Registry ────────────────────────────────────────────────────────────────
#
# Order within a group decides display order in the role editor.
# Groups appear in the order they first show up below.

PERMISSIONS: tuple[Permission, ...] = (
    Permission("leads:read",       "leads",    "线索", "查看线索",   "查看线索列表与详情"),
    Permission("leads:write",      "leads",    "线索", "编辑线索",   "新建/编辑/删除线索"),

    Permission("outreach:send",    "outreach", "外联", "发送外联",   "发起外联邮件、自拟邮件"),
    Permission("outreach:approve", "outreach", "外联", "审批草稿",   "审批/驳回 Agent 生成的外联草稿"),

    Permission("replies:sync",     "replies",  "回复", "同步回复",   "从邮箱拉取最新回复"),
    Permission("replies:analyze",  "replies",  "回复", "分析回复",   "对回复跑 AI 分析与跟进生成"),

    Permission("settings:read",    "settings", "设置", "查看设置",   "查看产品资料、邮件、Agent 等设置"),
    Permission("settings:write",   "settings", "设置", "修改设置",   "保存产品资料、邮件、Agent 等设置"),

    Permission("users:manage",     "users",    "用户", "管理用户",   "管理用户、角色、权限分配"),

    Permission("agent:chat",       "agent",    "助手", "使用助手",   "调用智能体对话功能"),
)


ALL_PERMISSION_KEYS: tuple[str, ...] = tuple(p.key for p in PERMISSIONS)


def _build_groups() -> "OrderedDict[str, list[Permission]]":
    groups: OrderedDict[str, list[Permission]] = OrderedDict()
    for perm in PERMISSIONS:
        groups.setdefault(perm.group, []).append(perm)
    return groups


PERMISSION_GROUPS: "OrderedDict[str, list[Permission]]" = _build_groups()


# ── Matching ────────────────────────────────────────────────────────────────

def matches(granted: Iterable[str], required: str) -> bool:
    """Return True iff ``granted`` satisfies ``required``.

    Wildcard rules (matching frontend ``hasPermission``):
      - ``"*"`` grants everything.
      - ``"<group>:*"`` grants every action in that group.
      - Exact ``"<group>:<action>"`` matches itself.

    Anything else is treated as a plain string and must match exactly.
    """
    granted_set = set(granted)
    if "*" in granted_set:
        return True
    if required in granted_set:
        return True
    # Wildcard at the group level: "leads:*"
    group, _, _action = required.partition(":")
    if group and f"{group}:*" in granted_set:
        return True
    return False


# ── Serialization for /permissions/registry ─────────────────────────────────

def registry_payload() -> dict[str, object]:
    """Shape consumed by the frontend permission registry."""
    return {
        "permissions": [
            {
                "key": p.key,
                "group": p.group,
                "group_label": p.group_label,
                "label": p.label,
                "description": p.description,
            }
            for p in PERMISSIONS
        ],
        "groups": [
            {
                "key": group_key,
                "label": perms[0].group_label,
                "permissions": [p.key for p in perms],
            }
            for group_key, perms in PERMISSION_GROUPS.items()
        ],
        "presets": [
            {
                "key": "viewer",
                "label": "只读员工",
                "description": "可查看线索和设置，不可修改、不可外联",
                "permissions": ["leads:read", "settings:read"],
            },
            {
                "key": "operator",
                "label": "运营",
                "description": "完整外联与回复处理，但不能管理用户/全局设置",
                "permissions": [
                    "leads:read", "leads:write",
                    "outreach:send", "outreach:approve",
                    "replies:sync", "replies:analyze",
                    "agent:chat",
                ],
            },
            {
                "key": "admin",
                "label": "管理员",
                "description": "拥有全部权限",
                "permissions": ["*"],
            },
        ],
    }
