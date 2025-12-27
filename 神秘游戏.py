# -*- coding: utf-8 -*-
"""
神秘游戏 推演模拟器（Tkinter）
"""
import random
import re
import math

HW_CID = 1001  # NPC: 洪伟
LDL_CID = 1002  # NPC: 李东雷
try:
# tkinter is only needed for the desktop GUI.
# Streamlit/Cloud environments often do not provide Tk.
try:
    import tkinter as tk  # type: ignore
# [patched for Streamlit]     from tkinter import ttk, messagebox  # type: ignore
except Exception:  # ImportError / TclError etc.
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore
    import tkinter.font as tkfont
# [patched for Streamlit]     from tkinter import ttk
# [patched for Streamlit]     from tkinter import messagebox
except ModuleNotFoundError:
    # Headless environment (e.g., server / CI): allow importing engine logic without Tk.
    import types as _types
    tk = _types.SimpleNamespace(Tk=object)
    tkfont = None
    ttk = None
    messagebox = None

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
# =========================
# Windows DPI Awareness (avoid blur on 4K/HiDPI)
# =========================
def set_dpi_awareness():
    """Make Tkinter app DPI-aware on Windows so it won't look blurry on 4K displays."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware (Win 8.1+)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()  # System DPI aware (older)
        except Exception:
            pass
# =========================
# 数据结构
# =========================
@dataclass
class Status:
    # 通用
    shields: int = 0          # 临时护盾层数（最多2，与 shield_perm 合计）
    shield_ttl: int = 0       # 临时护盾持续回合（>0每回合-1，到0清空 shields）
    shield_perm: int = 0      # 可持续护盾层数（不衰减，直到被消耗）
    thunder: int = 0          # 雷霆层数（第5/6/7名每回合+1，叠满3死亡）
    sealed: int = 0           # 封印剩余回合（主动无效）
    forgotten: int = 0        # 遗忘剩余回合（主动无效）
    perma_disabled: bool = False  # 遗策/永久失效（主动+被动都无效）
    # 集火（重做版）
    focused: bool = False
    invisible: bool = False      # 隐身：不会被技能选中（不包括世界规则）

    bomb: bool = False           # 炸弹：姚舒馨(40)烈焰炸弹标记
    vyzy: bool = False           # 越挫越勇：季任杰(34)棕色状态
    shenwei: bool = False        # 神威：施禹谦(36)金色状态效果

    fish: bool = False           # 鱼：游鱼归渊牵引
    dying_ttl: int = 0          # 濒亡：剩余回合数（>0不能行动）
    attached_life: bool = False  # 附生：携带李知雨残灯复明
    lone_wolf: bool = False      # 孤军奋战：永久效果
    spec_immune_ttl: int = 0     # 特异性免疫：剩余回合数（>0本回合无敌，仍受世界规则）
    spec_immune_gained_this_turn: bool = False  # 本回合是否新获得特异性免疫（用于沈澄婕触发判定）
    # 说明（新）：focused 不再是“随机技能必中该目标”
    # 而是“自我反噬集火”：
    # 若某角色带 focused，则其下一次发动的技能中，只要存在“有概率选中自己”的随机目标判定，
    # 则该判定必然选中自己；触发后 focused 立即消失。
    # ——为工程化实现：我们只在“随机选择目标”的 helper 中检查此规则。
    dusk_mark: int = 0            # Sunny 死亡触发：黄昏标记（每次发动主动后-1名）
    next_target_random: bool = False  # 留痕：下次技能目标随机
    doubled_move_next: bool = False   # 厄运预兆：下回合“排名变动效果”翻倍一次
    # mls
    mls_immune_used: int = 0
    mls_immune_used_this_turn: bool = False
    # 左右脑
    revives_left: int = 2
    # hewenx 怨念
    hewenx_curse: Optional[Dict[str, Any]] = None  # {"killer":cid, "threshold_rank":rank_at_death}
    # Sunny
    photosyn_energy: int = 0
    corrupted: bool = False
    sunny_revive_used: bool = False
    # 沈澄婕(33) 记录存活者集合（用于“每回合记录存活者获得特异免疫”逻辑）
    scj_recorded_alive: set = field(default_factory=set)
    scj_layers: int = 0  # 沈澄婕(33) 记录层数（用于特异免疫获取上限3）
    # 豆父
    father_world_boost_count: int = 0
    father_world_immune_used: bool = False
    # 钟无艳（仅保留巾帼护盾计数）
    zhong_triggers: int = 0
    # 朱昊泽：绝息效果（剩余回合数，>0 表示对朱昊泽(4)发动技能会被免疫一次）
    juexi_ttl: int = 0
    # 随机事件新增状态
    hongwei_gift_shield: int = 0     # 洪伟之赐：可抵挡一次伤害（相当于盾），>0 表示存在
    thunder_wrist_shield: int = 0    # 雷霆手腕：可抵挡一次伤害（相当于盾），>0 表示存在
    oxid_ttl: int = 0                # 氧化：剩余回合（深绿色），每回合上升1名
    reduce_ttl: int = 0              # 还原：剩余回合（深绿色），每回合下降1名

    witness: bool = False           # 目击：谢承哲破绽洞察
    defense_ttl: int = 0            # 辩护：剩余回合数（金色），每回合上升1名

    silent_ttl: int = 0           # 静默：严雅
    detour_ttl: int = 0           # 迂回：陈心如
    frontline_cd: int = 0         # 迫近战线冷却：张志成
    defense_line_ttl: int = 0     # 防线：蒋骐键
    defense_line_block: bool = False  # 防线抵消次数

    def total_shields(self) -> int:
        return min(2, max(0, self.shield_perm) + max(0, self.shields))
    def brief(self) -> str:
        parts: List[str] = []
        if self.total_shields() > 0:
            parts.append(f"护盾{self.total_shields()}")
        # Joke mode display only
        if self.__dict__.get("fake_99999", False):
            parts.append("护盾99999")
        if self.thunder:
            parts.append(f"雷霆{self.thunder}")
        if self.sealed:
            parts.append("封印")
        if self.forgotten:
            parts.append(f"遗忘{self.forgotten}")
        if self.focused:
            parts.append("集火")
        if self.invisible:
            parts.append("隐身")
        if self.bomb:
            parts.append("炸弹")
        if self.vyzy:
            parts.append("越挫越勇")
        if getattr(self, "shenwei", False):
            parts.append("神威")
        if self.fish:
            parts.append("鱼")
        if self.dying_ttl:
            parts.append(f"濒亡{self.dying_ttl}")
        if self.attached_life:
            parts.append("附生")
        if self.lone_wolf:
            parts.append("孤军奋战")
        if self.spec_immune_ttl:
            parts.append("特异性免疫")
        if getattr(self, "purify_ttl", 0) > 0:
            parts.append(f"净化{self.purify_ttl}")
        if getattr(self, "shenghui_ttl", 0) > 0:
            parts.append(f"圣辉{self.shenghui_ttl}")
        if getattr(self, "dian", 0) > 0:
            parts.append(f"感电{self.dian}")
        if getattr(self, "chase", 0) > 0:
            parts.append(f"乘胜追击{self.chase}")
        if getattr(self, "witness", False):
            parts.append("目击")
        if getattr(self, "defense_ttl", 0) > 0:
            parts.append(f"辩护{self.defense_ttl}")
        if getattr(self, "silent_ttl", 0) > 0:
            parts.append(f"静默{self.silent_ttl}")
        if getattr(self, "detour_ttl", 0) > 0:
            parts.append(f"迂回{self.detour_ttl}")
        if getattr(self, "defense_line_ttl", 0) > 0:
            parts.append(f"防线{self.defense_line_ttl}")
        if self.perma_disabled:
            parts.append("遗策")
        if self.dusk_mark:
            parts.append(f"黄昏{self.dusk_mark}")
        if self.next_target_random:
            parts.append("留痕")
        if self.doubled_move_next:
            parts.append("厄运")
        if self.corrupted:
            parts.append("腐化")
        if self.juexi_ttl:
            parts.append(f"绝息{self.juexi_ttl}")

        if getattr(self, "hongwei_gift_shield", 0) > 0:
            parts.append("洪伟之赐")
        if getattr(self, "thunder_wrist_shield", 0) > 0:
            parts.append("雷霆手腕")
        if getattr(self, "oxid_ttl", 0) > 0:
            parts.append("氧化")
        if getattr(self, "reduce_ttl", 0) > 0:
            parts.append("还原")

        return "；".join(parts)
@dataclass
class Role:
    cid: int
    name: str
    alive: bool = True
    status: Status = field(default_factory=Status)
    mem: Dict[str, Any] = field(default_factory=dict)
@dataclass
class DeathRecord:
    victim: int
    killer: Optional[int]  # None = 世界规则/未知
    reason: str
# =========================
# 引擎
# =========================
class Engine:
    def _error_log_path(self) -> str:
        import os
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            base = os.getcwd()
        return os.path.join(base, "error_log.txt")

    def _status_sig_no_silent(self, cid: int) -> str:
        """Return status brief string excluding 静默 for comparisons."""
        b = self.roles[cid].status.brief()
        parts = [p for p in b.split("，") if not p.startswith("静默")]
        return "，".join(parts)

    def __init__(self, seed: Optional[int] = None, fast_mode: bool = False):
        self.rng = random.Random(seed)
        self.base_seed = seed  # None => fully random each new_game
        self.fast_mode = fast_mode
        # Joke mode (UI toggle)
        self.joke_mode = False
        # Simulation safety: track skill exceptions (even in fast_mode)
        self.skill_exception_count = 0
        self.skill_exception_examples = []  # store a few (cid, exc)
        self.export_error_log = False
        self._active_logged = set()
        self.turn = 0
        self.world_event_triggered_this_turn = False  # 本回合是否触发世界事件
        self.roles: Dict[int, Role] = {}
        self.rank: List[int] = []
        self.log: List[str] = []
        # 回放帧：每条log一帧（仅非fast_mode）
        self.replay_frames: List[Dict[str, Any]] = []
        self._cid_pat = re.compile(r"\((\d{1,3})\)")
        self.game_over = False
        self.no_death_streak = 0
        self.pending_endgame_execute = False
        self.elimination_order: List[int] = []
        self.elimination_turn: Dict[int, int] = {}
        self.deaths_this_turn: List[DeathRecord] = []
        self.twin_pair: Tuple[int, int] = (13, -1)  # 13与随机一人绑定；-1表示未绑定
        # 随机事件NPC
        self.HW_CID = 1001  # 洪伟
        self.LDL_CID = 1002  # 李东雷
        self.start_rank_snapshot: Dict[int, int] = {}
        # 每局固定的主动技能发动顺序（新规则：开局随机生成，之后每回合按此顺序）
        self.skill_order: List[int] = []
        self._init_roles()
        self.new_game()
    def _init_roles(self):
        # 删除：潘乐一(2)、姚宇涛(5)、众议院(22)
        data = [
            (1, "金逸阳"),
            (3, "施沁皓"),
            (4, "朱昊泽"),
            (6, "牵寒"),
            (7, "hewenx"),
            (8, "增进舒"),
            (9, "书法家"),
            (10, "mls"),
            (11, "豆进天"),
            (12, "放烟花"),
            (13, "藕禄"),
            (14, "郑孑健"),
            (15, "施博理"),
            (16, "合议庭"),
            (17, "路济阳"),
            (18, "更西部"),
            (19, "释延能"),
            (20, "豆进天之父"),
            (21, "钟无艳"),
            (23, "梅雨神"),
            (24, "左右脑"),
            (25, "找自称"),
            (26, "Sunnydayorange"),
            (27, "黄伶俐"),
            (28, "黄梓睿"),
            (29, "严雅"),
            (30, "陈心如"),
            (31, "李知雨"),
            (32, "范一诺"),
            (33, "沈澄婕"),
            (34, "季任杰"),
            (35, "虞劲枫"),
            (36, "施禹谦"),
            (37, "谢承哲"),
            (38, "陆泽灏"),
            (39, "朱诚"),
            (40, "姚舒馨"),
            (41, "张志成"),
            (42, "俞守衡"),
            (43, "卞一宸"),
            (44, "冷雨霏"),
            (45, "蒋骐键"),
            (46, "戚银潞"),
        ]
        self.roles = {cid: Role(cid, name) for cid, name in data}
    # ---------- 通用 ----------
    def N(self, cid: int) -> str:
        name = self.roles[cid].name.strip()
        return f"{name}({cid})"
    def alive_ids(self) -> List[int]:
        return [cid for cid in self.rank if self.roles[cid].alive]
    def pos(self, cid: int) -> Optional[int]:
        try:
            return self.rank.index(cid)
        except ValueError:
            return None
    def rank_no(self, cid: int) -> Optional[int]:
        p = self.pos(cid)
        return None if p is None else p + 1
    def _compact(self):
        self.rank = [cid for cid in self.rank if self.roles[cid].alive]


    def _check_shenwei_loss(self):
        """施禹谦(36) 神威：只要不在第一名，立即消失。"""
        if 36 not in self.roles:
            return
        r = self.roles[36]
        if (not r.alive) or r.status.perma_disabled:
            return
        if r.status.shenwei and self.rank_no(36) != 1:
            before = r.status.brief()
            r.status.shenwei = False
            self._log("  · 神威消失：施禹谦(36) 不在第一名 → 神威立刻消失")
            self._on_status_change(36, before)

    def _snapshot(self) -> Dict[str, Any]:
        if self.fast_mode:
            return {"turn": self.turn, "rank": [], "status": {}}
        alive_rank = [cid for cid in self.rank if self.roles[cid].alive]
        status_map: Dict[int, Any] = {}
        for cid, r in self.roles.items():
            status_map[cid] = {"alive": r.alive, "brief": r.status.brief(), "name": r.name}
        return {"turn": self.turn, "rank": alive_rank[:], "status": status_map}
    def _log(self, s: str):
        if self.fast_mode:
            return
        # 日志净化：删除所有全角括号内容（例如（现为2层）、（死亡触发：…）等）
        # 不影响角色编号形式的半角括号 (cid)
        s = re.sub(r"（[^）]*）", "", s)
        self.log.append(s)
        highlights: List[int] = []
        try:
            for m in self._cid_pat.finditer(s):
                cid = int(m.group(1))
                if cid in self.roles:
                    highlights.append(cid)
        except Exception:
            highlights = []
        seen = set()
        highlights = [x for x in highlights if not (x in seen or seen.add(x))]
        self.replay_frames.append({"text": s, "snap": self._snapshot(), "highlights": highlights})
    # ---------- 随机目标 helper（实现重做后的“集火”） ----------
    def pick_random(self, actor: int, pool: List[int], desc: str) -> Optional[int]:
        """从pool里随机选一个。若actor带 focused，则只要 pool 里包含 actor，必选 actor，并消耗 focused。"""
        if not pool:
            return None
        # 隐身：不会被任何技能选中（不包括世界规则）；因此从技能随机池中剔除隐身目标
        pool = [x for x in pool if (x == actor) or (not self.roles[x].status.invisible)]
        if not pool:
            return None
        st = self.roles[actor].status
        if st.focused and actor in pool:
            st.focused = False
            self._log(f"  · 集火触发：{self.N(actor)} 的随机判定必选自己（{desc}），集火消失")
            return actor
        return self.rng.choice(pool)
    def set_unique_focus(self, target: int, note: str = ""):
        """Ensure there is at most one focused on the field: new focus overrides the old one."""
        for cid, r in self.roles.items():
            if r.status.focused and cid != target:
                r.status.focused = False
        self.roles[target].status.focused = True
        if note and (not self.fast_mode):
            self._log(note)
    # ---------- 护盾 ----------
    def _max2_shield_add(self, st: Status, add: int, ttl: int = 1, perm: bool = False):
        cur = st.total_shields()
        can = max(0, 2 - cur)
        add2 = min(add, can)
        if add2 <= 0:
            return
        if perm:
            st.shield_perm += add2
        else:
            st.shields += add2
            st.shield_ttl = max(st.shield_ttl, ttl)
    def give_shield(self, cid: int, n: int = 1, ttl: int = 1, perm: bool = False, note: str = ""):
        r = self.roles[cid]
        before_brief = r.status.brief()
        if not r.alive:
            return
        before = r.status.total_shields()
        self._max2_shield_add(r.status, n, ttl=ttl, perm=perm)
        after = r.status.total_shields()
        if after > before:
            self._log(f"  · {self.N(cid)} 获得护盾+{after-before}" + (f"（{note}）" if note else ""))
            self._oulu_bump_on_status_change(cid, before_brief)
    def consume_shield_once(self, cid: int) -> bool:
        before_brief = self.roles[cid].status.brief()
        st = self.roles[cid].status
        if st.shields > 0:
            st.shields -= 1
            # 找自称(25)：护盾被破后立刻上升5名
            if cid == 25 and st.shields == 0 and self.roles[25].alive and (not st.perma_disabled):
                self.move_by(25, -5, source=None, note="护盾被破上升5名")
            self._oulu_bump_on_status_change(cid, before_brief)
            return True
        if st.shield_perm > 0:
            st.shield_perm -= 1
            self._oulu_bump_on_status_change(cid, before_brief)
            return True        # 洪伟之赐 / 雷霆手腕：各自抵挡一次伤害
        if getattr(st, "hongwei_gift_shield", 0) > 0:
            st.hongwei_gift_shield = 0
            self._log(f"  · 洪伟之赐抵死：{self.N(cid)}（消耗）")
            self._oulu_bump_on_status_change(cid, before_brief)
            return True
        if getattr(st, "thunder_wrist_shield", 0) > 0:
            st.thunder_wrist_shield = 0
            self._log(f"  · 雷霆手腕抵死：{self.N(cid)}（消耗）")
            self._oulu_bump_on_status_change(cid, before_brief)
            return True

        return False
    # ---------- 可行动 ----------
    def can_act(self, cid: int) -> bool:
        r = self.roles[cid]
        if not r.alive:
            return False
        if r.status.perma_disabled:
            return False
        if r.status.sealed > 0:
            return False
        if r.status.forgotten > 0:
            return False
        if r.status.dying_ttl > 0:
            return False
        return True

    def _on_status_change(self, cid: int, before: str):
        """统一处理“状态发生变化”后的被动。before/after 使用 Status.brief()。"""
        if cid not in self.roles:
            return
        after = self.roles[cid].status.brief()
        if after == before:
            return

                # 44 冷雨霏：无懈可击——每次自身状态变化，获得1层乘胜追击（最高5）
        if cid == 44 and self.roles[44].alive and (not self.roles[44].status.perma_disabled):
            st44 = self.roles[44].status
            before_chase = getattr(st44, "chase", 0)
            st44.chase = min(3, before_chase + 1)
            if st44.chase != before_chase:
                self._log(f"  · 无懈可击：{self.N(44)} 获得1层【乘胜追击】(当前{st44.chase}/3)")

        # 13 藕禄：风过无痕——状态变化就上升一位
        if cid == 13 and self.roles[13].alive and (not self.roles[13].status.perma_disabled):
            self.move_by(13, -1, source=None, note="风过无痕")

        # 33 沈澄婕：特异性免疫（新获得的状态类型立即记录并给予免疫）
        if cid == 33:
            self._scj_sync_and_grant()

        # 规则：每次“记录到新的状态效果”时，都获得1回合特异性免疫（仍受世界规则）
        if cid == 33 and self.roles[33].alive and (not self.roles[33].status.perma_disabled):
            before_set = set([x for x in before.split("；") if x.strip()])
            after_set = set([x for x in after.split("；") if x.strip()])
            gained = [x for x in (after_set - before_set) if x]

            marked = set(self.roles[33].mem.get("scj_marked", []))
            new_recorded = False
            for tag in gained:
                # 雷霆从1到2等升级也视为“获得新特性”并触发特异性免疫
                if "雷霆" in tag:
                    new_recorded = True
                if tag not in marked:
                    marked.add(tag)
                    new_recorded = True
            self.roles[33].mem["scj_marked"] = list(marked)

            if new_recorded:
                before = self.roles[33].status.spec_immune_ttl
                self.roles[33].status.spec_immune_ttl = max(self.roles[33].status.spec_immune_ttl, 2)
                if before == 0 and self.roles[33].status.spec_immune_ttl > 0:
                    self.roles[33].status.spec_immune_gained_this_turn = True
                self._log("  · 特异性免疫：记录到新状态 → 本回合无敌（仍受世界规则）")
                self.move_by(33, -5, source=None, note="特异性免疫强化上升5名")

    def _oulu_bump_on_status_change(self, cid: int, before: str):
        """藕禄(13) 被动：状态效果发生改变时，排名上升一位。"""
        if cid != 13:
            return
        if (13 not in self.roles) or (not self.roles[13].alive) or self.roles[13].status.perma_disabled:
            return
        after = self.roles[13].status.brief()
        if after != before:
            self.move_by(13, -1, source=None, note="风过无痕")
    # ---------- 绝息免疫（朱昊泽重做需求） ----------
    def _juexi_blocks(self, source: Optional[int], target: int, effect: str) -> bool:
        """若 source 带绝息且 target 为朱昊泽(4)，则朱昊泽免疫该次技能影响并消耗 source 的绝息。
        返回 True 表示已被绝息拦截（后续应停止对 target 的作用）。
        """
        if target != 4 or source is None:
            return False
        if source not in self.roles:
            return False
        st = self.roles[source].status
        if (not self.roles[source].alive) or st.perma_disabled:
            return False
        if st.juexi_ttl > 0:
            st.juexi_ttl = 0
            self._log(f"  · 【绝息免疫】{self.N(4)} 免疫来自 {self.N(source)} 的技能效果（{effect}），并使其绝息消失")
            return True
        return False

    def apply_selection(self, source: Optional[int], target: int, effect: str) -> bool:
        """统一“被技能选中”入口。返回True表示允许继续；False表示该技能对target无效。
        - source is None 视为世界规则（不触发隐身/绝地反击/特异免疫等技能免疫）
        """
        if target not in self.roles or (not self.roles[target].alive):
            return False

        # 世界规则不受这些免疫影响
        if source is None:
            return True

        # 隐身：不被任何技能选中（不包括世界规则）
        if self.roles[target].status.invisible:
            self._log(f"  · 隐身免疫：{self.N(target)} 免疫来自 {self.N(source)} 的技能影响（{effect}）")
            return False

        # 虞劲枫(35)：绝地反击
        if target == 35 and (not self.roles[35].status.perma_disabled):
            mem = self.roles[35].mem.setdefault("yjf_hits", {})  # source->count
            key = str(source)
            mem[key] = int(mem.get(key, 0)) + 1
            cnt = mem[key]
            if cnt >= 2 and source in self.roles and self.roles[source].alive:
                self._log(f"  · 绝地反击：{self.N(35)} 第二次被 {self.N(source)} 选中 → 反击淘汰 {self.N(source)}")
                # 反击为技能淘汰（source=35），绕过护盾/复活
                self.kill(source, 35, "绝地反击反杀", bypass_shield=True, bypass_revive=True)
            else:
                self._log(f"  · 绝地反击：{self.N(35)} 被 {self.N(source)} 选中 → 免疫（第{cnt}次）")
            return False

        return True

    def set_status(self, target: int, attr: str, value, source: Optional[int], note: str = "") -> bool:
        """对某个状态字段做写入：走统一选中入口 + 状态变化钩子。"""
        if not self.apply_selection(source, target, note or f"状态:{attr}"):
            return False
        before = self.roles[target].status.brief()
        setattr(self.roles[target].status, attr, value)
        self._on_status_change(target, before)
        return True


    def _scj_status_types(self) -> set:
        """沈澄婕(33) 当前拥有的状态“类型集合”（不含层数/剩余回合数）。"""
        if 33 not in self.roles:
            return set()
        st = self.roles[33].status
        types = set()
        if st.thunder > 0:
            types.add("雷霆")
        if st.corrupted:
            types.add("腐化")
        if st.shields > 0:
            types.add("护盾")
        if st.sealed > 0:
            types.add("封印")
        if st.forgotten > 0:
            types.add("遗忘")
        if st.dusk_mark > 0:
            types.add("暮印")
        if st.focused:
            types.add("集火")
        if getattr(st, "invisible", False):
            types.add("隐身")
        if getattr(st, "fish", False):
            types.add("鱼")
        if getattr(st, "dying_ttl", 0) > 0:
            types.add("濒亡")
        if getattr(st, "attached_life", False):
            types.add("附生")
        if getattr(st, "lone_wolf", False):
            types.add("孤军奋战")
        if getattr(st, "juexi_ttl", 0) > 0:
            types.add("绝息")
        # 特异免疫本身也算一种状态；记录它并不会再触发自己（避免循环）
        if getattr(st, "spec_immune_ttl", 0) > 0:
            types.add("特异性免疫")
        return types

    def _scj_sync_and_grant(self):
        """确保：沈澄婕每次获得一个“之前未记录过的存活玩家”，就会补一个层数（顶到 3）。
        实现为：维护 status.scj_recorded_alive = set()，每次对比当前存活集合增量。
        """
        cid = 33
        if cid not in self.roles:
            return
        if (not self.roles[cid].alive) or self.roles[cid].status.perma_disabled:
            return

        st = self.roles[cid].status
        alive_now = set(self.alive_ids())
        if st.scj_recorded_alive is None:
            st.scj_recorded_alive = set()

        newly = alive_now - st.scj_recorded_alive
        if newly:
            st.scj_recorded_alive |= newly
            before = st.scj_layers
            st.scj_layers = min(3, st.scj_layers + len(newly))
            if st.scj_layers != before:
                self._log(f"  · 【沈澄婕】记录到新存活者 {len(newly)} 名，层数 {before}→{st.scj_layers}")

    # ---------- 双生 ----------
    # ---------- 双生 ----------
    def twin_partner(self, cid: int) -> Optional[int]:
        a, b = self.twin_pair
        if b == -1:
            return None
        if cid == a:
            return b
        if cid == b:
            return a
        return None
    def twin_share_nonkill(self, cid: int, kind: str):
        partner = self.twin_partner(cid)
        if partner is None or partner not in self.roles:
            return
        if not self.roles[partner].alive:
            return
        if self.rng.random() > 0.75:
            self._log(f"  · 双生传导失败：{self.N(cid)} 未影响 {self.N(partner)}")
            return
        self._log(f"  · 双生传导成功：{self.N(cid)} → {self.N(partner)}（{kind}）")
        if kind == "gain_shield":
            self.give_shield(partner, 1, ttl=1, perm=False, note="双生复制护盾")
        elif kind in ("swap", "move"):
            d = self.rng.choice([-1, +1])
            self.move_by(partner, d, source=None, note="双生±1位移")
        elif kind == "seal":
            self.roles[partner].status.sealed = max(self.roles[partner].status.sealed, 1)
        elif kind == "forget":
            self.roles[partner].status.forgotten = max(self.roles[partner].status.forgotten, 1)
    def on_twin_death(self, dead: int):
        partner = self.twin_partner(dead)
        if partner is None or partner not in self.roles:
            return
        if self.roles[partner].alive:
            self._log(f"  · 双生死亡反馈：{self.N(partner)} 获得护盾1层")
            self.give_shield(partner, 1, ttl=1, perm=False, note="双生死亡反馈")
    # ---------- 排名操作 ----------
    def swap(self, a: int, b: int, source: Optional[int] = None, note: str = ""):
        if not (self.roles[a].alive and self.roles[b].alive):
            return
        if self._juexi_blocks(source, a, "交换"):
            return
        if self._juexi_blocks(source, b, "交换"):
            return
        if not self.apply_selection(source, a, "交换"):
            return
        if not self.apply_selection(source, b, "交换"):
            return
        pa, pb = self.pos(a), self.pos(b)
        if pa is None or pb is None:
            return
        self.rank[pa], self.rank[pb] = self.rank[pb], self.rank[pa]
        self._log(f"  · 交换：{self.N(a)} ⇄ {self.N(b)}" + (f"（{note}）" if note else ""))
        self._check_shenwei_loss()
    def move_by(self, cid: int, delta: int, source: Optional[int] = None, note: str = ""):
        if not self.roles[cid].alive:
            return
        if self._juexi_blocks(source, cid, "位移"):
            return
        # 防线：抵消首次下降类位移
        st = self.roles[cid].status
        if source == 29 and cid != 29:
            self.roles[29].mem["did_displace"] = True
        if delta > 0 and getattr(st, "defense_line_ttl", 0) > 0 and (not getattr(st, "defense_line_block", False)):
            st.defense_line_block = True
            self._log(f"  · 防线：{self.N(cid)} 抵消一次下降位移")
            return
        if not self.apply_selection(source, cid, "位移"):
            return
        p = self.pos(cid)
        if p is None:
            return
        st = self.roles[cid].status
        if st.doubled_move_next:
            delta *= 2
            st.doubled_move_next = False
            self._log(f"  · 厄运翻倍生效：{self.N(cid)} 本次位移数值翻倍")
        newp = max(0, min(len(self.rank) - 1, p + delta))
        if newp == p:
            return
        self.rank.pop(p)
        self.rank.insert(newp, cid)
        self._log(f"  · 位移：{self.N(cid)} {p+1}→{newp+1}" + (f"（{note}）" if note else ""))
        self._check_shenwei_loss()
    def move_to_first(self, cid: int, source: Optional[int] = None, note: str = ""):
        """Move character to rank #1 (top) if alive and present in rank list."""
        if (cid not in self.rank) or (not self.roles[cid].alive):
            return
        cur = self.rank.index(cid)
        if cur == 0:
            return
        self.rank.pop(cur)
        self.rank.insert(0, cid)
        if note:
            self._log(f"  · 位移：{self.N(cid)} → 第1名（{note}）")
        else:
            self._log(f"  · 位移：{self.N(cid)} → 第1名")

    def insert_rank(self, cid: int, new_rank: int, source: Optional[int] = None, note: str = ""):
        if not self.roles[cid].alive:
            return
        if self._juexi_blocks(source, cid, "插入"):
            return
        if not self.apply_selection(source, cid, "插入"):
            return
        p = self.pos(cid)
        if p is None:
            return
        new_rank = max(1, min(len(self.rank), new_rank))
        self.rank.pop(p)
        self.rank.insert(new_rank - 1, cid)
        self._log(f"  · 插入：{self.N(cid)} → 第{new_rank}名" + (f"（{note}）" if note else ""))
    # ---------- mls 被动 ----------
        self._check_shenwei_loss()
    def mls_try_immune(self, cid: int, effect_desc: str) -> bool:
        if cid != 10:
            return False
        r = self.roles[10]
        st = r.status
        if st.perma_disabled:
            return False
        if st.mls_immune_used >= 3:
            return False
        if st.mls_immune_used_this_turn:
            return False
        st.mls_immune_used_this_turn = True
        st.mls_immune_used += 1
        self._log(f"  · mls(10) 绝对领域：免疫一次技能影响（{effect_desc}）并排名+1（已用{st.mls_immune_used}/3）")
        self.move_by(10, -1, source=None, note="绝对领域+1")
        return True
    def is_mls_unselectable_by_active_kill(self, target: int) -> bool:
        return target == 10
    # ---------- 击杀/死亡 ----------
    def kill(self, victim: int, killer: Optional[int], reason: str,
             bypass_shield: bool = False,
             bypass_revive: bool = False):
        if victim not in self.roles or not self.roles[victim].alive:
            return False
        # Joke mode: 找自称(25) is invincible (immune to everything, including world rules)
        if self.joke_mode and victim == 25:
            self._log("  · 找自称(25) 无敌：免疫本次淘汰")
            return False
        # 沈澄婕(33)：特异性免疫期间无敌（包含世界规则伤害），但不免疫终局末位淘汰
        if victim == 33 and self.roles[33].status.spec_immune_ttl > 0 and ("终局末位淘汰" not in reason):
            self._log(f"  · 特异性免疫：{self.N(33)} 免疫死亡（{reason}）")
            return False
        if self._juexi_blocks(killer, victim, reason):
            return False

        if not self.apply_selection(killer, victim, reason):
            return False

        # 书法家(9)【死而复生·遗策】：当自己被淘汰时立刻复活，
        # 获得永久【遗策】(perma_disabled=True)，并插至第一名；每局仅触发一次。
        if victim == 9 and (not bypass_revive):
            r9 = self.roles[9]
            if (not r9.status.perma_disabled) and (not r9.mem.get("shufa_revive_used", False)):
                r9.mem["shufa_revive_used"] = True
                # 立刻“复活”：本次淘汰无效化
                r9.alive = True
                r9.status.perma_disabled = True  # 永久遗策
                # 清理容易导致连锁的问题状态（保守：清雷霆与濒亡）
                r9.status.thunder = 0
                if hasattr(r9.status, "dying_ttl"):
                    r9.status.dying_ttl = 0
                # 插到第一名
                self._log("  · 书法家(9) 死而复生：复活并获得永久【遗策】，直插第1名（本局一次）")
                self.insert_rank(9, 1, source=None, note="书法家复活直插第一")
                return False


        # 俞守衡(42) 鱼珠回魂：每局一次，被淘汰时改为进入濒亡3回合（濒亡期间不能行动）；不免疫世界规则
        if victim == 42 and killer is not None and (not bypass_revive) and (not self.roles[42].status.perma_disabled):
            if not self.roles[42].mem.get("fish_soul_used", False):
                self.roles[42].mem["fish_soul_used"] = True
                before42 = self.roles[42].status.brief()
                self.roles[42].status.dying_ttl = 3
                self._log("  · 鱼珠回魂：俞守衡(42) 进入【濒亡】3回合（本局一次）")
                self._on_status_change(42, before42)
                return False

        # 护盾
        if not bypass_shield and self.roles[victim].status.total_shields() > 0:
            self.consume_shield_once(victim)
            self._log(f"  · 护盾抵死：{self.N(victim)}（{reason}）")
            if "雷霆" in str(reason) and self.roles[victim].status.thunder >= 3:
                self.roles[victim].status.thunder = 0
                self._log(f"  · 雷霆清除：{self.N(victim)} 因护盾抵消雷霆致死，雷霆归零")
            # 变更：删除郑孑健“坚毅之魂”——这里不再触发任何护盾消耗斩杀
            return False
        # 左右脑复活
        if (not bypass_revive) and victim == 24 and (not self.roles[24].status.perma_disabled):
            st = self.roles[24].status
            if st.revives_left > 0:
                st.revives_left -= 1
                self._log(f"  · 左右脑(24) 双重生命：立即复活（剩余{st.revives_left}）")
                if self.roles[victim].status.thunder >= 3:
                    self.roles[victim].status.thunder = 0
                    self._log(f"  · 雷霆清除：{self.N(victim)} 复活后雷霆归零")
                return False
        # 严雅(29) 复活直升第一机制已移除


        # 真死亡
        self.roles[victim].alive = False
        self.roles[victim].status.thunder = 0
        self.roles[victim].mem["dead_turn"] = self.turn
        self.deaths_this_turn.append(DeathRecord(victim, killer, reason))
        # 30 陈心如：回声追索（本回合发生淘汰则标记一名高于自己的角色迂回2回合）
        if self.roles.get(30) and self.roles[30].alive and (not self.roles[30].status.perma_disabled):
            if int(self.roles[30].mem.get("detour_turn", -1)) != self.turn:
                self.roles[30].mem["detour_turn"] = self.turn
                r30 = self.rank_no(30)
                if r30 is not None:
                    cand = []
                    for x in self.alive_ids():
                        if x == 30:
                            continue
                        rx = self.rank_no(x)
                        if rx is not None and rx < r30:
                            cand.append(x)
                    if cand:
                        t = self.rng.choice(cand)
                        self.roles[t].status.detour_ttl = max(getattr(self.roles[t].status, "detour_ttl", 0), 2)
                        self._log(f"  · 回声追索：{self.N(30)} 使 {self.N(t)} 获得【迂回】(2回合)")

        # 37 真相解码：若存在目击时自己被淘汰，则连带凶手一起被淘汰
        if victim == 37:
            st37 = self.roles[37].status
            if getattr(st37, "witness", False) and killer is not None and self.roles.get(killer) and self.roles[killer].alive:
                self._log(f"  · 真相解码：{self.N(37)} 持有目击被淘汰 → 连带淘汰凶手 {self.N(killer)}")
                self.kill(killer, 37, "真相解码连坐", bypass_shield=True)

        # 37 破绽洞察：监听低于自己排名的来源淘汰
        if killer is not None and victim != killer and self.roles.get(37) and self.roles[37].alive and (not self.roles[37].status.perma_disabled):
            sr = self.rank_no(37)
            vr = self.rank_no(victim)
            if sr is not None and vr is not None and vr > sr:
                st37 = self.roles[37].status
                if not getattr(st37, "witness", False):
                    if int(self.roles[37].mem.get("witness_block_turn", -1)) != self.turn:
                        st37.witness = True
                        self._log(f"  · 破绽洞察：{self.N(37)} 获得【目击】")
                else:
                    st37.witness = False
                    self.roles[37].mem["witness_block_turn"] = self.turn
                    kr = self.rank_no(killer)
                    self._log(f"  · 破绽洞察：{self.N(37)} 目击触发 → 反制淘汰凶手 {self.N(killer)}")
                    killed = self.kill(killer, 37, "破绽洞察反制", bypass_shield=True)
                    if killed and kr is not None and sr is not None:
                        diff = abs(sr - kr)
                        if diff > 0:
                            self._log(f"  · 破绽洞察：上升差值 {diff} 名")
                            self.move_by(37, -diff, source=37, note="破绽洞察位移")

        # 43 救赎祷言：相邻二人被淘汰后复活（场上剩余>=4）
        if killer is not None and self.roles.get(43) and self.roles[43].alive and (not self.roles[43].status.perma_disabled):
            alive_cnt = len(self.alive_ids())
            if alive_cnt >= 4:
                p43 = self.pos(43)
                if p43 is not None:
                    revived = []
                    for dp in (-1, 1):
                        q = p43 + dp
                        if 0 <= q < len(self.rank):
                            neigh = self.rank[q]
                            if neigh == victim and (not self.roles[neigh].alive):
                                self.roles[neigh].alive = True
                                self.roles[neigh].status.dying_ttl = 0
                                revived.append(neigh)
                    if revived:
                        self.roles[43].status.defense_ttl = max(getattr(self.roles[43].status, "defense_ttl", 0), 3)
                        for x in revived:
                            self.roles[x].status.defense_ttl = max(getattr(self.roles[x].status, "defense_ttl", 0), 3)
                        self._log(f"  · 救赎祷言：{self.N(43)} 复活相邻被淘汰者 " + "、".join(self.N(x) for x in revived) + " 并授予【辩护】(3回合)")

        self.elimination_order.append(victim)
        self.elimination_turn[victim] = self.turn

        # 随机事件NPC被淘汰：给予淘汰者特殊状态
        if victim == getattr(self, "HW_CID", 1001):
            if killer is not None and killer in self.roles and self.roles[killer].alive:
                before_k = self.roles[killer].status.brief()
                self.roles[killer].status.hongwei_gift_shield = 1
                self._log(f"  · 洪伟陨落：{self.N(killer)} 获得【洪伟之赐】（抵挡一次伤害；每回合上升2名）")
                self._on_status_change(killer, before_k)
        if victim == getattr(self, "LDL_CID", 1002):
            if killer is not None and killer in self.roles and self.roles[killer].alive:
                before_k = self.roles[killer].status.brief()
                self.roles[killer].status.thunder_wrist_shield = 1
                self._log(f"  · 李东雷陨落：{self.N(killer)} 获得【雷霆手腕】（抵挡一次伤害；每回合给上一名+1雷霆）")
                self._on_status_change(killer, before_k)
        self.check_qiyinlu_lone_wolf()

        # 李知雨(31) 改动：若被【世界规则处决】淘汰，则随机给一名存活者施加【附生】（每局一次）。
        if victim == 31 and killer is None and (not bypass_revive) and (reason == "世界规则处决"):
            if not self.roles[31].mem.get("candle_used", False):
                self.roles[31].mem["candle_used"] = True
                candidates = [c for c in self.alive_ids()
                              if c != 31 and c not in (getattr(self, "HW_CID", 1001), getattr(self, "LDL_CID", 1002))]
                if candidates:
                    t = self.rng.choice(candidates)
                    before_t = self.roles[t].status.brief()
                    self.roles[t].status.attached_life = True
                    self.roles[t].mem["attached_life_of"] = 31
                    self._log(f"  · 残灯复明：世界规则淘汰李知雨(31) → 随机使 {self.N(t)} 获得【附生】")
                    self._on_status_change(t, before_t)
                else:
                    self._log("  · 残灯复明：但无人可获得【附生】")
        # 李知雨(31) 残灯复明：被淘汰时给淘汰者附生；附生者再死则31复活顶替（每局一次）
        if victim == 31:
            if not self.roles[31].mem.get("candle_used", False):
                self.roles[31].mem["candle_used"] = True
                if killer is not None and killer in self.roles and self.roles[killer].alive:
                    uses = int(self.roles[31].mem.get("attached_uses", 0)) if 31 in self.roles else 0
                    if uses >= 2:
                        self._log("  · 残灯复明：本局附生已触发2次 → 不再给予【附生】")
                    else:
                        before_k = self.roles[killer].status.brief()
                        self.roles[killer].status.attached_life = True
                        self.roles[killer].mem["attached_life_of"] = 31
                        if 31 in self.roles:
                            self.roles[31].mem["attached_uses"] = uses + 1
                        self._log(f"  · 残灯复明：{self.N(killer)} 获得【附生】")
                        self._on_status_change(killer, before_k)

        # 附生触发：附生者被淘汰 → 李知雨(31) 立刻复活并顶替其位置
        if self.roles[victim].status.attached_life and self.roles[victim].mem.get("attached_life_of") == 31:
            if 31 in self.roles and (not self.roles[31].alive):
                pos = self.pos(victim)
                self.roles[31].alive = True
                self.roles[31].status.thunder = 0
                # 清除鱼/封印/遗忘等负面可按需保留，这里仅清雷霆
                if pos is None:
                    self.rank.append(31)
                else:
                    self.rank = [cid for cid in self.rank if cid != 31]
                    self.rank.insert(pos, 31)
                self._compact()
                self._log(f"  · 残灯复明：附生者 {self.N(victim)} 被淘汰 → 李知雨(31) 复活并顶替其位置")
        # 找自称：祝福叠加/兑换护盾
        if victim != 25 and (25 in self.roles) and self.roles[25].alive and (not self.roles[25].status.perma_disabled):
            st25 = self.roles[25].status
            st25.mem_bless = st25.__dict__.get("mem_bless", 0)  # 兼容：不新增字段也能用
            st25.mem_bless += 1
            st25.__dict__["mem_bless"] = st25.mem_bless
            self._log(f"  · 找自称(25) 获得祝福+1（现为{st25.mem_bless}层）")
            if st25.mem_bless >= 8:
                self._log("  · 找自称(25) 祝福叠满8层：兑换1层护盾，并清空祝福")
                self.give_shield(25, 1, ttl=1, perm=False, note="祝福兑换护盾")
                st25.__dict__["mem_bless"] = 0

        # Sunny死亡：仅第一次被淘汰时，击败者获得腐化；第二次被淘汰不再赋予腐化
        if victim == 26:
            dt = self.roles[26].mem.get("death_times", 0) + 1
            self.roles[26].mem["death_times"] = dt
            if dt == 1 and killer is not None and killer in self.roles and self.roles[killer].alive:
                if not self.roles[killer].status.corrupted:
                    self.roles[killer].status.corrupted = True
                    self._log(f"  · 【天命使然】{self.N(killer)} 获得腐化")
        return True
    # =========================
    # 新开局 / 回合推进
    # =========================
    def new_game(self):
        # 清理随机事件NPC（避免上一局残留）
        for _npc in (getattr(self, 'HW_CID', 1001), getattr(self, 'LDL_CID', 1002)):
            if _npc in getattr(self, 'roles', {}):
                try:
                    del self.roles[_npc]
                except Exception:
                    pass
        try:
            self.rank = [cid for cid in getattr(self, 'rank', []) if cid not in (getattr(self, 'HW_CID', 1001), getattr(self, 'LDL_CID', 1002))]
        except Exception:
            pass
        try:
            self.skill_order = [cid for cid in getattr(self, 'skill_order', []) if cid not in (getattr(self, 'HW_CID', 1001), getattr(self, 'LDL_CID', 1002))]
        except Exception:
            pass
        self.turn = 0
        self.world_event_triggered_this_turn = False  # 本回合是否触发世界事件
        # RNG reset policy:
        # - If base_seed is None: reseed from system entropy so each new game is independent/random.
        # - If base_seed is set: keep deterministic across new_game for reproducible testing.
        if self.base_seed is None:
            self.rng = random.Random()
        else:
            self.rng = random.Random(self.base_seed)
        self.game_over = False
        self.no_death_streak = 0
        self.pending_endgame_execute = False
        self.log = []
        self.replay_frames = []
        self.deaths_this_turn = []
        self.elimination_order = []
        for r in self.roles.values():
            r.alive = True
            r.status = Status()
            r.mem = {}
        # 初始排名随机
        self.rank = list(self.roles.keys())
        self.rng.shuffle(self.rank)
        # 每局随机生成一次“技能发动顺序”，之后每回合按此顺序循环（仅对存活且有主动技能者生效）
        self.skill_order = self.rank[:]  # 以初始排名的随机结果作为基础，再打乱一次更独立
        self.rng.shuffle(self.skill_order)
        # 双生：藕禄(13) 随机绑定（发动时绑定一次）
        self.twin_pair = (13, -1)
        self._log("【新开局】已生成初始排名")
    def spread_corruption_and_check(self):
        alive = self.alive_ids()
        if not alive:
            return
        sources = [cid for cid in alive if self.roles[cid].status.corrupted]
        if sources:
            to_infect = set()
            for cid in sources:
                p = self.pos(cid)
                if p is None:
                    continue
                if p - 1 >= 0:
                    to_infect.add(self.rank[p - 1])
                if p + 1 < len(self.rank):
                    to_infect.add(self.rank[p + 1])
            newly = [x for x in to_infect if self.roles[x].alive and (not self.roles[x].status.corrupted)]
            for x in newly:
                before_x = self.roles[x].status.brief()
                self.roles[x].status.corrupted = True
                self._oulu_bump_on_status_change(x, before_x)
            if newly:
                self._log("【腐化】扩散：" + "、".join(self.N(x) for x in newly))
        alive = self.alive_ids()
        if alive and all(self.roles[cid].status.corrupted for cid in alive):
            self._log("【腐化】全场腐化达成：清除所有腐化效果")
            for cid in self.roles:
                before_c = self.roles[cid].status.brief()
                self.roles[cid].status.corrupted = False
                self._oulu_bump_on_status_change(cid, before_c)
            st26 = self.roles[26].status
            if not st26.sunny_revive_used:
                st26.sunny_revive_used = True
                if not self.roles[26].alive:
                    self.roles[26].alive = True
                    if st26.thunder >= 3:
                        st26.thunder = 0
                        self._log("  · 雷霆清除：Sunny 复活后雷霆归零")
                    self._compact()
                    pos = 1
                    self.rank.insert(0, 26)
                    self._compact()
                    self._log("【无中生有】Sunnydayorange(26) 复活于第1名")
                else:
                    self._log("【无中生有】本应复活，但 Sunny 已存活 → 仅记录触发（每局一次）")
    def next_turn(self):
        if self.game_over:
            self._log("【提示】本局已结束，请点击【新开局】重新开始。")
            return
        self.turn += 1
        self._active_logged.clear()
        self.world_event_triggered_this_turn = False
        # reset per-turn markers
        for _cid, _r in self.roles.items():
            _r.status.spec_immune_gained_this_turn = False
        if self.roles.get(29):
            self.roles[29].mem["did_kill"] = False
            self.roles[29].mem["did_displace"] = False
        
        # store start-of-turn ranks
        for _cid in self.alive_ids():
            self.roles[_cid].mem["start_rank"] = self.rank_no(_cid)
        # store start-of-turn status signature for 严雅(29) excluding 静默
        if self.roles.get(28) and self.roles[28].alive:
            self.roles[29].mem["start_status_no_silent"] = self._status_sig_no_silent(28)
        self.replay_frames = []
        self._log("")
        self._log(f"========== 【第{self.turn}回合开始】 ==========")
        self.start_rank_snapshot = {cid: self.rank_no(cid) for cid in self.alive_ids()}


        # 0. 施禹谦(36) 神威：为第一名时，每回合处决末位；否则立刻消失
        if 36 in self.roles and self.roles[36].alive and (not self.roles[36].status.perma_disabled):
            st36 = self.roles[36].status
            if st36.shenwei:
                if self.rank_no(36) != 1:
                    self._check_shenwei_loss()
                else:
                    alive_now2 = self.alive_ids()
                    if len(alive_now2) >= 2:
                        target = alive_now2[-1]
                        if target != 36:
                            self._log(f"【神威】处决末位：{self.N(target)}（可被护盾抵消）")
                            self.kill(target, 36, "神威处决", bypass_shield=False, bypass_revive=False)
                            self.step_death_triggers()
                            self._compact()
        # 回合开始：末位斩杀待执行
        alive_now = self.alive_ids()
        if self.pending_endgame_execute and alive_now and len(alive_now) <= 3:
            target = alive_now[-1]
            self._log(f"【末位斩杀】执行：斩杀末位 {self.N(target)}（可被护盾抵消）")
            self.kill(target, None, "末位斩杀", bypass_shield=False, bypass_revive=False)
            self.step_death_triggers()
            self._compact()
            self.pending_endgame_execute = False
        # 回合开始清理
        for cid in self.alive_ids():
            self.roles[cid].status.mls_immune_used_this_turn = False
        # hewenx怨念爆发：下回合行动前结算
        self.apply_hewenx_curse_preaction()
        self.deaths_this_turn = []
        # 1 世界规则（第1回合不触发）
        if self.turn == 1:
            self._log("【世界规则】第1回合不触发")
        else:
            self.step_world_rule()
        # 1.5 随机事件（世界规则后、角色技能前）
        self._random_event_trigger()
        # 1.6 随机事件NPC自动施法（世界规则后）
        self.step_event_npc_actions()
        # 2 主动技能
        self.step_active_skills()
        # 3 死亡触发
        self.step_death_triggers()
        # 4 更新与被动
        self.step_update_and_cleanup()
        # 连续无人死亡计数（仅终局≤3）
        alive_after = self.alive_ids()
        if len(alive_after) <= 3:
            if len(self.deaths_this_turn) == 0:
                self.no_death_streak += 1
            else:
                self.no_death_streak = 0
        else:
            self.no_death_streak = 0
        self._log(f"========== 【第{self.turn}回合结束】 存活{len(self.alive_ids())}人；连续无人死亡={self.no_death_streak} ==========")
        alive = self.alive_ids()
        if not alive:
            self.game_over = True
            return
        if len(alive) > 3:
            self.pending_endgame_execute = False
        else:
            if (not self.pending_endgame_execute) and self.no_death_streak >= 3:
                self.pending_endgame_execute = True
                self._log("【末位斩杀】存活≤3且连续3回合无人淘汰：下一回合将斩杀末位（可被护盾抵消）")
        # 胜利判定
        alive = self.alive_ids()
        if len(alive) == 1:
            winner = alive[0]
            second = self.elimination_order[-1] if len(self.elimination_order) >= 1 else None
            third = self.elimination_order[-2] if len(self.elimination_order) >= 2 else None
            self._log(f"🏆【胜利】{self.N(winner)} 活到最后，获得胜利！")
            if second is not None:
                self._log(f"🥈【第二名】{self.N(second)}")
            if third is not None:
                self._log(f"🥉【第三名】{self.N(third)}")
            self.game_over = True
    # =========================
    # 步骤1：世界规则
    # =========================
    def step_world_rule(self):
        alive = self.alive_ids()
        if len(alive) < 4:
            self._log("【世界规则】存活人数不足4，不触发")
            return
        # 世界事件开始
        self.world_event_triggered_this_turn = True
        # 沈澄婕(33)：若触发世界事件且有特异性免疫 -> 立刻插入第一
        if self.roles.get(33) and self.roles[33].alive and getattr(self.roles[33].status, 'spec_immune_ttl', 0) > 0:
            self._log(f"【沈澄婕】世界事件触发且有特异性免疫 → 立刻插入第一")
            self.insert_rank(33, 1, note="沈澄婕-世界事件免疫")
        target4 = alive[3]
        self._log(f"【世界规则】处决第4名：{self.N(target4)}")
        if target4 == 20 and (not self.roles[11].alive) and (not self.roles[20].status.perma_disabled):
            st = self.roles[20].status
            if not st.father_world_immune_used:
                st.father_world_immune_used = True
                self._log("  · 豆进天之父：被动免疫一次世界规则处决（每局一次）")
            else:
                self.kill(target4, None, "世界规则处决", bypass_shield=False)
        else:
            self.kill(target4, None, "世界规则处决", bypass_shield=False)
        if (not self.roles[11].alive) and self.roles[20].alive and (not self.roles[20].status.perma_disabled):
            st = self.roles[20].status
            if st.father_world_boost_count < 3:
                st.father_world_boost_count += 1
                self._log("  · 豆进天之父：被动触发（世界规则处决时排名+1，计数+1）")
                self.move_by(20, -1, source=None, note="父子同心(被动)+1")
        self._compact()
        alive = self.alive_ids()
        if not alive:
            return
        thunder_targets: List[int] = []
        for idx in (4, 5, 6):
            if idx < len(alive):
                thunder_targets.append(alive[idx])
        if thunder_targets:
            self._log("【世界规则】雷霆降临：第5/6/7名获得一层雷霆")
            for t in thunder_targets:
                if not self.roles[t].alive:
                    continue
                st = self.roles[t].status
                before_t = self.roles[t].status.brief()
                st.thunder += 1
                self._oulu_bump_on_status_change(t, before_t)
                self._log(f"  · {self.N(t)} 雷霆层数={st.thunder}")
                if st.thunder >= 3:
                    self._log(f"  · 雷霆满3：{self.N(t)} 立刻死亡")
                    self.kill(t, None, "雷霆叠满3层处决", bypass_shield=False, bypass_revive=True)
        self._compact()
    
    # =========================
    # 随机事件
    # =========================
    def _ensure_npc(self, cid: int, name: str):
        """Create NPC role if missing and insert into current rank at a random position."""
        if cid in self.roles:
            self.roles[cid].alive = True
            if cid not in self.rank:
                pos = self.rng.randint(0, len(self.rank))
                self.rank.insert(pos, cid)
            return
        self.roles[cid] = Role(cid, name, alive=True)
        pos = self.rng.randint(0, len(self.rank))
        self.rank.insert(pos, cid)

    def _random_event_trigger(self):
        """
        随机事件触发（世界规则后、角色技能前）：
        - 第1回合不触发
        - 每回合 25% 概率触发
        - 触发后等概率抽取 1 个事件并执行
        - 日志输出金色行：触发随机事件：【事件名】！（简短描述）
        """
        if self.turn <= 1:
            return
        if self.rng.random() >= 0.25:
            return

        events = [
            ("洪伟降临", self._ev_spawn_hw),
            ("李东雷降临", self._ev_spawn_ldl),
            ("冰封下的阳光", self._ev_ice_sun),
            ("倒反天罡", self._ev_reverse_rank),
            ("氧化还原反应", self._ev_redox),
            ("骰子", self._ev_shuffle_rank),
        ]
        name, fn = self.rng.choice(events)
        desc = fn() or ""
        if desc:
            self._log(f"触发随机事件：【{name}】！{desc}")
        else:
            self._log(f"触发随机事件：【{name}】！")
        self._compact()

    def _ev_spawn_hw(self) -> str:
        cid = getattr(self, "HW_CID", 1001)
        self._ensure_npc(cid, "洪伟")
        self.roles[cid].mem["npc_casts"] = 0
        return "洪伟加入游戏，并将在接下来3回合（世界规则后）施放技能。"

    def _ev_spawn_ldl(self) -> str:
        cid = getattr(self, "LDL_CID", 1002)
        self._ensure_npc(cid, "李东雷")
        self.roles[cid].mem["npc_casts"] = 0
        return "李东雷加入游戏，并将在接下来3回合（世界规则后）施放技能。"

    def _ev_ice_sun(self) -> str:
        # 随机复活三名已阵亡角色（排除容易出bug的特例）
        dead = []
        for cid, r in self.roles.items():
            if r.alive:
                continue
            if cid in (getattr(self, "HW_CID", 1001), getattr(self, "LDL_CID", 1002)):
                continue
            # Sunnydayorange 腐化时不复活
            if cid == 26 and getattr(r.status, "corrupted", False):
                continue
            # 李知雨：避免“附生/残灯”等链式状态导致错位（保守：已触发残灯不复活）
            if cid == 31 and r.mem.get("candle_used", False):
                continue
            dead.append(cid)

        if not dead:
            return "但无人可被复活。"

        k = min(3, len(dead))
        picks = self.rng.sample(dead, k=k)
        for cid in picks:
            # 从淘汰序列移除，避免结算名次异常
            try:
                self.elimination_order = [x for x in self.elimination_order if x != cid]
            except Exception:
                pass
            self.roles[cid].alive = True
            st = self.roles[cid].status
            # 复活时清理部分容易连锁的即时状态（保守）
            st.thunder = 0
            if hasattr(st, "dying_ttl"):
                st.dying_ttl = 0
            # 插入到随机位置
            if cid not in self.rank:
                pos = self.rng.randint(0, len(self.rank))
                self.rank.insert(pos, cid)

        return "复活了 " + "、".join(self.N(c) for c in picks) + "。"

    def _ev_reverse_rank(self) -> str:
        self.rank = list(reversed(self.rank))
        return "所有人排名完全颠倒。"

    def _ev_redox(self) -> str:
        alive = [cid for cid in self.alive_ids()
                 if cid not in (getattr(self, "HW_CID", 1001), getattr(self, "LDL_CID", 1002))]
        if not alive:
            return "但场上无人受到影响。"

        pool = alive[:]
        self.rng.shuffle(pool)
        oxid = pool[:2] if len(pool) >= 2 else pool[:]
        rest = [c for c in pool if c not in oxid]
        reduc = rest[:2] if len(rest) >= 2 else (rest[:] if rest else oxid[:2])

        for cid in oxid:
            before = self.roles[cid].status.brief()
            self.roles[cid].status.oxid_ttl = max(getattr(self.roles[cid].status, "oxid_ttl", 0), 3)
            self._on_status_change(cid, before)
        for cid in reduc:
            before = self.roles[cid].status.brief()
            self.roles[cid].status.reduce_ttl = max(getattr(self.roles[cid].status, "reduce_ttl", 0), 3)
            self._on_status_change(cid, before)

        return f"{'、'.join(self.N(c) for c in oxid)} 获得【氧化】3回合；{'、'.join(self.N(c) for c in reduc)} 获得【还原】3回合。"

    def _ev_shuffle_rank(self) -> str:
        self.rng.shuffle(self.rank)
        return "所有人排名被打乱。"

    def step_event_npc_actions(self):
        """
        洪伟/李东雷：存在时，每回合在世界规则后施放一次技能（共3次），然后离场。
        - 洪伟：随机插入到任意位置，并为相邻2人添加1层【永久护盾】
        - 李东雷：随机插入到任意位置，并为相邻2人添加1层【雷霆】
        """
        # 洪伟
        hw = getattr(self, "HW_CID", 1001)
        if hw in self.roles and self.roles[hw].alive:
            self._npc_cast_hw(hw)

        # 李东雷
        ldl = getattr(self, "LDL_CID", 1002)
        if ldl in self.roles and self.roles[ldl].alive:
            self._npc_cast_ldl(ldl)

        self._compact()

    def _npc_random_reinsert(self, cid: int):
        if cid in self.rank:
            try:
                self.rank.remove(cid)
            except ValueError:
                pass
        pos = self.rng.randint(0, len(self.rank))
        self.rank.insert(pos, cid)

    def _npc_adjacent_two(self, cid: int):
        if cid not in self.rank:
            return []
        i = self.rank.index(cid)
        res = []
        if i - 1 >= 0:
            res.append(self.rank[i - 1])
        if i + 1 < len(self.rank):
            res.append(self.rank[i + 1])
        return res

    def _npc_cast_hw(self, cid: int):
        casts = int(self.roles[cid].mem.get("npc_casts", 0))
        if casts >= 3:
            self.roles[cid].alive = False
            self.rank = [x for x in self.rank if x != cid]
            self._log("  · 洪伟离场")
            return

        self._npc_random_reinsert(cid)
        neigh = self._npc_adjacent_two(cid)
        for t in neigh:
            if t in self.roles and self.roles[t].alive:
                # 永久护盾：perm=True, ttl=0
                self.give_shield(t, 1, ttl=0, perm=True, note="洪伟赐福(永久)")
        self.roles[cid].mem["npc_casts"] = casts + 1
        self._log(f"  · 洪伟施法：随机换位，并为相邻2人添加永久护盾（第{casts+1}/3次）")

        if casts + 1 >= 3:
            self.roles[cid].alive = False
            self.rank = [x for x in self.rank if x != cid]
            self._log("  · 洪伟离场")

    def _npc_cast_ldl(self, cid: int):
        casts = int(self.roles[cid].mem.get("npc_casts", 0))
        if casts >= 3:
            self.roles[cid].alive = False
            self.rank = [x for x in self.rank if x != cid]
            self._log("  · 李东雷离场")
            return

        self._npc_random_reinsert(cid)
        neigh = self._npc_adjacent_two(cid)
        for t in neigh:
            if t in self.roles and self.roles[t].alive:
                before_t = self.roles[t].status.brief()
                self.roles[t].status.thunder += 1
                self._oulu_bump_on_status_change(t, before_t)
                if self.roles[t].status.thunder >= 3:
                    self._log(f"  · 雷霆满3：{self.N(t)} 立刻死亡")
                    self.kill(t, None, "雷霆叠满3层处决", bypass_shield=False, bypass_revive=True)

        self.roles[cid].mem["npc_casts"] = casts + 1
        self._log(f"  · 李东雷施法：随机换位，并为相邻2人添加1层雷霆（第{casts+1}/3次）")

        if casts + 1 >= 3:
            self.roles[cid].alive = False
            self.rank = [x for x in self.rank if x != cid]
            self._log("  · 李东雷离场")

# =========================
    # 步骤2：主动技能
    # =========================
    def step_active_skills(self):
        # 新规则：每局游戏随机生成一个技能发动顺序，之后每回合按该顺序进行
        if not self.skill_order:
            # 兜底：若未生成则立即生成一次（不输出日志）
            self.skill_order = self.alive_ids()[:]
            self.rng.shuffle(self.skill_order)
        alive_set = {cid for cid in self.alive_ids()}
        # 按固定顺序遍历：只执行存活者；顺序列表中若有人已死亡则跳过
        order = [cid for cid in self.skill_order if cid in alive_set]
        for cid in order:
            if not self.roles[cid].alive:
                continue
            if not self.can_act(cid):
                why = "遗策" if self.roles[cid].status.perma_disabled else ("封印" if self.roles[cid].status.sealed > 0 else "遗忘")
                self._log(f"  · {self.N(cid)} 无法发动（{why}）")
                continue
            if cid not in self._active_logged:
                self._active_logged.add(cid)
                self._log(f"【{self.N(cid)}】发动主动技能…")
            if cid == 33 and self.roles[33].alive and (not self.roles[33].status.perma_disabled):
                st33 = self.roles[33].status
                if st33.spec_immune_ttl > 0 and (not st33.spec_immune_gained_this_turn):
                    self.move_to_first(33, source=None, note="特异性免疫发动时升至第1名")
                else:
                    # 沈澄婕：若发动时没有【特异性免疫】，则上升2名
                    self.move_by(33, -2, source=None, note="无特异性免疫发动上升2名")
            # 施禹谦(36) 天罚灭世：若上回合排名下降，则在本回合发动主动技能前升至第一并获得【神威】
            if cid == 36 and self.roles[36].alive and (not self.roles[36].status.perma_disabled):
                if self.roles[36].mem.get("tfms_pending", False):
                    if self.rank_no(36) != 1:
                        before36 = self.roles[36].status.brief()
                        self.roles[36].status.shenwei = True
                        self._on_status_change(36, before36)
                        self.move_to_first(36, source=None, note="天罚灭世触发：升至第1名并获得神威")
                        self._log("  · 天罚灭世触发：上回合排名下降 → 本回合发动时升至第一并获得【神威】")
                    self.roles[36].mem["tfms_pending"] = False
            self.dispatch_active(cid)
            if self.roles[cid].status.dusk_mark > 0:
                self._log(f"  · 黄昏标记：{self.N(cid)} 因发动主动，排名下降1位")
                self.move_by(cid, +1, source=None, note="黄昏标记惩罚")
    def dispatch_active(self, cid: int):
        fn_map = {
            1: self.act_1,
            3: self.act_3,
            4: self.act_4,
            6: self.act_6,
            7: self.act_7,
            8: self.act_8,
            9: self.act_9,
            10: self.act_10,
            11: self.act_11,
            12: self.act_12,
            13: self.act_13,
            14: self.act_14,
            15: self.act_15,
            16: self.act_16,
            17: self.act_17,
            18: self.act_18,
            19: self.act_19,
            20: self.act_20,
            21: self.act_21,
            23: self.act_23,
            24: self.act_24,
            25: self.act_25,
            26: self.act_26,
            27: self.act_27,
            29: self.act_29,
            34: self.act_34,
            36: self.act_36,
            38: self.act_38,
            39: self.act_39,
            40: self.act_40,
            41: self.act_41,
            33: self.act_33,
                    42: self.act_42,
                    46: self.act_46,
        }
        fn = fn_map.get(cid)
        if fn is None:
            self._log(f"  · 无主动技能")
            return
        try:
            fn()
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            self.skill_exception_count += 1
            if len(self.skill_exception_examples) < 20:
                self.skill_exception_examples.append((cid, f"{type(e).__name__}: {e}", tb))
            if getattr(self, "export_error_log", False):
                try:
                    with open(self._error_log_path(), "a", encoding="utf-8") as f:
                        f.write("\n=== Skill Exception turn=%s cid=%s name=%s ===\n" % (self.turn, cid, self.N(cid)))
                        f.write("%s: %s\n" % (type(e).__name__, e))
                        f.write(tb + "\n")
                except Exception:
                    pass
            if not self.fast_mode:
                self._log(f"  · 【异常】{self.N(cid)} 的主动技能错误：{type(e).__name__}: {e}")
            return
    # =========================
    # 步骤3：死亡触发
    # =========================
    def step_death_triggers(self):
        if not self.deaths_this_turn:
            self._log("【死亡触发】本回合无死亡")
            return
        self._log("【死亡触发】按死亡顺序处理：")
        i = 0
        while i < len(self.deaths_this_turn):
            rec = self.deaths_this_turn[i]
            i += 1
            v = rec.victim
            if v == 7:
                self.on_death_7(rec.killer)
            elif v == 9:
                self.on_death_9()
            elif v == 14:
                self.on_death_14(rec.killer)
            elif v == 23:
                self.on_death_23()
    # =========================
    # 步骤4：更新/清理 + 被动
    # =========================
    def step_update_and_cleanup(self):
        self._compact()
        self.spread_corruption_and_check()
                # 29 严雅：净化爆发（回合结束时判定；净化能量已改为在主动释放时触发）
        if self.roles.get(29) and self.roles[29].alive and (not self.roles[29].status.perma_disabled):
            alive_rank = [c for c in self.rank if self.roles[c].alive]
            for i in range(len(alive_rank) - 2):
                a, b, c = alive_rank[i], alive_rank[i + 1], alive_rank[i + 2]
                if getattr(self.roles[a].status, "purify_ttl", 0) > 0 and getattr(self.roles[b].status, "purify_ttl", 0) > 0 and getattr(self.roles[c].status, "purify_ttl", 0) > 0:
                    # 清除三人的全部状态（保留perma_disabled与fake标记）
                    for x in (a, b, c):
                        stx = self.roles[x].status
                        perm = stx.perma_disabled
                        fake = stx.__dict__.get("fake_99999", False)
                        self.roles[x].status = Status(perma_disabled=perm)
                        self.roles[x].status.__dict__["fake_99999"] = fake
                    # 设置冷却
                    self.roles[29].mem["purify_cd"] = 2
                    self._log(f"  · 净化爆发：{self.N(a)}、{self.N(b)}、{self.N(c)} 相邻且均有净化 → 清除全部状态；{self.N(b)} 直升第一")
                    self.insert_rank(b, 1, source=None, note="净化爆发直升第一")
                    break

        for cid in self.alive_ids():
            st = self.roles[cid].status
            before_brief_u = st.brief()
            # 29 严雅：静默审判（若本回合除静默外状态未改变，则获得静默；若已有静默则消耗并上升2名）
            if cid == 28 and (not st.perma_disabled):
                if getattr(st, "silent_ttl", 0) > 0:
                    self.move_by(28, -2, source=None, note="静默审判上升2名")
                    st.silent_ttl = 0
                else:
                    start_sig = self.roles[29].mem.get("start_status_no_silent", "")
                    now_sig = self._status_sig_no_silent(28)
                    if start_sig == now_sig:
                        st.silent_ttl = 1
                        self._log(f"  · 静默审判：{self.N(28)} 获得【静默】")



            # 45 蒋骐键：锁定防线（本回合下降>=2名触发）
            if cid == 45 and (not st.perma_disabled):
                sr = self.roles[45].mem.get("start_rank", None)
                cr = self.rank_no(45)
                if sr is not None and cr is not None and (cr - sr) >= 2 and getattr(st, "defense_line_ttl", 0) == 0:
                    st.defense_line_ttl = 2
                    st.defense_line_block = False
                    self._log(f"  · 锁定防线：{self.N(45)} 获得【防线】(2回合)")
                    self.roles[29].mem["silent_grant_turn"] = self.turn
            if st.shield_ttl > 0:
                st.shield_ttl -= 1
                if st.shield_ttl == 0:
                    st.shields = 0
            if st.sealed > 0:
                st.sealed -= 1
            if st.forgotten > 0:
                st.forgotten -= 1
            if st.juexi_ttl > 0:
                st.juexi_ttl -= 1

            if st.dying_ttl > 0:
                st.dying_ttl -= 1
            if st.spec_immune_ttl > 0:
                st.spec_immune_ttl -= 1

            # 迂回：回合结算下降1名
            if getattr(st, "detour_ttl", 0) > 0:
                self.move_by(cid, 1, source=None, note="迂回下降1名")
                st.detour_ttl -= 1

            # 防线：回合结算上升1名
            if getattr(st, "frontline_cd", 0) > 0:
                st.frontline_cd -= 1

            if getattr(st, "defense_line_ttl", 0) > 0:
                self.move_by(cid, -1, source=None, note="防线上升1名")
                st.defense_line_ttl -= 1
                if st.defense_line_ttl <= 0:
                    st.defense_line_block = False

            # 迫近战线冷却
            if getattr(st, "frontline_cd", 0) > 0:
                st.frontline_cd -= 1

# 辩护：持续期间每回合上升1名
            if getattr(st, "defense_ttl", 0) > 0:
                self.move_by(cid, -1, source=None, note="辩护上升1名")
                st.defense_ttl -= 1

            # 圣辉：持续期间每回合上升1名
            if getattr(st, "shenghui_ttl", 0) > 0:
                self.move_by(cid, -1, source=None, note="圣辉上升1名")
                st.shenghui_ttl -= 1

            # 感电：叠满3层后，每回合消耗1层并上升3名
            if getattr(st, "dian", 0) >= 3:
                self.move_by(cid, -3, source=None, note="感电爆发上升3名")
                st.dian = max(0, st.dian - 1)

            # 乘胜追击：叠满3层后，每回合上升3名
            if getattr(st, "chase", 0) >= 3:
                self.move_by(cid, -3, source=None, note="乘胜追击上升3名")

            # 氧化/还原：每回合位移并衰减
            if getattr(st, "oxid_ttl", 0) > 0:
                self.move_by(cid, -1, source=None, note="氧化上升1名")
                st.oxid_ttl -= 1
            if getattr(st, "reduce_ttl", 0) > 0:
                self.move_by(cid, +1, source=None, note="还原下降1名")
                st.reduce_ttl -= 1

            # 洪伟之赐：持有期间每回合上升2名（直到抵挡一次伤害被消耗）
            if getattr(st, "hongwei_gift_shield", 0) > 0:
                self.move_by(cid, -2, source=None, note="洪伟之赐上升2名")
            # 雷霆手腕：持有期间每回合给上一名雷霆+1（直到抵挡一次伤害被消耗）
            if getattr(st, "thunder_wrist_shield", 0) > 0:
                myr = self.rank_no(cid)
                if myr is not None and myr > 1:
                    above = self.rank[myr - 2]
                    if above in self.roles and self.roles[above].alive:
                        before_a = self.roles[above].status.brief()
                        self.roles[above].status.thunder += 1
                        self._on_status_change(above, before_a)
                        self._log(f"  · 雷霆手腕：{self.N(cid)} 令 {self.N(above)} 雷霆层数={self.roles[above].status.thunder}")
                        if self.roles[above].status.thunder >= 3:
                            self._log(f"  · 雷霆满3：{self.N(above)} 立刻死亡")
                            self.kill(above, None, "雷霆叠满3层处决", bypass_shield=False, bypass_revive=True)
                            self._compact()

            
            # 32 范一诺：清障圣辉——若本回合名次下降，则获得3回合圣辉；圣辉期间每回合上升1名
            if cid == 32 and (not st.perma_disabled) and self.roles[32].alive:
                start_r = self.start_rank_snapshot.get(32)
                now_r = self.rank_no(32)
                if start_r is not None and now_r is not None and now_r > start_r:
                    st32 = self.roles[32].status
                    st32.shenghui_ttl = 3
                    self._log(f"  · 清障圣辉：{self.N(32)} 本回合排名下降 → 获得【圣辉】(3回合)")

            # 施沁皓(3) 斩杀冷却递减
            if cid == 3:
                cd3 = int(self.roles[3].mem.get("execute_cd", 0))
                if cd3 > 0:
                    self.roles[3].mem["execute_cd"] = cd3 - 1

            # 路济阳(17) 护佑之盾冷却递减
            if cid == 17:
                cd2 = int(self.roles[17].mem.get("shield_cd", 0))
                if cd2 > 0:
                    self.roles[17].mem["shield_cd"] = cd2 - 1
            # 施禹谦(36) 天罚灭世：若本回合排名下降，则标记下回合发动时升至第一并获得【神威】
            if cid == 36 and (not st.perma_disabled) and self.roles[36].alive:
                cur = self.rank_no(36)
                prev = self.roles[36].mem.get("last_rank")
                if prev is not None and cur is not None and cur > int(prev):
                    self.roles[36].mem["tfms_pending"] = True
                self.roles[36].mem["down_streak"] = 0
                now_after = self.rank_no(36)
                if now_after is not None:
                    self.roles[36].mem["last_rank"] = int(now_after)
            
            # 28 黄梓睿：净化能量——每回合给自己与相邻两人施加2回合净化；三人净化相邻则触发净化爆发
            if False and cid == 29 and (not st.perma_disabled) and self.roles[29].alive:
                cd = int(self.roles[29].mem.get("purify_cd", 0))
                if cd > 0:
                    self.roles[29].mem["purify_cd"] = cd - 1
                else:
                    self.roles[29].mem["purify_cd"] = 0
                p29 = self.pos(29)
                if cd > 0:
                    # 冷却中，跳过本回合净化施加与判定
                    return
                targets = []
                if p29 is not None:
                    for q in (p29-1, p29, p29+1):
                        if 0 <= q < len(self.rank):
                            t = self.rank[q]
                            if self.roles[t].alive:
                                targets.append(t)
                if targets:
                    for t in targets:
                        before_t = self.roles[t].status.brief()
                        self.roles[t].status.purify_ttl = max(getattr(self.roles[t].status, "purify_ttl", 0), 2)
                        self._on_status_change(t, before_t)
                    self._log("  · 净化能量：" + "、".join(self.N(x) for x in targets) + " 获得【净化】(2回合)")

                # 检查连续三人均有净化
                alive_rank = [c for c in self.rank if self.roles[c].alive]
                for i in range(len(alive_rank)-2):
                    a,b,c = alive_rank[i], alive_rank[i+1], alive_rank[i+2]
                    if getattr(self.roles[a].status, "purify_ttl", 0)>0 and getattr(self.roles[b].status, "purify_ttl", 0)>0 and getattr(self.roles[c].status, "purify_ttl", 0)>0:
                        # 清除三人的所有状态效果（保留永久禁用等硬规则字段）
                        for x in (a,b,c):
                            stx=self.roles[x].status
                            perm = stx.perma_disabled
                            fake = stx.__dict__.get("fake_99999", False)
                            self.roles[x].status = Status(perma_disabled=perm)
                            self.roles[x].status.__dict__["fake_99999"]=fake
                        self.roles[29].mem["purify_cd"] = 2
                        self._log(f"  · 净化爆发：{self.N(a)}、{self.N(b)}、{self.N(c)} 相邻且均有净化 → 清除全部状态；{self.N(b)} 直升第一")
                        self.insert_rank(b, 1, source=None, note="净化爆发直升第一")
                        break

            # 季任杰(34) 越挫越勇：回合末结算（被动）
            if cid == 34 and (not st.perma_disabled) and self.roles[34].alive:
                alive_now = self.alive_ids()
                cur_rank = self.rank_no(34)
                if cur_rank is not None:
                    # 倒数第一且不在前三：立刻升至第一并移除效果
                    if cur_rank == len(alive_now) and cur_rank > 3:
                        if st.vyzy:
                            st.vyzy = False
                        self._log("  · 越挫越勇：倒数第一触发 → 立刻升至第一并移除【越挫越勇】")
                        self.insert_rank(34, 1, source=None, note="越挫越勇触底反弹")
                    else:
                        # 不在前三：获得/保持越挫越勇，并每回合下降2名
                        if cur_rank > 3:
                            if not st.vyzy:
                                before34 = st.brief()
                                st.vyzy = True
                                self._log("  · 越挫越勇：不在前三 → 获得【越挫越勇】")
                                self._oulu_bump_on_status_change(34, before34)
                            self.move_by(34, +2, source=None, note="越挫越勇下降2名")
                        # 进入前三：移除越挫越勇
                        else:
                            if st.vyzy:
                                before34 = st.brief()
                                st.vyzy = False
                                self._log("  · 越挫越勇：进入前三 → 移除【越挫越勇】")
                                self._oulu_bump_on_status_change(34, before34)

            if cid == 46 and st.lone_wolf and (not st.perma_disabled):
                self.move_by(46, -1, source=None, note="孤军奋战")


            self._oulu_bump_on_status_change(cid, before_brief_u)
        # 钟无艳巾帼护盾
        self.endcheck_zhongwuyan()
        # 豆进天被动
        self.check_doujintian_passive()
        # 牵寒被动
        self.check_qianhan_passive()
        self.check_qiyinlu_lone_wolf()
    def check_doujintian_passive(self):
        if not self.roles[11].alive or self.roles[11].status.perma_disabled:
            return
        alive = self.alive_ids()
        r = self.rank_no(11)
        if r is None:
            return
        if r > int(len(alive) * 0.7):
            self._log("  · 豆进天(11) 天命所归触发：升至第一并获得护盾1层(2回合)")
            self.insert_rank(11, 1, source=None, note="天命所归升至第一")
            self.give_shield(11, 1, ttl=2, perm=False, note="天命所归护盾")
    def check_qianhan_passive(self):
        if not self.roles[6].alive or self.roles[6].status.perma_disabled:
            return

    def check_qiyinlu_lone_wolf(self):
        if 46 not in self.roles or (not self.roles[46].alive) or self.roles[46].status.perma_disabled:
            return
        r = self.roles[46]
        if r.status.lone_wolf:
            return
        mates = r.mem.get("mates", [])
        if len(mates) != 2:
            return
        if all((m in self.roles) and (not self.roles[m].alive) for m in mates):
            before = r.status.brief()
            self.give_shield(46, 1, ttl=1, perm=False, note="孤军奋战触发护盾")
            r.status.lone_wolf = True
            self._log("  · 孤军奋战：两名队友均被淘汰 → 获得永久【孤军奋战】（每回合上升1名）")
            self._on_status_change(46, before)
        alive = self.alive_ids()
        r = self.rank_no(6)
        if r is None:
            return
        if r > int(len(alive) * 0.6):
            if not self.roles[6].mem.get("qian_immune_next", False):
                self.roles[6].mem["qian_immune_next"] = True
                self._log("  · 牵寒(6) 逆流而上触发：免疫下次技能影响并排名+1")
                self.move_by(6, -1, source=None, note="逆流而上+1")
                higher = [x for x in self.alive_ids()
                          if self.rank_no(x) is not None and self.rank_no(x) < self.rank_no(6)]
                if higher:
                    t = self.rng.choice(higher)
                    if not self.is_mls_unselectable_by_active_kill(t):
                        self._log(f"  · 寒锋逆雪：斩杀高位随机目标 {self.N(t)}")
                        self.kill(t, 6, "寒锋逆雪条件斩杀")
                    else:
                        self._log("  · 寒锋逆雪：随机到mls(10)不可选 → 失败")
    def endcheck_zhongwuyan(self):
        # 钟无艳(21)
        # 回合结束：只要本回合排名上升（≥1位），就触发判定：
        # - 50%概率获得1层护盾（最多触发3次，且需要当前没有护盾才可抽取）
        # - 若本次未获得护盾，则直接冲到第一名。
        if not self.roles[21].alive or self.roles[21].status.perma_disabled:
            return
        st = self.roles[21].status
        start = self.start_rank_snapshot.get(21)
        now = self.rank_no(21)
        if start is None or now is None:
            return

        rise = start - now
        if rise < 1:
            return

        gained = False
        # 只有在：触发次数未满3次 且 当前没有任何护盾 时，才允许进行“50%抽盾”
        if st.zhong_triggers < 3 and st.total_shields() == 0:
            if self.rng.random() < 0.5:
                st.zhong_triggers += 1
                self.give_shield(21, 1, ttl=1, perm=False, note="巾帼护盾判定")
                gained = True

        # 未获得护盾：直接冲到第一
        if not gained:
            self._log("  · 巾帼未获盾→直冲第一")
            self.insert_rank(21, 1, source=None, note="巾帼未获盾→直冲第一")
    def apply_hewenx_curse_preaction(self):
        for cid in self.alive_ids():
            curse = self.roles[cid].status.hewenx_curse
            if not curse:
                continue
            threshold = curse["threshold_rank"]
            cur = self.rank_no(cid)
            if cur is None:
                self.roles[cid].status.hewenx_curse = None
                continue
            if cur < threshold:
                self._log(f"【怨念爆发】{self.N(cid)} 行动前判定：排名高于阈值 → 直接斩杀（护盾无效）")
                self.kill(cid, 7, "怨念爆发斩杀(护盾无效)", bypass_shield=True, bypass_revive=True)
            self.roles[cid].status.hewenx_curse = None
        self._compact()
    # =========================
    # 主动技能实现
    # =========================
    def act_1(self):
        r = self.roles[1]
        r.mem["counter"] = r.mem.get("counter", 0) + 1
        if r.mem["counter"] % 3 != 0:
            self._log("  · 逆袭之光：计数未到（每3回合必发）")
            return
        alive = self.alive_ids()
        myr = self.rank_no(1)
        if myr is None:
            return
        if myr <= int(len(alive) * 0.4):
            self._log("  · 逆袭之光：不在后60%，条件不满足")
            return
        front = alive[:max(1, len(alive) // 2)]
        target = self.pick_random(1, [x for x in front if x != 1], "逆袭之光交换目标")
        if target is None:
            return
        old_rank = myr
        self.swap(1, target, source=1, note="逆袭之光")
        self._compact()
        if old_rank <= len(self.rank):
            v = self.rank[old_rank - 1]
            if v != 1:
                self._log(f"  · 光影裁决：斩杀原第{old_rank}名位置的 {self.N(v)}")
                self.kill(v, 1, "光影裁决联动斩杀")
    def act_3(self):
        myr = self.rank_no(3)
        if myr is None:
            return
        cd = int(self.roles[3].mem.get("execute_cd", 0))
        if cd > 0:
            self._log(f"  · 凌空决：斩杀冷却中（剩余{cd}回合）")
            return
        higher = [x for x in self.alive_ids()
                  if self.rank_no(x) is not None and self.rank_no(x) < myr]
        if not higher:
            self._log("  · 凌空决：无更高排名目标")
            return
        target = self.pick_random(3, higher, "凌空决目标")
        if target is None:
            return
        if self.is_mls_unselectable_by_active_kill(target):
            self._log("  · 凌空决：目标为mls(10)绝对防御不可选 → 失败，自身下降2位")
            self.move_by(3, +2, source=3, note="凌空决失败惩罚")
            return
        if target == 6 and self.roles[6].mem.get("qian_immune_next"):
            self.roles[6].mem["qian_immune_next"] = False
            self._log("  · 凌空决：牵寒免疫下次技能影响 → 斩杀无效；自身下降2位")
            self.move_by(3, +2, source=3, note="凌空决失败惩罚")
            return
        self._log(f"  · 凌空决：斩杀更高位目标 {self.N(target)}")
        died = self.kill(target, 3, "凌空决主动斩杀")
        if died:
            self.roles[3].mem["execute_cd"] = 2
        if not died:
            self._log("  · 凌空决：斩杀被抵挡（护盾），自身下降2位")
            self.move_by(3, +2, source=3, note="凌空决失败惩罚")
    # 10) 朱昊泽完全重做
    def act_4(self):
        r = self.roles[4]
        # 每两回合发动：第2、4、6…回合可尝试
        if self.turn % 2 != 0:
            self._log("  · 绝息斩：未到发动回合（每两回合）")
            self._log("  · 朱昊泽 获得【绝息】")
            return
        myr = self.rank_no(4)
        if myr is None:
            return
        if myr <= 4:
            self._log("  · 绝息斩：不存在“比自己高4名的人” → 无法发动")
            return
        target_rank = myr - 4
        target = self.rank[target_rank - 1]  # 恰好高4名
        if not self.roles[target].alive:
            self._log("  · 绝息斩：目标已死亡 → 无法发动")
            return
        if self.is_mls_unselectable_by_active_kill(target):
            self._log("  · 绝息斩：目标为mls(10)不可被主动斩杀 → 无法发动")
            return
        # 绝息路径：发动前第(target_rank+1 .. myr-1) 共3人获得1回合绝息
        path = []
        for rk in range(target_rank + 1, myr):
            if rk - 1 < len(self.rank):
                cid = self.rank[rk - 1]
                if cid != 4 and self.roles[cid].alive:
                    path.append(cid)
        # 理论上恰好3人；保险起见截断
        path = path[:3]
        self._log(f"  · 绝息斩：斩杀第{target_rank}名 {self.N(target)} 并替换其位置")
        # 先斩杀目标（护盾可挡；若挡住则不替换、不施加绝息）
        died = self.kill(target, 4, "绝息斩斩杀")
        if not died:
            self._log("  · 绝息斩：斩杀被护盾抵消 → 不替换、不施加绝息")
            return
        # 替换位置：把4插到目标位置
        self._compact()
        # 目标死亡后其位置空缺：我们将 4 插入 target_rank
        self.insert_rank(4, target_rank, source=None, note="绝息斩替换位置")
        # 施加绝息（1回合）
        if path:
            self._log("  · 绝息效果：沿途获得一回合绝息：" + "、".join(self.N(x) for x in path))
            for x in path:
                new_ttl = max(self.roles[x].status.juexi_ttl, 1)
                # 绝息为技能效果，走统一入口（可触发隐身/绝地反击/特异性免疫等）
                self.set_status(x, 'juexi_ttl', new_ttl, 4, note='绝息')
    def act_6(self):
        self._log("  · 无主动技能（被动在回合末判定）")
    # 9) hewenx：不再自集火；集火语义已重做（见 pick_random）
    def act_7(self):
        alive = [x for x in self.alive_ids() if x != 7]
        if not alive:
            self._log("  · 下位集火：无目标")
            return
        target = self.pick_random(7, alive, "下位集火目标")
        if target is None:
            return
        self.set_unique_focus(target, note=f"  · 下位集火：{self.N(target)} 获得【集火】（自我反噬版，顶掉场上其它集火）")
    def act_8(self):
        # 曾靖舒(8)
        # 每回合上升名次（奇数回合+1，偶数回合+2）。
        # 联动斩杀：每3回合最多触发一次（不影响上升）。
        step = 1 if (self.turn % 2 == 1) else 2
        old = self.pos(8)
        self.move_by(8, -step, source=8, note=f"日进千里+{step}")
        if old is None:
            return

        last_kill_turn = self.roles[8].mem.get("zjs_last_kill_turn")
        can_kill = (last_kill_turn is None) or ((self.turn - last_kill_turn) >= 3)

        alive_now = self.alive_ids()
        if old + 1 < len(alive_now):
            target = alive_now[old + 1]
            if self.roles[target].status.total_shields() == 0:
                if can_kill:
                    self._log(f"  · 乘胜追击：斩杀 {self.N(target)}（目标无护盾）")
                    self.kill(target, 8, "乘胜追击联动斩杀")
                    self.roles[8].mem["zjs_last_kill_turn"] = self.turn
                else:
                    self._log("  · 乘胜追击：斩杀冷却中（每3回合最多触发一次）")
            else:
                self._log("  · 乘胜追击：目标有护盾，无法斩杀")

    # 8) 书法家：笔戮千秋后上升两名
    # 8) 书法家：笔戮千秋后上升两名
    def act_9(self):
        r = self.roles[9]
        if not r.mem.get("seal_used", False):
            alive = [x for x in self.alive_ids() if x != 9]
            if len(alive) >= 2:
                a, b = self.rng.sample(alive, 2)
                before_a = self.roles[a].status.brief()
                before_b = self.roles[b].status.brief()
                self.roles[a].status.sealed = max(self.roles[a].status.sealed, 1)
                self.roles[b].status.sealed = max(self.roles[b].status.sealed, 1)
                self._oulu_bump_on_status_change(a, before_a)
                self._oulu_bump_on_status_change(b, before_b)
                r.mem["seal_used"] = True
                self._log(f"  · 笔定乾坤：封印 {self.N(a)}、{self.N(b)} 下一回合主动")
                self.twin_share_nonkill(a, "seal")
                self.twin_share_nonkill(b, "seal")
        cd = r.mem.get("kill_cd", 0)
        if cd > 0:
            r.mem["kill_cd"] = cd - 1
            self._log("  · 笔戮千秋：冷却中")
            return
        myr = self.rank_no(9)
        if myr is None:
            return
        lower = [x for x in self.alive_ids() if self.rank_no(x) is not None and self.rank_no(x) > myr]
        if not lower:
            self._log("  · 笔戮千秋：无低位目标")
            return
        target = self.pick_random(9, lower, "笔戮千秋目标")
        if target is None:
            return
        if self.is_mls_unselectable_by_active_kill(target):
            self._log("  · 笔戮千秋：随机到mls(10)不可选 → 失败")
        else:
            self._log(f"  · 笔戮千秋：斩杀 {self.N(target)}")
            self.kill(target, 9, "笔戮千秋主动斩杀")
        r.mem["kill_cd"] = 1
        # 新增：释放后可上升两名
        self.move_by(9, -2, source=9, note="笔戮千秋后上升2名")
    def act_10(self):
        self._log("  · 无主动技能（绝对领域为被动）")
    def act_11(self):
        self._log("  · 无主动技能（天命所归为被动）")
    def act_12(self):
        # 放烟花：万象挪移
        # 规则更改：
        # - 每次释放时，选中第一名（当前第1名）的概率初始为 1%；
        # - 若未选中第一名，则在其它位置目标中等概率选择；
        # - 每次释放后，“选中第一名”的概率 +1%（上限100%），跨回合累计。
        r = self.roles[12]
        times = max(1, self.turn)
        p_first = float(r.mem.get("wx_first_p", 0.01))
        p_first = max(0.0, min(1.0, p_first))
        self._log(f"  · 万象挪移：本回合连续释放 {times} 次（本回合起始选中第一名概率={p_first*100:.0f}%）")
        for k in range(times):
            alive_all = self.alive_ids()
            pool = [x for x in alive_all if x != 12]
            if not pool:
                self._log("  · 万象挪移：无可交换目标，后续停止")
                break
            first = alive_all[0] if alive_all else None
            # 先按概率尝试选中第一名（若第一名可被选中）
            target = None
            if first is not None and first in pool and self.rng.random() < p_first:
                target = first
            else:
                others = [x for x in pool if x != first] if first in pool else pool[:]
                target = self.rng.choice(others) if others else (first if first in pool else None)
            # 每次释放后，选中第一名概率 +1%
            p_first = min(1.0, p_first + 0.01)
            r.mem["wx_first_p"] = p_first
            if target is None:
                return
            # mls 免疫处理
            if target == 10 and self.mls_try_immune(10, f"放烟花交换（第{k+1}次）"):
                # 免疫触发后：从除mls以外的目标里重新等概率选一个（不再强制第一名）
                pool2 = [x for x in pool if x != 10]
                if not pool2:
                    self._log("  · 万象挪移：仅剩mls且其免疫触发 → 本次无效")
                    continue
                target = self.rng.choice(pool2)
            self._log(f"  · 万象挪移（第{k+1}次）：与 {self.N(target)} 交换（释放后第一名概率已升至{p_first*100:.0f}%）")
            self.swap(12, target, source=12, note=f"万象挪移第{k+1}次交换")
    def act_13(self):
        # 藕禄：完全重做（移除全部双生相关内容）
        # 【影入空濛】每回合若自己没有隐身，则获得隐身；若已有隐身，则移除隐身。
        # 隐身状态：不会被任何技能选中（不包括世界规则）
        before = self.roles[13].status.brief()
        st = self.roles[13].status
        if not st.invisible:
            st.invisible = True
            self._log("  · 影入空濛：获得【隐身】")
        else:
            st.invisible = False
            self._log("  · 影入空濛：移除【隐身】")
        self._oulu_bump_on_status_change(13, before)


    def act_14(self):
        self._log("  · 无主动技能（死亡触发：血债血偿）")
    def act_15(self):
        myr = self.rank_no(15)
        if myr is None or myr == 1:
            self._log("  · 高位清算：无高位目标")
            return
        higher = [x for x in self.alive_ids() if self.rank_no(x) is not None and self.rank_no(x) < myr]
        if not higher:
            self._log("  · 高位清算：无高位目标")
            return
        t1 = self.pick_random(15, higher, "高位清算第1杀目标")
        if t1 is None:
            return
        if self.is_mls_unselectable_by_active_kill(t1):
            self._log("  · 高位清算：随机到mls(10)不可选 → 失败")
            return
        self._log(f"  · 高位清算：斩杀 {self.N(t1)}")
        died = self.kill(t1, 15, "高位清算第1杀")
        if died:
            myr2 = self.rank_no(15)
            if myr2 is None:
                return
            higher2 = []
            for x in self.alive_ids():
                rx = self.rank_no(x)
                if rx is not None and rx < myr2:
                    higher2.append(x)
            if higher2:
                t2 = self.pick_random(15, higher2, "高位清算第2杀目标")
                if t2 is not None and (not self.is_mls_unselectable_by_active_kill(t2)):
                    self._log(f"  · 追加清算：斩杀 {self.N(t2)}")
                    self.kill(t2, 15, "高位清算第2杀")
    # 5) 合议庭：删除“第一名本回合技能无效”
    def act_16(self):
        alive = self.alive_ids()
        myr = self.rank_no(16)
        if myr is None:
            return
        if myr <= int(len(alive) * 0.4):
            self._log("  · 众意审判：不在后60%，条件不满足")
            return
        first = alive[0]
        tail = alive[int(len(alive) * 0.4):]
        target = self.pick_random(16, [x for x in tail if x != first], "众意审判交换目标")
        if target is None:
            return
        self._log(f"  · 众意审判：强制 {self.N(first)} 与 {self.N(target)} 交换")
        self.swap(first, target, source=16, note="众意审判交换")
    # 7) 路济阳：移除“插到第一或最后→自杀”
    def act_17(self):
        r = self.roles[17]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 时空跃迁：冷却中")
            return
        alive = self.alive_ids()
        oldr = self.rank_no(17)
        n = len(alive)
        new_rank = self.rng.randint(1, n)
        self._log(f"  · 时空跃迁：插入第{new_rank}名位置")
        self.insert_rank(17, new_rank, source=17, note="时空跃迁")

        # 护佑之盾：为随机两人生成可持续护盾（冷却5回合，且本局最多触发2次）
        shield_cd = int(r.mem.get("shield_cd", 0))
        if shield_cd > 0:
            self._log(f"  · 护佑之盾：冷却中（剩余{shield_cd}回合）")
        else:
            uses = int(r.mem.get("shield_uses", 0))
            if uses >= 2:
                self._log("  · 护佑之盾：本局已使用2次 → 无法再触发")
            else:
                whitelist = [17, 14, 16, 7, 6, 20, 11, 19]
                cand = [x for x in whitelist if x in self.roles and self.roles[x].alive]
                if len(cand) >= 2:
                    a, b = self.rng.sample(cand, 2)
                    self.give_shield(a, 1, perm=True, note="增益：护佑之盾(可持续)")
                    self.give_shield(b, 1, perm=True, note="增益：护佑之盾(可持续)")
                    r.mem["shield_cd"] = 5
                    r.mem["shield_uses"] = uses + 1

        nowr = self.rank_no(17)
        if oldr is not None and nowr is not None and nowr > oldr:
            higher_before = [x for x in alive if self.rank_no(x) is not None and self.rank_no(x) < oldr and x != 17]
            if higher_before:
                t = self.pick_random(17, higher_before, "时空斩击目标")
                if t is not None:
                    if not self.is_mls_unselectable_by_active_kill(t):
                        self._log(f"  · 时空斩击：跃迁后下降，斩杀跃迁前高位 {self.N(t)}")
                        self.kill(t, 17, "时空斩击联动斩杀")
                    else:
                        self._log("  · 时空斩击：随机到mls(10)不可选 → 失败")
        r.mem["cd"] = 2
    def act_18(self):
        r = self.roles[18]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 秩序颠覆：冷却中")
            return
        alive = self.alive_ids()
        first = alive[0]
        back = alive[len(alive) // 2:]
        target = self.pick_random(18, [x for x in back if x != first], "秩序颠覆交换目标")
        if target is None:
            return
        self._log(f"  · 秩序颠覆：交换 {self.N(first)} 与 {self.N(target)}")
        self.swap(first, target, source=18, note="秩序颠覆")
        myr = self.rank_no(18)
        if myr is not None and myr > 10 and self.roles[18].status.total_shields() > 0:
            self.consume_shield_once(18)
            self._log(f"  · 末位放逐：消耗1层护盾，斩杀原第一 {self.N(first)}")
            self.kill(first, 18, "末位放逐联动斩杀")
        r.mem["cd"] = 2
    def act_19(self):
        # 释延能(19)
        # 改动：每回合必定释放（概率100%），随机复制一名存活角色的主动逻辑并执行。
        pool = [i for i in self.alive_ids() if i != 19]
        pick = self.pick_random(19, pool, "万象随机复制对象")
        if pick is None:
            self._log("  · 万象随机：无可复制目标")
            return
        self._log(f"  · 万象随机：复制 {self.N(pick)} 的主动逻辑（以释延能触发）")
        self.dispatch_active(pick)
    def act_20(self):
        if not self.roles[11].alive:
            self._log("  · 父子同心：豆进天已死，本回合无主动（转被动）")
            return
        myr = self.rank_no(20)
        son = self.rank_no(11)
        if myr is None or son is None:
            return
        if myr >= son:
            self._log("  · 父子同心：自身排名不高于豆进天，条件不满足")
            return
        lower = [x for x in self.alive_ids() if self.rank_no(x) is not None and self.rank_no(x) > myr and x != 20]
        if not lower:
            self._log("  · 父子同心：无低位目标")
            return
        t = self.pick_random(20, lower, "父子同心斩杀目标")
        if t is None:
            return
        if self.is_mls_unselectable_by_active_kill(t):
            self._log("  · 父子同心：随机到mls(10)不可选 → 失败")
            return
        p = 0.50 + (son - myr) * 0.05
        p = max(0.0, min(0.80, p))
        if self.rng.random() <= p:
            self._log(f"  · 父子同心：成功率{int(p*100)}%判定成功，斩杀 {self.N(t)} 并与豆进天交换")
            self.kill(t, 20, "父子同心斩杀")
            if self.roles[11].alive:
                self.swap(20, 11, source=20, note="父子同心成功后交换")
        else:
            self._log(f"  · 父子同心：成功率{int(p*100)}%判定失败")
    # 4) 钟无艳：删除孤傲/禁盾；仅保留“每3回合遗忘1回合”
    def act_21(self):
        r = self.roles[21]
        r.mem["counter"] = r.mem.get("counter", 0) + 1
        if r.mem["counter"] % 3 != 0:
            self._log("  · 往事皆尘：计数未到（每3回合）")
            return
        alive = [x for x in self.alive_ids() if x != 21]
        target = self.pick_random(21, alive, "往事皆尘目标")
        if target is None:
            return
        if self.roles[target].status.sealed > 0 or self.roles[target].status.forgotten > 0:
            self._log("  · 往事皆尘：目标已封印/遗忘，无效")
            return
        before_t = self.roles[target].status.brief()
        self.roles[target].status.forgotten = max(self.roles[target].status.forgotten, 1)
        self._oulu_bump_on_status_change(target, before_t)
        self._log(f"  · 往事皆尘：{self.N(target)} 遗忘主动技能1回合")
    def act_23(self):
        r = self.roles[23]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 久旱逢甘霖：冷却中")
            return
        cand = []
        for cid in self.alive_ids():
            if cid == 23:
                continue
            t = self.roles[cid].mem.get("alive_turns", 0)
            if t >= 2:
                cand.append(cid)
        if not cand:
            self._log("  · 久旱逢甘霖：无连续存活≥2目标")
            r.mem["cd"] = 2
            return
        target = self.pick_random(23, cand, "久旱逢甘霖目标")
        if target is None:
            return
        if self.is_mls_unselectable_by_active_kill(target):
            self._log("  · 久旱逢甘霖：随机到mls(10)不可选 → 失败")
        else:
            self._log(f"  · 久旱逢甘霖：斩杀 {self.N(target)}")
            self.kill(target, 23, "久旱逢甘霖随机斩杀")
        r.mem["cd"] = 2
    def act_24(self):
        r = self.roles[24]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 混乱更换：冷却中")
            return
        cand = [x for x in self.alive_ids() if x != 24]
        if len(cand) < 2:
            self._log("  · 混乱更换：目标不足")
            return
        a, b = self.rng.sample(cand, 2)
        self._log(f"  · 混乱更换：{self.N(a)} 与 {self.N(b)} 互换")
        self.swap(a, b, source=24, note="混乱更换")
        r.mem["cd"] = 2
    def act_25(self):
        # Default: no active skill (blessings are handled in passives).
        if not self.joke_mode:
            self._log("  · 无主动技能（祝福为被动叠加）")
            return
        # Joke mode: invincible + 10 times per turn: eliminate a random role, then move up 1.
        self._log("  · 找自称(25) 无敌：获得护盾99999疫一切）")
        try:
            self.roles[25].status.__dict__["fake_99999"] = True
        except Exception:
            pass
        npc_ids = {getattr(self, "HW_CID", 1001), getattr(self, "LDL_CID", 1002)}
        for i in range(10):
            targets = [cid for cid in self.alive_ids() if cid != 25 and cid not in npc_ids]
            if not targets:
                break
            v = self.rng.choice(targets)
            self._log(f"    - 第{i+1}次：随机淘汰 {self.N(v)}")
            # Direct elimination (bypass shields & revival) to match the joke-mode description.
            self.kill(v, 25, "玩笑模式随机淘汰", bypass_shield=True, bypass_revive=True)
            # After each trigger, rise 1 position.
            self.move_by(25, -1)


    def act_26(self):
        if self.turn == 6:
            self._log("  · 【自我放逐】：Sunnydayorange(26) 自己移除自己（第6回合）")
            self.kill(26, None, "自我放逐", bypass_shield=True, bypass_revive=True)
        else:
            self._log("  · 无主动技能（仅第6回合触发【自我放逐】）")
    # =========================
    # 死亡触发
    # =========================
    def on_death_7(self, killer: Optional[int]):
        if killer is None or killer not in self.roles or (not self.roles[killer].alive):
            self._log("  · hewenx怨念爆发：无有效凶手")
            return
        threshold = self.start_rank_snapshot.get(7, 999)
        self.roles[killer].status.hewenx_curse = {"killer": killer, "threshold_rank": threshold}
        self._log(f"  · hewenx怨念爆发：标记凶手 {self.N(killer)}，下回合行动前若排名高于阈值则斩杀（护盾无效）")
    def on_death_9(self):
        # 书法家(9) 的死亡触发已改为“立刻复活并获得永久遗策直插第一（本局一次）”，
        # 因此此处不再执行旧版“遗策/留痕”随机效果。
        return
    def on_death_14(self, killer: Optional[int]):
        """郑孑健(14)【血债血偿】：首次被淘汰时复活，并反杀击杀者。"""
        if 14 not in self.roles:
            return
        r = self.roles[14]
        st = r.status
        if st.perma_disabled:
            return
        if r.mem.get("revive_used"):
            self._log("  · 血债血偿：已用过，本次不触发")
            return

        # 触发一次性复活
        r.mem["revive_used"] = True
        r.alive = True
        self._log(f"  · 【血债血偿】{self.N(14)} 首次被淘汰时复活")

        # 反杀凶手
        if killer is None or killer not in self.roles or (not self.roles[killer].alive):
            self._log("    ↳ 无有效存活凶手，不触发反杀")
        else:
            self._log(f"    ↳ 反杀 {self.N(killer)}")
            self.kill(14, killer, "血债血偿反杀")

        # 复活后移到队尾并整理
        if 14 in self.rank:
            self.rank.remove(14)
        self.rank.append(14)
        self._compact()

    def act_27(self):
        # 黄伶俐(27)
        # 【穷追猛打】每两回合发动：随机淘汰一人，记录双方排名，
        # 随后自己上升“排名差值”（按绝对差计算）。
        if self.turn % 2 != 0:
            self._log("  · 穷追猛打：未到发动回合（每两回合）")
            return
        myr = self.rank_no(27)
        if myr is None:
            return
        pool = [cid for cid in self.alive_ids() if cid != 27 and cid != 10]  # mls(10) 不可被主动淘汰
        if not pool:
            self._log("  · 穷追猛打：无可淘汰目标")
            return
        target = self.pick_random(27, pool, "穷追猛打淘汰目标")
        if target is None:
            return
        tr = self.rank_no(target)
        if tr is None:
            return
        self._log(f"  · 穷追猛打：随机淘汰 {self.N(target)}（我={myr}名，目标={tr}名）")
        died = self.kill(target, 27, "穷追猛打淘汰")
        if not died:
            self._log("  · 穷追猛打：淘汰被抵挡（护盾）→ 不进行位移")
            return
        diff = abs(tr - myr)
        if diff > 0:
            self._log(f"  · 穷追猛打：上升排名差值 {diff} 名")
            self.move_by(27, -diff, source=27, note="穷追猛打位移")


    def act_29(self):
        # 严雅(29) 净化能量：在其释放主动技能时触发（不再在回合结束触发）。
        # 行为：若不在冷却，则对自己及相邻（排名前后各1）存活者施加【净化】2回合。
        # 冷却：purify_cd > 0 时本回合不释放，并在每次释放阶段 cd-1。
        if (not self.roles[29].alive) or self.roles[29].status.perma_disabled:
            return

        cd = int(self.roles[29].mem.get("purify_cd", 0))
        if cd > 0:
            self.roles[29].mem["purify_cd"] = cd - 1
            self._log(f"  · 净化能量：冷却中({cd-1})")
            return

        p = self.pos(29)
        targets = []
        if p is not None:
            for q in (p - 1, p, p + 1):
                if 0 <= q < len(self.rank):
                    t = self.rank[q]
                    if self.roles[t].alive:
                        targets.append(t)

        if targets:
            for t in targets:
                before_t = self.roles[t].status.brief()
                self.roles[t].status.purify_ttl = max(getattr(self.roles[t].status, "purify_ttl", 0), 2)
                self._on_status_change(t, before_t)
            self._log("  · 净化能量：" + "、".join(self.N(x) for x in targets) + " 获得【净化】(2回合)")

    def act_34(self):
        # 季任杰(34)
        # 【越挫越勇】被动：在回合末结算（见 step_update_and_cleanup）
        self._log("  · 无主动技能（被动：越挫越勇在回合末结算）")


    def act_36(self):
        # 施禹谦(36) 无主动技能；被动在回合末判定【天罚灭世】与回合初【神威】处决
        self._log("  · 无主动技能（被动：天罚灭世/神威）")

    def act_38(self):
        # 陆泽灏(38)
        # 【翩若惊鸿】每回合有5%概率立刻升至第一名。
        # 若判定失败，则下一回合概率上升5%（可叠加），最高80%。
        r = self.roles[38]
        p = float(r.mem.get("pyjh_p", 0.05))
        p = max(0.05, min(0.80, p))
        if self.rng.random() < p:
            self._log(f"  · 翩若惊鸿：{int(p*100)}% 判定成功 → 立刻升至第一名")
            self.insert_rank(38, 1, source=38, note="翩若惊鸿")
            r.mem["pyjh_p"] = 0.05
        else:
            p2 = min(0.80, p + 0.05)
            r.mem["pyjh_p"] = p2
            self._log(f"  · 翩若惊鸿：{int(p*100)}% 判定失败 → 下回合概率提升至{int(p2*100)}%")

    def act_40(self):
        # 姚舒馨(40)
        # 【烈焰炸弹】若场上不存在炸弹：随机一人获得炸弹（红色状态）。
        # 若场上存在炸弹：引爆，持有者被姚舒馨淘汰；若其排名高于姚舒馨，则姚舒馨代替其位置。
        alive = self.alive_ids()
        if not alive:
            return
        holders = [cid for cid in alive if self.roles[cid].status.bomb]
        if not holders:
            pool = [cid for cid in alive if cid != 40]
            if not pool:
                self._log("  · 烈焰炸弹：无可生成目标")
                return
            target = self.pick_random(40, pool, "烈焰炸弹投放目标")
            if target is None:
                self._log("  · 烈焰炸弹：未选中目标（可能全体隐身/不可选）")
                return
            before = self.roles[target].status.brief()
            self.roles[target].status.bomb = True
            self._log(f"  · 烈焰炸弹：{self.N(target)} 获得【炸弹】")
            self._on_status_change(target, before)
            return

        holder = holders[0]
        holder_rank = self.rank_no(holder)
        my_rank = self.rank_no(40)
        if holder_rank is None or my_rank is None:
            return

        self._log(f"  · 烈焰炸弹：引爆 {self.N(holder)} 的炸弹")
        died = self.kill(holder, 40, "烈焰炸弹引爆淘汰")
        # 无论是否淘汰成功（护盾/免疫等），炸弹都会消失
        before_b = self.roles[holder].status.brief()
        self.roles[holder].status.bomb = False
        self._on_status_change(holder, before_b)
        if not died:
            # 护盾抵挡也应消耗炸弹（修复：炸弹不应继续留场）
            self._log("  · 烈焰炸弹：淘汰被抵挡（护盾）→ 炸弹消失")
            return

        if holder_rank < my_rank and self.roles[40].alive:
            self._compact()
            self._log(f"  · 烈焰炸弹：目标原排名更高 → {self.N(40)} 代替其位置（第{holder_rank}名）")
            self.insert_rank(40, holder_rank, source=None, note="烈焰炸弹代替位置")

    def act_41(self):
        # 张志成（41）【迫近战线】主动，冷却2回合
        if not self.roles[41].alive or self.roles[41].status.perma_disabled:
            return
        st = self.roles[41].status
        if getattr(st, "frontline_cd", 0) > 0:
            return
        r41 = self.rank_no(41)
        if r41 is None:
            return
        cand = []
        for x in self.alive_ids():
            if x == 41:
                continue
            rx = self.rank_no(x)
            if rx is not None and rx < r41:
                cand.append(x)
        if not cand:
            return
        t = self.rng.choice(cand)
        if 41 not in self._active_logged:
            self._active_logged.add(41)
            self._log(f"【{self.N(41)}】发动主动技能…")
        self._log(f"  · 迫近战线：选择 {self.N(t)}，双方互相逼近1名")
        # 自己上升1，目标下降1
        self.move_by(41, -1, source=41, note="迫近战线")
        self.move_by(t, 1, source=41, note="迫近战线")
        st.frontline_cd = 2

    def act_33(self):
        # 沈澄婕：无主动技能（仅被动【特异性免疫】）
        self._log("  · 无主动技能（被动：特异性免疫）")


    def act_39(self):
        # 朱诚
        # 【导电性】（主动）转移自身雷霆层数给随机一名排名高于自身的角色；成功则获得1层感电，叠满3后每回合消耗1层并上升3名
        if not self.roles[39].alive or self.roles[39].status.perma_disabled:
            return
        st = self.roles[39].status
        if st.thunder <= 0:
            self._log("  · 导电性：自身无雷霆可转移")
            return
        my_rank = self.rank_no(39)
        if my_rank is None:
            return
        higher = [cid for cid in self.alive_ids() if (self.rank_no(cid) is not None and self.rank_no(cid) < my_rank)]
        if not higher:
            self._log("  · 导电性：无排名高于自身的目标")
            return
        target = self.pick_random(39, higher, "导电性转移目标")
        if target is None:
            self._log("  · 导电性：未选中目标（可能全体隐身/不可选）")
            return
        before_t = self.roles[target].status.brief()
        trans = st.thunder
        st.thunder = 0
        self.roles[target].status.thunder += trans
        self._on_status_change(target, before_t)
        self._log(f"  · 导电性：转移雷霆{trans}层 → {self.N(target)}")
        # 获得感电
        st.dian = min(3, getattr(st, "dian", 0) + 1)
        self._log(f"  · 导电性：{self.N(39)} 获得1层【感电】(当前{st.dian}/3)")

    def act_42(self):
        # 俞守衡
        # 【鱼龙潜跃】若场上不存在鱼，则随机为一个角色施加一个“鱼”（蓝色）
        # 【游鱼归渊】鱼每回合将附身者以及相邻角色向下拖一个名次；俞守衡自己不受影响
        alive = self.alive_ids()
        if not alive:
            return

        fish_exists = any(self.roles[cid].alive and self.roles[cid].status.fish for cid in self.roles)
        if not fish_exists:
            pool = [cid for cid in alive if cid != 42]
            if not pool:
                self._log("  · 鱼龙潜跃：无可施加目标")
            else:
                target = self.pick_random(42, pool, "鱼龙潜跃施加目标")
                if target is None:
                    self._log("  · 鱼龙潜跃：未选中目标（可能全体隐身/不可选）")
                else:
                    self.set_status(target, "fish", True, 42, note="鱼龙潜跃")
                    self._log(f"  · 鱼龙潜跃：{self.N(target)} 获得【鱼】")

        # 游鱼归渊：取场上第一条鱼的附身者（规则：场上至多1条鱼）
        alive_now = self.alive_ids()
        holders = [cid for cid in alive_now if self.roles[cid].status.fish]
        if not holders:
            self._log("  · 游鱼归渊：场上无鱼")
            return

        holder = holders[0]
        p = self.pos(holder)
        if p is None:
            return

        affected = []
        for q in (p - 1, p, p + 1):
            if 0 <= q < len(self.rank):
                c = self.rank[q]
                if self.roles[c].alive and c != 42:
                    affected.append(c)

        seen = set()
        affected = [x for x in affected if not (x in seen or seen.add(x))]
        if not affected:
            self._log("  · 游鱼归渊：无受影响目标")
            return

        self._log("  · 游鱼归渊：鱼 牵引  " + "、".join(self.N(x) for x in affected) + " 下移1位")
        # 同步位移：从后往前移动，避免先移动导致相互抵消
        affected_sorted = sorted(affected, key=lambda x: self.rank_no(x) or 0, reverse=True)
        for c in affected_sorted:
            self.move_by(c, +1, source=42, note="游鱼归渊")

    def act_46(self):
        # 戚银潞：第一回合标记两名队友（仅日志记录）
        r = self.roles[46]
        if self.turn == 1 and (not r.mem.get("mates_picked", False)):
            pool = [cid for cid in self.alive_ids() if cid != 46]
            if len(pool) >= 2:
                a, b = self.rng.sample(pool, 2)
                r.mem["mates_picked"] = True
                r.mem["mates"] = [a, b]
                self._log(f"  · 孤军奋战：队友标记为 {self.N(a)}、{self.N(b)}（仅记录）")
        # 主动无额外效果
        return

        if not any(self.roles[cid].alive and self.roles[cid].status.fish for cid in self.roles):
            pool = [cid for cid in alive if cid != 42]
            if pool:
                target = self.pick_random(42, pool, "鱼龙潜跃施加目标")
                if target is not None:
                    self.set_status(target, 'fish', True, 42, note='鱼龙潜跃')
                    self._log(f"  · 鱼龙潜跃：{self.N(target)} 获得【鱼】")

        # 【游鱼归渊】鱼每回合牵引附身者及相邻者下拖一位；俞守衡自己不受影响
        alive_now = self.alive_ids()
        holders = [cid for cid in alive_now if self.roles[cid].status.fish]
        if holders:
            holder = holders[0]
            p = self.pos(holder)
            if p is not None:
                affected = []
                for q in (p-1, p, p+1):
                    if 0 <= q < len(self.rank):
                        c = self.rank[q]
                        if self.roles[c].alive and c != 42:
                            affected.append(c)
                # 去重
                seen=set()
                affected=[x for x in affected if not (x in seen or seen.add(x))]
                if affected:
                    self._log("  · 游鱼归渊：鱼 牵引  " + "、".join(self.N(x) for x in affected) + " 下移1位")
                    for c in affected:
                        self.move_by(c, +1, source=42, note="游鱼归渊")

        self.roles[14].mem["revive_used"] = True
        self.roles[14].alive = True
        self._log(f"  · 血债血偿：{self.N(14)} 复活并杀死凶手 {self.N(killer)}")

        self.kill(killer, 14, "血债血偿反杀凶手", bypass_shield=False, bypass_revive=True)

        # 复活后必定在最后一名
        self._compact()
        if self.roles[14].alive:
            # 确保 rank 中只有一个 14
            self.rank = [cid for cid in self.rank if cid != 14]
            self.rank.append(14)
        self._compact()


    def on_death_23(self):
        cand = []
        for cid, r in self.roles.items():
            if cid == 23:
                continue
            if (not r.alive) and ("dead_turn" in r.mem) and (self.turn - r.mem["dead_turn"] > 3):
                cand.append(cid)
        if cand:
            t = self.rng.choice(cand)
            self.roles[t].alive = True
            self._log(f"  · 梅雨神死亡被动：复活 {self.N(t)}（死亡超过3回合）")
            self._compact()
            mid = max(1, len(self.rank) // 2 + 1)
            self.rank.insert(mid - 1, t)
            self._compact()
    # =========================
    # 回合存活计数
    # =========================
    def tick_alive_turns(self):
        for cid, r in self.roles.items():
            if r.alive:
                r.mem["alive_turns"] = r.mem.get("alive_turns", 0) + 1
            else:
                if "dead_turn" not in r.mem:
                    r.mem["dead_turn"] = self.turn
    # ---------- 批量模拟 ----------
    def play_to_end(self, max_turns: int = 5000) -> Optional[int]:
        for _ in range(max_turns):
            if self.game_over:
                alive = self.alive_ids()
                return alive[0] if len(alive) == 1 else None
            if not self.alive_ids():
                return None
            try:
                self.tick_alive_turns()
                self.next_turn()
            except Exception:
                return None
        return None
# =========================
# UI
# =========================
class UI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("神秘游戏 made by dian_mi")
        self.root.geometry("1100x720")
        self.engine = Engine(seed=None)
        # 播放/回放状态
        self.play_cursor = 0
        self.playing = False
        self._play_job = None  # after() job id for auto-play (avoid stacking)
        self.speed_var = tk.DoubleVar(value=0.25)
        # 显示历史（右侧日志与逐行回放）
        self.preserve_history = tk.BooleanVar(value=True)
        self.show_realname = tk.BooleanVar(value=False)
        self.show_initials = tk.BooleanVar(value=False)
        self.auto_skip_turn = tk.BooleanVar(value=True)
        self.export_error_log = False
        self._auto_skip_job: Optional[str] = None
        # Joke mode: "找自称无敌模式" (default off)
        self.joke_mode = tk.BooleanVar(value=False)
        self.revealed_lines: List[str] = []
        self.revealed_hls: List[List[int]] = []
        self.revealed_victims: List[Optional[int]] = []
        self.current_snap = None
        self.current_highlights: set[int] = set()
        self.font_size = 16
        self.font_rank = tkfont.Font(family="Microsoft YaHei UI", size=self.font_size, weight="normal")
        self.font_log = tkfont.Font(family="Microsoft YaHei UI", size=self.font_size, weight="normal")
        self.font_log_bold = tkfont.Font(family="Microsoft YaHei UI", size=self.font_size, weight="bold")
        self._cid_pat = re.compile(r"\((\d{1,3})\)")
        # 颜色
        self.color_thunder = "#0B3D91"
        self.color_pos = "#D4AF37"
        self.color_neg = "#E53935"
        self.color_purple = "#8E44AD"
        self.NPC_NAME_COLOR = {1001: "#D4AF37", 1002: "#D4AF37", 901: "#D4AF37", 902: "#1E40AF"}
        # 显示实名：仅改名字，不改机制、不改编号
        self.REALNAME_MAP = {
            "更西部": "高鑫博",
            "Sunnydayorange": "秦添城",
            "施博理": "施博文",
            "释延能": "邵煜楠",
            "牵寒": "黄芊涵",
            "mls": "孟真",
            "放烟花": "范雨涵",
            "合议庭": "黄煜婷",
            "藕禄": "欧鹭",
            "梅雨神": "董玫妤",
            "豆进天之父": "胡喆",
            "钟无艳": "章文元",
            "hewenx": "何文馨",
            "豆进天": "窦竞天",
            "书法家": "孙凡珺",
            "路济阳": "陆嘉翊",
            "增进舒": "曾靖舒",
            "找自称": "赵梓琛",
            "郑孑健": "郑子健",
            "左右脑": "甄艺诺",
        }

        self.INITIALS_MAP = {
            "朱昊泽": "zhz",
            "蒋骐键": "jqj",
            "李知雨": "lzy",
            "朱诚": "zc",
            "邵煜楠": "syn",
            "陈心如": "cxr",
            "俞守衡": "ysh",
            "施禹谦": "syq",
            "虞劲枫": "yjf",
            "范一诺": "fyn",
            "孙凡珺": "sfj",
            "严雅": "yy",
            "陆嘉翊": "ljy",
            "甄艺诺": "zyn",
            "黄煜婷": "hyt",
            "赵梓琛": "赵zc",
            "卞一宸": "byc",
            "章文元": "zyw",
            "施沁皓": "sqh",
            "秦添城": "qtc",
            "季任杰": "jrj",
            "黄伶俐": "hll",
            "高鑫博": "gxb",
            "郑子健": "zzj",
            "金逸阳": "jyy",
            "范雨涵": "fyh",
            "胡喆": "hz",
            "谢承哲": "xcz",
            "何文馨": "hwx",
            "沈澄婕": "scj",
            "张志成": "张zc",
            "孟真": "mz",
            "黄梓睿": "hzr",
            "冷雨霏": "lyf",
            "黄芊涵": "hqh",
            "欧鹭": "ol",
            "姚舒馨": "ysx",
            "施博文": "sbw",
            "曾靖舒": "zjs",
            "董玫妤": "dmy",
            "陆泽灏": "lzh",
            "戚银潞": "qyl",
            "窦竞天": "djt",
        }
        self._build()
        self.refresh()
    # ---------- 菜单 ----------
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        menu = tk.Menu(menubar, tearoff=0)
        menu.add_command(label="说明", command=self.show_help)
        menu.add_separator()
        menu.add_command(label="快速跑500局", command=self.on_sim_500)
        menu.add_command(label="快速跑5000局", command=self.on_sim_5000)
        menu.add_command(label="快速跑50000局", command=self.on_sim_50000)
        menu.add_separator()
        menu.add_checkbutton(label="输出异常日志到脚本目录(error_log.txt)", variable=self.export_error_log, command=self._on_toggle_export_error)
        menu.add_checkbutton(label="自动跳过回合（回合结束后5秒）", variable=self.auto_skip_turn, command=self._on_toggle_auto_skip)
        menu.add_checkbutton(label="找自称无敌模式", variable=self.joke_mode, command=self._on_toggle_joke_mode)
        menu.add_checkbutton(label="保留历史记录", variable=self.preserve_history)
        menu.add_checkbutton(label="显示实名", variable=self.show_realname, command=self._on_toggle_show_realname)
        menu.add_checkbutton(label="显示首字母", variable=self.show_initials, command=self._on_toggle_show_initials)
        menu.add_separator()
        menu.add_command(label="字体放大", command=lambda: self.adjust_font(2))
        menu.add_command(label="字体缩小", command=lambda: self.adjust_font(-2))
        menubar.add_cascade(label="菜单", menu=menu)
        self.root.config(menu=menubar)
    def _on_toggle_export_error(self):
        self.engine.export_error_log = bool(self.export_error_log.get())
        if self.engine.export_error_log:
            try:
                with open(self.engine._error_log_path(), "a", encoding="utf-8") as f:
                    f.write("\n=== Error log enabled ===\n")
            except Exception as e:
                self.log_text.configure(state="normal")
                self.log_text.insert(tk.END, f"\n【警告】无法写入异常日志文件：{e}\n")
                self.log_text.configure(state="disabled")
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert(tk.END, "\n【设置】异常日志输出：%s\n路径：{self.engine._error_log_path()}\n" % ("开启" if self.engine.export_error_log else "关闭"))
            self.log_text.configure(state="disabled")
            self.log_text.see(tk.END)
        except Exception:
            pass

    def _on_toggle_auto_skip(self):
        """Toggle auto-skip timer. When turned off, cancel any pending after() job."""
        if not self.auto_skip_turn.get():
            if self._auto_skip_job is not None:
                try:
                    self.root.after_cancel(self._auto_skip_job)
                except Exception:
                    pass
                self._auto_skip_job = None
    def _on_toggle_joke_mode(self):
        """Toggle joke mode and synchronize to engine."""
        try:
            self.engine.joke_mode = bool(self.joke_mode.get())
            if 25 in self.engine.roles:
                st = self.engine.roles[25].status
                st.__dict__["fake_99999"] = bool(self.joke_mode.get())
        except Exception:
            pass

    # ---------- UI 构建 ----------
    def _build(self):
        self._build_menu()
        self.main = ttk.Frame(self.root, padding=8)
        self.main.pack(fill=tk.BOTH, expand=True)
        self.main.columnconfigure(0, weight=2, uniform="main")
        self.main.columnconfigure(1, weight=1, uniform="main")
        self.main.rowconfigure(0, weight=1)
        # 左：排名
        self.left = ttk.Frame(self.main)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.left.columnconfigure(0, weight=1)
        self.left.rowconfigure(0, weight=1)
        self.rank_frame = ttk.Frame(self.left)
        self.rank_frame.grid(row=0, column=0, sticky="nsew")
        self.rank_frame.columnconfigure(0, weight=1)
        self.rank_frame.columnconfigure(1, weight=1)
        # 预建行池：为“未来可能添加更多角色”准备，默认给 40 行
        self.max_rows = max(40, len(self.engine.roles) + 8)
        self.rank_rows: List[Dict[str, Any]] = []
        for i in range(self.max_rows):
            row = tk.Frame(self.rank_frame, bg=self.root.cget("bg"))
            name_lbl = tk.Label(row, text="", anchor="w", font=self.font_rank, bg=self.root.cget("bg"))
            name_lbl.pack(side="left")
            tags_frame = tk.Frame(row, bg=self.root.cget("bg"))
            tags_frame.pack(side="right", padx=6)
            self.rank_rows.append({"frame": row, "name": name_lbl, "tags": tags_frame})
        # 右：日志
        self.right = ttk.Frame(self.main)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.rowconfigure(0, weight=1)
        self.right.columnconfigure(0, weight=1)
        self.log_text = tk.Text(self.right, wrap="word", font=self.font_log)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.right, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")
        # 底部按钮
        self.bottom = ttk.Frame(self.main)
        self.bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(self.bottom, text="新开局", command=self.on_new).grid(row=0, column=0, padx=8)
        self.btn_turn = ttk.Button(self.bottom, text="下一回合", command=self.on_build_turn)
        self.btn_turn.grid(row=0, column=1, padx=8)
        self.btn_step = ttk.Button(self.bottom, text="下一行", command=self.on_step_line)
        self.btn_step.grid(row=0, column=2, padx=8)
        self.btn_auto = ttk.Button(self.bottom, text="自动播放", command=self.on_auto_play)
        self.btn_auto.grid(row=0, column=3, padx=8)
        self.btn_pause = ttk.Button(self.bottom, text="暂停", command=self.on_pause)
        self.btn_pause.grid(row=0, column=4, padx=8)
        ttk.Label(self.bottom, text="播放速度").grid(row=0, column=5, padx=(20, 6))
        self.speed_scale = ttk.Scale(
            self.bottom,
            from_=0.1,
            to=2.0,
            orient="horizontal",
            variable=self.speed_var,
            command=lambda _v: self._update_speed_label()
        )
        self.speed_scale.grid(row=0, column=6, padx=6, sticky="ew")
        self.speed_label = ttk.Label(self.bottom, text="")
        self.speed_label.grid(row=0, column=7, padx=(6, 0))
        self.bottom.columnconfigure(6, weight=1)
        self._update_speed_label()
    def _update_speed_label(self):
        try:
            v = float(self.speed_var.get())
        except Exception:
            v = 0.25
        self.speed_label.config(text=f"{v:.2f}s/行")
    # ---------- 名字展示（实名/首字母） ----------
    def _on_toggle_show_realname(self):
        """互斥：开启显示实名时自动关闭显示首字母。"""
        if self.show_realname.get() and self.show_initials.get():
            self.show_initials.set(False)
        self.refresh()

    def _on_toggle_show_initials(self):
        """互斥：开启显示首字母时自动关闭显示实名。"""
        if self.show_initials.get() and self.show_realname.get():
            self.show_realname.set(False)
        self.refresh()

    def _display_name(self, cid: int) -> str:

        """根据开关返回展示名：原昵称 / 实名 / 首字母（互斥）。并清理首尾空格。"""

        name = self.engine.roles[cid].name.strip()

        if self.show_realname.get():

            return self.REALNAME_MAP.get(name, name).strip()

        if self.show_initials.get():

            real = self.REALNAME_MAP.get(name, name).strip()

            return self.INITIALS_MAP.get(real, real).strip()

        return name
    def _rewrite_names_in_line(self, line: str) -> str:
        """Normalize name tokens in log lines.
        - Always remove '(cid)' or '（cid）' suffixes from names in logs.
        - If 'show realname' or 'show initials' is enabled, convert names accordingly.
        """
        # Match both ASCII and full-width parentheses: Name(12) / Name（12）
        pattern = re.compile(r'([\u4e00-\u9fffA-Za-z0-9_\-·\.\s]{1,30})[\(（]\s*(\d+)\s*[\)）]')
        use_mode = self.show_realname.get() or (hasattr(self, "show_initials") and self.show_initials.get())
        def repl(m):
            cid = int(m.group(2))
            if use_mode:
                return self._display_name(cid)
            # mode off: keep original name but strip spaces (and remove cid)
            return m.group(1).strip()
        return pattern.sub(repl, line)
        def repl(m):
            cid = int(m.group(2))
            return f"{self._display_name(cid)}"
        return pattern.sub(repl, line)
        def repl(m):
            cid = int(m.group(2))
            if cid in self.engine.roles:
                return f"{self._display_name(cid)}({cid})"
            return m.group(0)
        return token_pat.sub(repl, line)
    # ---------- 说明 ----------
    
    def adjust_font(self, delta: int):
        # 菜单：动态调整字体大小（影响排行榜与日志）
        new_size = self.font_size + delta
        new_size = max(10, min(40, new_size))
        if new_size == self.font_size:
            return
        self.font_size = new_size
        self.font_rank.configure(size=self.font_size)
        self.font_log.configure(size=self.font_size)
        self.font_log_bold.configure(size=self.font_size)
        # 触发一次刷新，确保显示稳定
        self.refresh()
    def show_help(self):
        win = tk.Toplevel(self.root)
        win.title("游戏说明")
        win.geometry("700x520")
        text = tk.Text(win, wrap="word", font=("Microsoft YaHei UI", 12))
        text.pack(fill="both", expand=True, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(win, command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.config(yscrollcommand=scrollbar.set)
        help_text = """
made by dian_mi
但是其实都是GPT大人神力
欢迎大家游玩
菜单说明：
- 快速跑5000局：完整规则蒙特卡洛统计（界面可能短暂无响应）
- 自动跳过回合：每次回合日志播完后，等待5秒自动推进下一回合
- 保留历史记录：推进新回合时，右侧日志不清空、会继续累积（便于复盘）
"""
        text.insert("1.0", help_text.strip())
        text.config(state="disabled")
    # ---------- 新开局 ----------
    def on_new(self):
        if self._auto_skip_job is not None:
            try:
                self.root.after_cancel(self._auto_skip_job)
            except Exception:
                pass
            self._auto_skip_job = None
        self.engine.new_game()
        self.play_cursor = 0
        self.playing = False
        self.revealed_lines = []
        self.revealed_hls = []
        self.revealed_victims = []
        self.current_snap = None
        self.current_highlights = set()
        self._set_buttons_enabled(True)
        self.refresh()
    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for b in (self.btn_turn, self.btn_step, self.btn_auto, self.btn_pause):
            try:
                b.config(state=state)
            except Exception:
                pass
    # ---------- 快速模拟 ----------
    
    def _run_quick_sim(self, GAMES: int):
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert(tk.END, f"\n【测试】开始快速模拟{GAMES}局…（期间界面可能短暂无响应）\n")
            self.log_text.configure(state="disabled")
            self.log_text.see(tk.END)
            self.root.update_idletasks()
        except Exception:
            pass
        first_cnt = {cid: 0 for cid in self.engine.roles.keys()}
        top3_cnt = {cid: 0 for cid in self.engine.roles.keys()}
        top10_cnt = {cid: 0 for cid in self.engine.roles.keys()}
        place_sum = {cid: 0 for cid in self.engine.roles.keys()}
        place_cnt = {cid: 0 for cid in self.engine.roles.keys()}
        survive_sum = {cid: 0 for cid in self.engine.roles.keys()}
        survive_cnt = {cid: 0 for cid in self.engine.roles.keys()}
        errors = 0
        first_err = None

        timeouts = 0
        skill_errors = 0
        valid_games = 0
        seed_rng = random.Random()
        for gi in range(GAMES):
            try:
                e = Engine(seed=seed_rng.randint(1, 10**9), fast_mode=True)
                seed = e.base_seed

                # [v19 debug] 继承UI开关到快速跑引擎，并写入每局标记
                e.export_error_log = bool(self.engine.export_error_log)
                if e.export_error_log:
                    try:
                        with open(self.engine._error_log_path(), "a", encoding="utf-8") as f:
                            f.write("\n[v19] quick_sim start seed=%s\n" % (e.base_seed,))
                            f.flush()
                    except Exception as _e:
                        try:
                            self.log_text.configure(state="normal")
                            self.log_text.insert(tk.END, f"\n【警告】写入error_log失败：{_e}\n")
                            self.log_text.configure(state="disabled")
                        except Exception:
                            pass
                # Run until game over (or until safety cap). If cap is hit, treat as timeout and exclude.
                MAX_TURNS = 50000
                for __ in range(MAX_TURNS):
                    if e.game_over:
                        break
                    e.tick_alive_turns()
                    e.next_turn()
                if (not e.game_over) and len(e.alive_ids()) > 1:
                    timeouts += 1
                    continue
                # If any skill exception happened, treat the game as invalid (rules not executed correctly).
                if e.skill_exception_count > 0:
                    skill_errors += 1

                if e.skill_exception_count > 0 and getattr(e, "export_error_log", False):
                    try:
                        with open(e._error_log_path(), "a", encoding="utf-8") as f:
                            f.write("\n=== Game %d skill_exceptions=%d seed=%s ===\n" % (gi+1, e.skill_exception_count, seed))
                            for ex in getattr(e, "skill_exception_examples", [])[:20]:
                                if len(ex) == 3:
                                    cid_, msg_, tb_ = ex
                                else:
                                    cid_, msg_ = ex[0], ex[1]
                                    tb_ = ""
                                f.write("- %s: %s\n" % (e.N(cid_), msg_))
                                if tb_:
                                    f.write(tb_ + "\n")
                    except Exception:
                        pass
                    continue
                alive = e.alive_ids()

                if getattr(e, "export_error_log", False):
                    try:
                        with open(e._error_log_path(), "a", encoding="utf-8") as f:
                            f.write("\n=== Game %d seed=%s skill_exception_count=%d ===\n" % (gi+1, seed, e.skill_exception_count))
                            if e.skill_exception_count > 0:
                                for ex in getattr(e, "skill_exception_examples", [])[:20]:
                                    if len(ex) == 3:
                                        cid_, msg_, tb_ = ex
                                    else:
                                        cid_, msg_ = ex[0], ex[1]
                                        tb_ = ""
                                    f.write("- %s: %s\n" % (e.N(cid_), msg_))
                                    if tb_:
                                        f.write(tb_ + "\n")
                            f.flush()
                    except Exception:
                        pass
                npc_ids = {HW_CID, LDL_CID}
                alive_players = [cid for cid in alive if cid not in npc_ids]
                # 统计每名角色的存活回合数：死亡回合=被淘汰回合；存活到最后=本局总回合数
                for cid_ in self.engine.roles.keys():
                    if cid_ in npc_ids:
                        continue
                    if cid_ in alive_players:
                        sturn = int(e.turn)
                    else:
                        sturn = int(e.elimination_turn.get(cid_, e.turn))
                    survive_sum[cid_] += sturn
                    survive_cnt[cid_] += 1

                elim_players = [cid for cid in e.elimination_order if cid not in npc_ids]

                if len(alive) == 1 and alive_players:
                    # 最终存活者为角色
                    first = alive_players[0]
                    second = elim_players[-1] if len(elim_players) >= 1 else None
                    third = elim_players[-2] if len(elim_players) >= 2 else None
                else:
                    # 最终存活者为NPC或无人存活：前三名取“最后死亡的三名角色”
                    first = elim_players[-1] if len(elim_players) >= 1 else None
                    second = elim_players[-2] if len(elim_players) >= 2 else None
                    third = elim_players[-3] if len(elim_players) >= 3 else None

                # 计算本局最终名次（1为冠军，其次为最后淘汰者…）
                place_map = {}
                if len(alive) == 1 and alive_players:
                    # 冠军为最终存活者
                    place_map[alive_players[0]] = 1
                    for i, cid_ in enumerate(reversed(elim_players), start=2):
                        place_map[cid_] = i
                else:
                    # 无角色存活或冠军为NPC：名次按最后淘汰顺序倒序
                    for i, cid_ in enumerate(reversed(elim_players), start=1):
                        place_map[cid_] = i
                for cid_, pl in place_map.items():
                    place_sum[cid_] += int(pl)
                    place_cnt[cid_] += 1
                    if int(pl) <= 10:
                        top10_cnt[cid_] += 1

                if first is not None:
                    first_cnt[first] += 1
                    top3_cnt[first] += 1
                if second is not None:
                    top3_cnt[second] += 1
                if third is not None:
                    top3_cnt[third] += 1
                valid_games += 1
            except Exception as ex:
                errors += 1
                if first_err is None:
                    first_err = ex
                    try:
                        import traceback as _tb
                        tb_txt = _tb.format_exc()
                        self.log_text.configure(state='normal')
                        self.log_text.insert(tk.END, '\n【快速跑异常示例】\n' + tb_txt + '\n')
                        self.log_text.configure(state='disabled')
                    except Exception:
                        pass
        
        # Build two separate tables: Champion win rate and Top-3 win rate (exclude NPCs).
        npc_ids = {HW_CID, LDL_CID}
        role_ids = [cid for cid in first_cnt.keys() if cid not in npc_ids]
        champ_rows = []
        top3_rows = []
        for cid in role_ids:
            champ_rate = (first_cnt[cid] / valid_games * 100.0) if valid_games > 0 else 0.0
            top3_rate = (top3_cnt[cid] / valid_games * 100.0) if valid_games > 0 else 0.0
            champ_rows.append((cid, champ_rate))
            top3_rows.append((cid, top3_rate))
        champ_rows.sort(key=lambda x: (-x[1], x[0]))
        top3_rows.sort(key=lambda x: (-x[1], x[0]))

        win = tk.Toplevel(self.root)
        win.title(f"{GAMES}局统计（冠军/前三名胜率）")
        win.geometry("560x780")
        textw = tk.Text(win, wrap="none", font=("Consolas", 12))
        textw.tag_configure('hdr', font=('Microsoft YaHei', 11, 'bold'))
        textw.tag_configure('title', font=('Microsoft YaHei', 13, 'bold'))
        textw.tag_configure('alt', background='#f2f2f2')
        textw.tag_configure('hl', background='#ffe8a3')
        NAME_W = 22
        VAL_W = 12
        SEP_W = 40
        textw.pack(fill="both", expand=True, padx=10, pady=10)

        # Summary
        issues = (errors > 0) or (skill_errors > 0) or (timeouts > 0)
        textw.insert(tk.END, f"总局数：{GAMES}\n")
        textw.insert(tk.END, f"正常局数：{valid_games}\n")
        textw.insert(tk.END, f"错误局数：{errors}\n")
        textw.insert(tk.END, f"技能异常局数：{skill_errors}\n")
        textw.insert(tk.END, f"超时未结束局数：{timeouts}\n")
        textw.insert(tk.END, f"是否出现问题：{'是' if issues else '否'}\n\n")

        textw.insert(tk.END, "冠军统计胜率（按胜率从高到低）\n", 'title')
        textw.insert(tk.END, f"{'角色':<{NAME_W}} {'胜率':>8} {'胜场':>6}\n", 'hdr')
        textw.insert(tk.END, "-" * SEP_W + "\n")
        for i, (cid, rate) in enumerate(champ_rows):
            tag = None
            if i < 3:
                tag = 'hl'
            elif i % 2 == 1:
                tag = 'alt'
            textw.insert(tk.END, f"{self.engine.N(cid):<{NAME_W}} {rate:7.3f}% {first_cnt[cid]:6d}\n", tag)

        textw.insert(tk.END, "\n前三名统计胜率（按胜率从高到低）\n")
        textw.insert(tk.END, f"{'角色':<{NAME_W}} {'胜率':>8} {'胜场':>6}\n", 'hdr')
        textw.insert(tk.END, "-" * SEP_W + "\n")
        for i, (cid, rate) in enumerate(top3_rows):
            tag = None
            if i < 3:
                tag = 'hl'
            elif i % 2 == 1:
                tag = 'alt'
            textw.insert(tk.END, f"{self.engine.N(cid):<{NAME_W}} {rate:7.3f}% {top3_cnt[cid]:6d}\n", tag)


        # ---- 平均排名（独立统计）----
        avg_rows = []
        for cid in self.engine.roles.keys():
            if place_cnt.get(cid, 0) > 0:
                avg_place = place_sum[cid] / place_cnt[cid]
                avg_rows.append((cid, avg_place))
        avg_rows.sort(key=lambda x: (x[1], x[0]))

        textw.insert(tk.END, "\n平均排名统计（按平均排名从低到高）\n", 'hdr')
        textw.insert(tk.END, f"{'角色':<{NAME_W}} {'平均排名':>{VAL_W}}\n", 'hdr')
        textw.insert(tk.END, "-" * SEP_W + "\n")
        for i, (cid, avg_place) in enumerate(avg_rows):
            tag = None
            if i < 3:
                tag = 'hl'
            elif i % 2 == 1:
                tag = 'alt'
            textw.insert(tk.END, f"{self.engine.N(cid):<{NAME_W}} {avg_place:{VAL_W}.3f}\n", tag)
        textw.insert(tk.END, "-" * SEP_W + "\n")
        textw.insert(tk.END, "\n")

        # ---- 平均存活回合数（独立统计）----
        surv_rows = []
        for cid in self.engine.roles.keys():
            if survive_cnt.get(cid, 0) > 0:
                avg_surv = survive_sum[cid] / survive_cnt[cid]
                surv_rows.append((cid, avg_surv))
        surv_rows.sort(key=lambda x: (-x[1], x[0]))  # 存活越久越靠前

        textw.insert(tk.END, "\n平均存活回合数统计（按平均存活回合从高到低）\n", 'hdr')
        textw.insert(tk.END, f"{'角色':<{NAME_W}} {'平均存活回合':>{VAL_W}}\n", 'hdr')
        textw.insert(tk.END, "-" * SEP_W + "\n")
        for i, (cid, avg_surv) in enumerate(surv_rows):
            tag = None
            if i < 3:
                tag = 'hl'
            elif i % 2 == 1:
                tag = 'alt'
            textw.insert(tk.END, f"{self.engine.N(cid):<{NAME_W}} {avg_surv:{VAL_W}.3f}\n", tag)
        textw.insert(tk.END, "-" * SEP_W + "\n")
        textw.configure(state="disabled")
    def on_sim_5000(self):
        self._run_quick_sim(5000)

    def on_sim_500(self):
        self._run_quick_sim(500)

    def on_sim_50000(self):
        self._run_quick_sim(50000)


    def on_build_turn(self):
        # If auto-skip had scheduled a pending turn advance, cancel it when user manually advances.
        try:
            if self._auto_skip_job is not None:
                self.root.after_cancel(self._auto_skip_job)
        except Exception:
            pass
        self._auto_skip_job = None
        if self.engine.game_over:
            return
        try:
            if self._play_job is not None:
                self.root.after_cancel(self._play_job)
        except Exception:
            pass
        self._play_job = None
        # 新回合开始：如果不保留历史，就清空“逐行展示缓存”
        if not self.preserve_history.get():
            self.revealed_lines = []
            self.revealed_hls = []
            self.revealed_victims = []
        self.engine.tick_alive_turns()
        self.engine.next_turn()
        self.play_cursor = 0
        self.playing = False
        self.current_snap = None
        self.current_highlights = set()
        # 默认显示第一行并继续自动播放一行（与旧版一致）
        if self.engine.replay_frames:
            self.on_step_line()
            self.playing = True
            self.on_step_line()
        else:
            self.refresh()
    def on_step_line(self):
        frames = self.engine.replay_frames
        if self.play_cursor >= len(frames):
            self.playing = False
            try:
                if self._play_job is not None:
                    self.root.after_cancel(self._play_job)
            except Exception:
                pass
            self._play_job = None
            if self.engine.game_over:
                self._set_buttons_enabled(False)
            else:
                # 自动跳回合：回合日志播完后，5秒推进下一回合
                if self.auto_skip_turn.get():
                    if self._auto_skip_job is not None:
                        try:
                            self.root.after_cancel(self._auto_skip_job)
                        except Exception:
                            pass
                    self._auto_skip_job = self.root.after(5000, self.on_build_turn)
            return
        frame = frames[self.play_cursor]
        self.play_cursor += 1
        self.revealed_lines.append(frame["text"])
        self.revealed_hls.append(frame.get("highlights", []))
        self.revealed_victims.append(self._parse_victim_cid(frame["text"]))
        self.current_snap = frame["snap"]
        self.current_highlights = set(frame.get("highlights", []))
        self.refresh_replay_view()
        if self.playing:
            delay_ms = int(max(0.1, min(2.0, float(self.speed_var.get()))) * 1000)
            # If a random event is triggered, auto-pause 3 seconds for readability.
            try:
                if "触发随机事件：" in frame.get("text", ""):
                    delay_ms = max(delay_ms, 3000)
            except Exception:
                pass
            try:
                if self._play_job is not None:
                    self.root.after_cancel(self._play_job)
            except Exception:
                pass
            self._play_job = self.root.after(delay_ms, self.on_step_line)
    def on_auto_play(self):
        if not self.engine.replay_frames:
            return
        # Avoid stacking multiple after() loops when clicking repeatedly
        if self.playing:
            return
        self.playing = True
        try:
            if self._play_job is not None:
                self.root.after_cancel(self._play_job)
        except Exception:
            pass
        self._play_job = None
        self.on_step_line()
    def on_pause(self):
        self.playing = False
        try:
            if self._play_job is not None:
                self.root.after_cancel(self._play_job)
        except Exception:
            pass
        self._play_job = None
    def _parse_victim_cid(self, line: str) -> Optional[int]:
        # Structured markers
        if "【死亡】" in line:
            m = self._cid_pat.search(line)
            return int(m.group(1)) if m else None
        if "【击杀】" in line:
            ids = [int(m.group(1)) for m in self._cid_pat.finditer(line)]
            if len(ids) >= 2:
                return ids[1]

        # Keywords that imply an elimination in this line (various modes/wordings)
        keywords = ("淘汰", "斩杀", "zhansha", "处决")
        if any(k in line for k in keywords):
            # Prefer cid-based resolution if present
            ids = [int(m.group(1)) for m in self._cid_pat.finditer(line)]
            if len(ids) == 1:
                return ids[0]
            if len(ids) >= 2:
                return ids[-1]

            # Fallback: name-based resolution when the log line contains no (cid)
            # Try to extract the target name that follows the keyword.
            # e.g. "zhansha 书法家" / "斩杀 戚银潞" / "处决第4名：施沁皓"
            seg = line
            for k in keywords:
                if k in seg:
                    seg = seg.split(k, 1)[1]
                    break
            seg = seg.replace("：", " ").replace(":", " ")
            seg = seg.strip()
            if not seg:
                return None
            parts = seg.split()
            if not parts:
                return None
            # Take the first token-like chunk as candidate name
            cand = parts[0].strip("，。,.!！?？;；】")
            if not cand:
                return None

            # Build a map of possible names (display name + real name if present) -> cid
            for cid, role in self.engine.roles.items():
                dn = self._display_name(cid)
                if dn == cand:
                    return cid
                rn = getattr(role, "real_name", "") or ""
                if rn and rn == cand:
                    return cid
                # also allow matching by role.name if display differs
                nm = getattr(role, "name", "") or ""
                if nm and nm == cand:
                    return cid
        return None
    def _clean_log_text(self, line: str) -> str:
        # Remove numeric prefix and cid in headers, e.g. 【23. Name(23)】 -> 【Name】
        # Insert a space after ")" to avoid concatenated names after removing "(cid)"
        line = re.sub(r"\)(?=\S)", ") ", line)
        line = re.sub(r"【\s*\d+\s*\.\s*([^】(]+)\(\d+\)】", r"【\1】", line)
        # Remove any remaining (cid) after names: Name(23) -> Name
        line = re.sub(r"\(\d+\)", "", line)
        line = re.sub(r"\s{2,}", " ", line)
        return line

    # ---------- 渲染 ----------
    def _set_rank_row(self, idx: int, left_text: str, status_parts: List[str], highlight: bool):
        bg = "#FFF2A8" if highlight else self.root.cget("bg")
        row = self.rank_rows[idx]["frame"]
        name_lbl = self.rank_rows[idx]["name"]
        tags_frame = self.rank_rows[idx]["tags"]
        row.configure(bg=bg)
        # NPC name color in left rank list (explicit names)
        if "洪伟" in left_text or "李东雷" in left_text:
            name_fg = "#D4AF37"
        else:
            name_fg = "black"
        name_lbl.configure(text=left_text, bg=bg, fg=name_fg)
        for w in tags_frame.winfo_children():
            w.destroy()
        tags_frame.configure(bg=bg)
        for part in status_parts:
            part = part.strip()
            if not part:
                continue
            if part.startswith("雷霆"):
                fg = self.color_thunder
            elif part.startswith("腐化"):
                fg = self.color_purple
            elif part.startswith("隐身"):
                fg = "#A0A0A0"
            elif part.startswith("鱼"):
                fg = "#2E86C1"
            elif part.startswith("濒亡"):
                fg = "#E53935"
            elif part.startswith("炸弹"):
                fg = "#E53935"
            elif part.startswith("越挫越勇"):
                fg = "#8B4513"
            elif part.startswith("神威"):
                fg = "#D4AF37"
            elif part.startswith("洪伟之赐"):
                fg = "#D4AF37"
            elif part.startswith("雷霆手腕"):
                fg = "#0B3D91"
            elif part.startswith("氧化") or part.startswith("还原"):
                fg = "#006400"
            elif part.startswith("附生"):
                fg = "#F7DC6F"
            elif part.startswith("孤军奋战"):
                fg = "#D4AF37"
            elif part.startswith("特异性免疫"):
                fg = "#2ECC71"
            elif part.startswith("净化"):
                fg = "#7DCEA0"  # 浅绿色
            elif part.startswith("圣辉"):
                fg = "#D4AF37"  # 金色
            elif part.startswith("感电"):
                fg = "#85C1E9"  # 浅蓝色
            elif part.startswith("乘胜追击"):
                fg = "#F5B041"  # 浅橙色
            elif part.startswith("目击"):
                fg = "#8B4513"  # 棕色
            elif part.startswith("辩护"):
                fg = "#D4AF37"  # 金色
            elif part.startswith("静默"):
                fg = "#7D3C98"  # 灰紫
            elif part.startswith("迂回"):
                fg = "#76D7C4"  # 浅青
            elif part.startswith("防线"):
                fg = "#1E8449"  # 深绿
            elif part.startswith("护盾"):
                fg = self.color_pos
            else:
                fg = self.color_neg
            lbl = tk.Label(tags_frame, text=f" {part} ", font=self.font_rank, fg=fg, bg=bg)
            lbl.pack(side="left", padx=(0, 4))
    def refresh_replay_view(self):
        snap = self.current_snap
        if not snap:
            self.refresh()
            return
        rank = snap["rank"]
        status_map = snap["status"]
        normal_bg = self.root.cget("bg")
        # 计算两列布局
        total = len(rank)
        rows_per_col = max(1, math.ceil(total / 2))
        # 先隐藏全部行
        for i in range(self.max_rows):
            row = self.rank_rows[i]["frame"]
            row.grid_forget()
            # 清内容
            self.rank_rows[i]["name"].configure(text="", bg=normal_bg)
            for w in self.rank_rows[i]["tags"].winfo_children():
                w.destroy()
        # 再填充
        for i, cid in enumerate(rank):
            info = status_map[cid]
            st = info["brief"]
            left_text = f"{i+1:>2}. {self._display_name(cid)}"
            status_parts = st.split("；") if st else []
            highlight = (cid in self.current_highlights)
            self._row_name_fg = self.NPC_NAME_COLOR.get(cid)
            self._set_rank_row(i, left_text, status_parts, highlight=highlight)
            self._row_name_fg = None
            r = i % rows_per_col
            c = i // rows_per_col
            self.rank_rows[i]["frame"].grid(row=r, column=c, sticky="ew", padx=(0, 8) if c == 0 else (8, 0), pady=1)
        self.render_log_with_current_highlight(self.revealed_lines, self.revealed_hls)
    def render_log_with_current_highlight(self, lines: List[str], hls: List[List[int]]):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.tag_configure("hl_current", font=self.font_log_bold)
        self.log_text.tag_configure("name_bold", font=self.font_log_bold)
        self.log_text.tag_configure("victim_red", foreground="red")
        self.log_text.tag_configure("event_gold", foreground="#D4AF37", font=self.font_log)
        self.log_text.tag_configure("event_name_bold", foreground="#D4AF37", font=self.font_log_bold)
        last_i = len(lines) - 1
        for i, line in enumerate(lines):
            start_idx = self.log_text.index(tk.INSERT)
            line2 = self._rewrite_names_in_line(line)
            # Normalize any extra spaces inside 【...】 to avoid '【Name 】' artifacts
            line2 = re.sub(r"【[\s\u00A0\u3000]*([^】]*?)[\s\u00A0\u3000]*】", r"【\1】", line2)
            disp_line = self._clean_log_text(line2)
            disp_line = re.sub(r"【[\s\u00A0\u3000]*([^】]*?)[\s\u00A0\u3000]*】", r"【\1】", disp_line)
            self.log_text.insert(tk.END, disp_line + "\n")
            end_idx = self.log_text.index(tk.INSERT)
            if "触发随机事件：" in line2:
                # Only make the event name (【...】) bold; keep the rest in gold normal.
                self.log_text.tag_add("event_gold", start_idx, end_idx)
                try:
                    lbr = line2.index("【")
                    rbr = line2.index("】", lbr) + 1
                    self.log_text.tag_add("event_name_bold", f"{start_idx}+{lbr}c", f"{start_idx}+{rbr}c")
                except Exception:
                    pass
            victim_cid = self.revealed_victims[i] if i < len(self.revealed_victims) else None
            if victim_cid is not None and victim_cid in self.engine.roles:
                token_v = f"{self._display_name(victim_cid)}"
                search_from = start_idx
                while True:
                    pos = self.log_text.search(token_v, search_from, stopindex=end_idx)
                    if not pos:
                        break
                    pos_end = f"{pos}+{len(token_v)}c"
                    self.log_text.tag_add("victim_red", pos, pos_end)
                    search_from = pos_end
            # Bold all names in this line
            for cid2 in self.engine.roles.keys():
                name2 = self._display_name(cid2)
                if not name2:
                    continue
                search_from2 = start_idx
                while True:
                    pos2 = self.log_text.search(name2, search_from2, stopindex=end_idx)
                    if not pos2:
                        break
                    pos2_end = f"{pos2}+{len(name2)}c"
                    self.log_text.tag_add("name_bold", pos2, pos2_end)
                    search_from2 = pos2_end
            if i == last_i and i < len(hls):
                for cid in hls[i]:
                    if cid not in self.engine.roles:
                        continue
                    token = f"{self._display_name(cid)}"
                    search_from = start_idx
                    while True:
                        pos = self.log_text.search(token, search_from, stopindex=end_idx)
                        if not pos:
                            break
                        pos_end = f"{pos}+{len(token)}c"
                        self.log_text.tag_add("hl_current", pos, pos_end)
                        search_from = pos_end
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)
    def _refresh_impl(self):
        # 非回放状态：直接用 engine.log 全量显示
        normal_bg = self.root.cget("bg")
        alive = self.engine.alive_ids()
        total = len(alive)
        rows_per_col = max(1, math.ceil(total / 2))
        for i in range(self.max_rows):

            self.rank_rows[i]["name"].configure(text="", bg=normal_bg)
            for w in self.rank_rows[i]["tags"].winfo_children():
                w.destroy()
        for i, cid in enumerate(alive):
            r = self.engine.roles[cid]
            st = r.status.brief()
            left_text = f"{i+1:>2}. {self._display_name(cid)}"
            status_parts = st.split("；") if st else []
            self._row_name_fg = self.NPC_NAME_COLOR.get(cid)
            self._set_rank_row(i, left_text, status_parts, highlight=False)
            self._row_name_fg = None
            rr = i % rows_per_col
            cc = i // rows_per_col
            self.rank_rows[i]["frame"].grid(row=rr, column=cc, sticky="ew", padx=(0, 8) if cc == 0 else (8, 0), pady=1)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        joined = "\n".join(self._rewrite_names_in_line(x) for x in self.engine.log)
        self.log_text.insert(tk.END, joined)
        self.log_text.tag_configure("event_gold", foreground="#D4AF37", font=self.font_log)
        self.log_text.tag_configure("event_name_bold", foreground="#D4AF37", font=self.font_log_bold)
        start = "1.0"
        while True:
            pos = self.log_text.search("触发随机事件：", start, stopindex=tk.END)
            if not pos:
                break
            line_start = pos.split(".")[0] + ".0"
            line_end = pos.split(".")[0] + ".end"
            self.log_text.tag_add("event_gold", line_start, line_end)
            start = line_end
        # event_gold_refresh
        
        # Apply bold styling to all names and red styling to victims in the displayed log.
        for cid2 in self.engine.roles.keys():
            name2 = self._display_name(cid2)
            if not name2:
                continue
            search_from2 = "1.0"
            while True:
                pos2 = self.log_text.search(name2, search_from2, stopindex=tk.END)
                if not pos2:
                    break
                pos2_end = f"{pos2}+{len(name2)}c"
                self.log_text.tag_add("name_bold", pos2, pos2_end)
                search_from2 = pos2_end

        # Victim highlighting: parse each raw log line to find eliminated cid, then tag its (cleaned) display name red.
        raw_lines = list(self.engine.log)
        disp_lines = [self._clean_log_text(x) for x in raw_lines]
        # Build start indices of each displayed line in the Text widget
        line_start_idx = "1.0"
        for raw_line, disp_line in zip(raw_lines, disp_lines):
            victim_cid = self._parse_victim_cid(raw_line)
            if victim_cid is not None and victim_cid in self.engine.roles:
                token_v = self._display_name(victim_cid)
                if token_v:
                    # restrict search within this line only
                    end_idx = f"{line_start_idx} lineend"
                    search_from = line_start_idx
                    while True:
                        pos = self.log_text.search(token_v, search_from, stopindex=end_idx)
                        if not pos:
                            break
                        pos_end = f"{pos}+{len(token_v)}c"
                        self.log_text.tag_add("victim_red", pos, pos_end)
                        search_from = pos_end
            # advance to next line
            line_start_idx = f"{line_start_idx} +1line"

        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)

    def refresh(self):
        # Debounced refresh to avoid visible flicker when the UI updates rapidly.
        if getattr(self, "_refresh_scheduled", None):
            return
        self._refresh_scheduled = self.root.after_idle(self._do_refresh)

    def _do_refresh(self):
        self._refresh_scheduled = None
        try:
            self._refresh_impl()
        except Exception:
            import traceback
            traceback.print_exc()

def main():
    set_dpi_awareness()
    try:
        root = tk.Tk()
        try:
            ttk.Style().theme_use("clam")
        except Exception:
            pass
        UI(root)
# [patched for Streamlit]         root.mainloop()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            messagebox.showerror("Program crashed", tb)
        except Exception:
            print(tb)

if __name__ == "__main__":
    main()
