# -*- coding: utf-8 -*-
"""
神秘游戏 推演模拟器（Tkinter）
- 左侧：存活排名（占屏幕大部分）
- 右侧：滚动战报（第N回合开始、世界处决、谁放技能、谁击杀谁、死亡触发、更新等）
- 底部：新开局 / 下一回合

规则与技能以用户提供的“游戏规则推演提示词”为准（含：世界规则、补刀、护盾、封印/遗忘/遗策、双生、集火、挡刀等）。
"""

import tkinter.font as tkfont
import random
import re
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


# =========================
# 数据结构
# =========================

@dataclass
class Status:
    # 通用状态
    shields: int = 0                 # 护盾层数（最多2）
    shield_ttl: int = 0              # 临时护盾持续回合（>0每回合-1，到0清空临时盾；可持续盾用 shield_perm=层数）
    shield_perm: int = 0             # 可持续护盾层数（不随回合衰减，直到被消耗）
    thunder: int = 0                 # 雷霆层数（每回合第5/6/7名+1，叠满3立刻死亡）

    frost: bool = False             # 霜冻（由潘乐一施加；潘乐一死亡后清除）

    sealed: int = 0                  # 封印剩余回合（主动无效）
    forgotten: int = 0               # 遗忘剩余回合（主动无效）
    perma_disabled: bool = False     # 遗策/永久失效（主动+被动都无效）

    focused: bool = False            # 集火（本回合随机技能必中目标）
    dusk_mark: int = 0               # Sunny 死亡触发：黄昏标记（每次发动主动后-1名）
    next_target_random: bool = False # 留痕：下次技能目标随机
    doubled_move_next: bool = False  # 厄运预兆：下回合“排名变动效果”翻倍

    # 众议院挡刀
    guard_for: Optional[int] = None  # 本回合为谁挡刀
    guard_used: bool = False

    # 钟无艳特殊
    cant_gain_shield_next: int = 0   # 发动往事皆尘后：下回合无法获得护盾
    zhong_triggers: int = 0          # 巾帼护盾触发次数（最多3）
    lonely_pride: bool = False       # 孤傲标签（钟无艳）
    blessing: int = 0                # 找自称：祝福层数

    # mls
    mls_immune_used: int = 0         # 每局限3次
    mls_immune_used_this_turn: bool = False  # 每回合第一次受影响判定

    # 左右脑
    revives_left: int = 2            # 可复活两次

    # hewenx
    hewenx_curse: Optional[Dict[str, Any]] = None  # {"killer":cid, "threshold_rank":rank_at_death}

    # 施沁皓/姚宇涛联动等
    yao_substitute_used: bool = False

    # Sunny
    photosyn_energy: int = 0         # 光合能量（最多3）
    photosyn_watch: Optional[Dict[str, Any]] = None  # {"targets":[a,b,(c)], "remain":2}
    corrupted: bool = False          # 腐化（紫色显示）
    sunny_revive_used: bool = False  # Sunny【无中生有】是否已触发（每局一次）

    # 豆父：被动阶段
    father_world_boost_count: int = 0
    father_world_immune_used: bool = False

    def total_shields(self) -> int:
        return min(2, max(0, self.shield_perm) + max(0, self.shields))

    def brief(self) -> str:
        parts = []
        if self.total_shields() > 0:
            parts.append(f"护盾{self.total_shields()}")
        if self.thunder:
            parts.append(f"雷霆{self.thunder}")
        if self.frost:
            parts.append("霜冻")
        if self.sealed:
            parts.append(f"封印{self.sealed}")
        if self.forgotten:
            parts.append(f"遗忘{self.forgotten}")
        if self.focused:
            parts.append("集火")
        if self.perma_disabled:
            parts.append("遗策")
        if self.dusk_mark:
            parts.append(f"黄昏{self.dusk_mark}")
        if self.next_target_random:
            parts.append("留痕")
        if self.doubled_move_next:
            parts.append("厄运")
        if self.cant_gain_shield_next:
            parts.append("禁盾")
        if self.lonely_pride:
            parts.append("孤傲")
        if self.corrupted:
            parts.append("腐化")
        if self.blessing:
            parts.append(f"祝福{self.blessing}")
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
    killer: Optional[int]  # None 表示世界规则/未知
    reason: str


# =========================
# 引擎
# =========================

class Engine:
    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.turn = 0
        self.roles: Dict[int, Role] = {}
        self.rank: List[int] = []
        self.log: List[str] = []
        # 逐行回放（本回合每条log对应一个帧）
        self.replay_frames: List[Dict[str, Any]] = []
        self.replay_turn_id: int = 0
        self._cid_pat = re.compile(r"\((\d{1,2})\)")
        self.game_over = False

        # 全局
        self.no_death_streak = 0
        self.twin_pair: Tuple[int, int] = (13, -1)  # -1 表示当前未绑定
        self.deaths_this_turn: List[DeathRecord] = []
        self.start_rank_snapshot: Dict[int, int] = {}  # 用于钟无艳回合末“上升≥2”判断

        self._init_roles()
        self.new_game()

    def _init_roles(self):
        data = [
            (1,"金逸阳"),(2,"潘乐一"),(3,"施沁皓"),(4,"朱昊泽"),
            (5,"姚宇涛"),(6,"牵寒"),(7,"hewenx"),(8,"增进舒"),
            (9,"书法家"),(10,"mls"),(11,"豆进天"),(12,"放烟花"),
            (13,"藕禄"),(14,"郑孑健"),(15,"施博理"),(16,"合议庭"),
            (17,"路济阳"),(18,"更西部"),(19,"释延能"),(20,"豆进天之父"),
            (21,"钟无艳"),(22,"众议院"),(23,"梅雨神"),(24,"左右脑"),
            (25,"找自称"),(26,"Sunnydayorange"),
        ]
        self.roles = {cid: Role(cid, name) for cid, name in data}

    # ---------- 通用 ----------
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

    def N(self, cid: int) -> str:
        return f"{self.roles[cid].name}({cid})"

    def _snapshot(self) -> Dict[str, Any]:
        # 保存 UI 需要的快照：排名 + 每个角色的alive与brief状态
        alive_rank = [cid for cid in self.rank if self.roles[cid].alive]
        status_map = {}
        for cid, r in self.roles.items():
            status_map[cid] = {
                "alive": r.alive,
                "brief": r.status.brief(),
                "name": r.name
            }
        return {
            "turn": self.turn,
            "rank": alive_rank[:],
            "status": status_map
        }

    def _log(self, s: str):
        self.log.append(s)

        # 从日志文本里抓出所有出现过的 (cid)，用于“直播高亮”
        highlights = []
        try:
            for m in self._cid_pat.finditer(s):
                cid = int(m.group(1))
                if cid in self.roles:
                    highlights.append(cid)
        except Exception:
            highlights = []

        # 去重但保留顺序
        seen = set()
        highlights = [x for x in highlights if not (x in seen or seen.add(x))]

        # 每条日志记录一帧
        self.replay_frames.append({
            "text": s,
            "snap": self._snapshot(),
            "highlights": highlights
        })


    def _compact(self):
        self.rank = [cid for cid in self.rank if self.roles[cid].alive]

    def _max2_shield_add(self, st: Status, add: int, ttl: int = 1, perm: bool = False):
        # 护盾最多叠加2层
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
        if not r.alive:
            return
        if r.status.lonely_pride and note.startswith("增益"):
            # 钟无艳：无法成为任何增益技能目标
            self._log(f"  · {self.N(cid)} 因【孤傲】无法成为增益目标，未获得护盾")
            return
        if r.status.cant_gain_shield_next > 0:
            self._log(f"  · {self.N(cid)} 因【禁盾】无法获得护盾")
            return
        before = r.status.total_shields()
        self._max2_shield_add(r.status, n, ttl=ttl, perm=perm)
        after = r.status.total_shields()
        if after > before:
            self._log(f"  · {self.N(cid)} 获得护盾+{after-before}" + (f"（{note}）" if note else ""))

    def consume_shield_once(self, cid: int) -> bool:
        st = self.roles[cid].status
        # 优先消耗临时盾
        if st.shields > 0:
            st.shields -= 1
            return True
        if st.shield_perm > 0:
            st.shield_perm -= 1
            return True
        return False

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
        return True

    # ---------- 潘乐一：霜冻免疫（被动【大风机关】） ----------
    def frost_immune(self, source: Optional[int], target: int, effect_desc: str) -> bool:
        """若 target 为潘乐一(2)，且 source 携带霜冻，则潘乐一免疫该效果。"""
        if target != 2:
            return False
        if source is None:
            return False
        if source not in self.roles:
            return False
        if not self.roles[2].alive:
            return False
        # 潘乐一自身永久失效不影响被动免疫（如需受影响可改为检查 perma_disabled）
        if self.roles[source].alive and self.roles[source].status.frost:
            self._log(f"  · 大风机关：{self.N(2)} 免疫来自 {self.N(source)} 的效果（{effect_desc}）")
            return True
        return False



    # ---------- 双生 ----------
    def twin_partner(self, cid: int) -> Optional[int]:
        a, b = self.twin_pair
        # 未绑定：b == -1
        if b == -1:
            return None
        if cid == a:
            return b
        if cid == b:
            return a
        return None

    def twin_prob(self, cid: int) -> float:
        # 基础 75%；钟无艳孤傲：双生传导概率降至25%
        partner = self.twin_partner(cid)
        if partner is None:
            return 0.0
        if cid == 21 or partner == 21:
            return 0.25
        return 0.75

    def twin_share_nonkill(self, cid: int, kind: str):
        """
        双生：当一方受到技能影响（护盾/交换/位移/封印/遗忘等）时，另一方概率复制“部分效果”
        """
        partner = self.twin_partner(cid)
        if partner is None:
            return
        if partner not in self.roles:
            return
        if not self.roles[partner].alive:
            return

        p = self.twin_prob(cid)
        if self.rng.random() > p:
            self._log(f"  · 双生传导失败：{self.N(cid)} 未影响 {self.N(partner)}")
            return

        self._log(f"  · 双生传导成功：{self.N(cid)} → {self.N(partner)}（{kind}）")

        if kind == "gain_shield":
            self.give_shield(partner, 1, ttl=1, perm=False, note="双生复制护盾")
        elif kind in ("swap", "move"):
            d = self.rng.choice([-1, +1])
            self.move_by(partner, d, note="双生±1位移")
        elif kind == "seal":
            self.roles[partner].status.sealed = max(self.roles[partner].status.sealed, 1)
        elif kind == "forget":
            self.roles[partner].status.forgotten = max(self.roles[partner].status.forgotten, 1)

    def on_twin_death(self, dead: int):
        partner = self.twin_partner(dead)
        # 未绑定 or 不存在：直接跳过
        if partner is None:
            return
        if partner not in self.roles:
            return
        if self.roles[partner].alive:
            self._log(f"  · 双生死亡反馈：{self.N(partner)} 获得护盾1层")
            self.give_shield(partner, 1, ttl=1, perm=False, note="双生死亡反馈")


    # ---------- 排名操作 ----------
    def swap(self, a: int, b: int, note: str = ""):
        if not (self.roles[a].alive and self.roles[b].alive):
            return

        # 潘乐一(2) 被动【大风机关】：免疫霜冻携带者对其施加的交换效果
        if a == 2 and self.roles[b].status.frost:
            self._log(f"  · 大风机关：{self.N(2)} 免疫来自 {self.N(b)} 的交换效果")
            return
        if b == 2 and self.roles[a].status.frost:
            self._log(f"  · 大风机关：{self.N(2)} 免疫来自 {self.N(a)} 的交换效果")
            return

        pa, pb = self.pos(a), self.pos(b)
        if pa is None or pb is None:
            return
        self.rank[pa], self.rank[pb] = self.rank[pb], self.rank[pa]
        self._log(f"  · 交换：{self.N(a)} ⇄ {self.N(b)}" + (f"（{note}）" if note else ""))
        # 双生传导（交换属于技能影响）
        self.twin_share_nonkill(a, "swap")

    def move_by(self, cid: int, delta: int, note: str = ""):
        """
        delta<0 上升（更靠前），delta>0 下降
        翻倍规则：若该角色带 doubled_move_next，且本次属于“排名变动效果”，则翻倍一次并清除标记。
        """
        if not self.roles[cid].alive:
            return
        p = self.pos(cid)
        if p is None:
            return

        # 厄运翻倍只影响“排名变动效果数值”，工程化：move_by 一律视为排名变动效果
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
        self.twin_share_nonkill(cid, "move")

    def insert_rank(self, cid: int, new_rank: int, note: str = ""):
        if not self.roles[cid].alive:
            return
        p = self.pos(cid)
        if p is None:
            return
        new_rank = max(1, min(len(self.rank), new_rank))
        self.rank.pop(p)
        self.rank.insert(new_rank - 1, cid)
        self._log(f"  · 插入：{self.N(cid)} → 第{new_rank}名" + (f"（{note}）" if note else ""))

    # ---------- mls 被动 ----------
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
        self.move_by(10, -1, note="绝对领域+1")
        return True

    def is_mls_unselectable_by_active_kill(self, target: int) -> bool:
        # mls 绝对防御：无法被角色的主动斩杀选中（但可被世界规则处决）
        return target == 10

    # ---------- 众议院挡刀 ----------
    def find_guarder_for(self, victim: int) -> Optional[int]:
        for cid in self.alive_ids():
            st = self.roles[cid].status
            if st.guard_for == victim and not st.guard_used:
                return cid
        return None

    # ---------- 击杀 / 死亡 ----------
    def kill(self, victim, killer, reason,
         bypass_shield=False,
         bypass_guard=False,
         bypass_revive=False):
        """
        统一死亡入口：处理挡刀、护盾、左右脑复活、郑孑健护盾消耗触发、记录死亡顺序、双生死亡反馈等
        """
        if not self.roles[victim].alive:
            return False

        # 潘乐一(2) 被动【大风机关】：免疫霜冻携带者对其施加的效果
        if self.frost_immune(killer, victim, reason):
            return False


        # 挡刀
        if not bypass_guard:
            guarder = self.find_guarder_for(victim)
            if guarder is not None and guarder != victim:
                self.roles[guarder].status.guard_used = True
                self._log(f"  · 挡刀触发：{self.N(guarder)} 为 {self.N(victim)} 挡刀")
                # 挡刀者承受同一次死亡（通常也可被护盾）
                self.kill(guarder, killer, reason=f"挡刀代死（原目标{self.N(victim)}）", bypass_shield=bypass_shield, bypass_guard=True)
                return False

        # 护盾
        if not bypass_shield and self.roles[victim].status.total_shields() > 0:
            self.consume_shield_once(victim)
            self._log(f"  · 护盾抵死：{self.N(victim)}（{reason}）")
            # 郑孑健：每消耗一层护盾随机斩杀一人
            if victim == 14 and not self.roles[14].status.perma_disabled:
                self._log("  · 郑孑健(14) 坚韧之魂：消耗护盾后随机斩杀1人")
                pool = [x for x in self.alive_ids() if x != 14]
                if pool:
                    t = self.rng.choice(pool)
                    self.kill(t, 14, "坚韧之魂随机斩杀")
            return False

        # 左右脑复活（可被强制处决绕过）
        if (not bypass_revive) and victim == 24 and not self.roles[24].status.perma_disabled:
            st = self.roles[24].status
            if st.revives_left > 0:
                st.revives_left -= 1
                self._log(f"  · 左右脑(24) 双重生命：立即复活（剩余{st.revives_left}）")
                return False


        # 真死亡
        self.roles[victim].alive = False
        self.roles[victim].mem["dead_turn"] = self.turn   # ✅补：立刻记录死亡回合
        self.deaths_this_turn.append(DeathRecord(victim, killer, reason))
        # 找自称(25)：每有角色被击败，获得1层祝福；祝福满10层兑换1护盾并清空祝福
        if victim != 25 and self.roles[25].alive and not self.roles[25].status.perma_disabled:
            st25 = self.roles[25].status
            st25.blessing += 1
            self._log(f"  · 找自称(25) 获得祝福+1（现为{st25.blessing}层）")

            if st25.blessing >= 10:
                self._log("  · 找自称(25) 祝福叠满10层：兑换1层护盾，并清空祝福")
                self.give_shield(25, 1, ttl=1, perm=False, note="祝福兑换护盾")
                st25.blessing = 0
        if killer is None:
            self._log(f"  · 【死亡】{self.N(victim)}（{reason}）")
        else:
            self._log(f"  · 【击杀】{self.N(killer)} → {self.N(victim)}（{reason}）")
        # Sunny(26) 新规则：若被他人击败，则击败者获得【天命使然】→ 腐化
        if victim == 26 and killer is not None and killer in self.roles and self.roles[killer].alive:
            if not self.roles[killer].status.corrupted:
                self.roles[killer].status.corrupted = True
                self._log(f"  · 【天命使然】{self.N(killer)} 获得腐化")


        # 双生：一方死亡另一方得盾
        self.on_twin_death(victim)
        return True

    # =========================
    # 新开局 / 回合推进
    # =========================

    def new_game(self):
        self.turn = 0
        self.game_over = False
        self.no_death_streak = 0
        self.log = []
        self.deaths_this_turn = []

        # reset
        for r in self.roles.values():
            r.alive = True
            r.status = Status()
            r.mem = {}

        # 钟无艳孤傲标签
        self.roles[21].status.lonely_pride = True

        # 初始排名随机
        self.rank = list(self.roles.keys())
        self.rng.shuffle(self.rank)

        # 双生：藕禄(13) 随机绑定
        self.twin_pair = (13, -1)

        self._log("【新开局】已生成初始排名")

    def spread_corruption_and_check(self):
        """
        腐化机制：
        - 拥有腐化的角色，每回合把腐化传染给自己排名相邻的两人（左右各一）
        - 当所有存活角色都拥有腐化时：清除所有腐化，然后触发【无中生有】：
          Sunny(26) 若死亡且本局未触发过，则随机位置复活一次。
        """
        alive = self.alive_ids()
        if not alive:
            return

        # 1) 本回合腐化扩散（同时结算，避免链式一回合扩全场）
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
                self.roles[x].status.corrupted = True
            if newly:
                self._log("【腐化】扩散：" + "、".join(self.N(x) for x in newly))

        # 2) 检查是否“全场存活者都腐化”
        alive = self.alive_ids()
        if alive and all(self.roles[cid].status.corrupted for cid in alive):
            self._log("【腐化】全场腐化达成：清除所有腐化效果")
            for cid in self.roles:
                self.roles[cid].status.corrupted = False

            # 触发【无中生有】（每局一次）
            st26 = self.roles[26].status
            if (not st26.sunny_revive_used):
                st26.sunny_revive_used = True
                if not self.roles[26].alive:
                    self.roles[26].alive = True
                    # 随机位置插入（1..len(rank)+1）
                    self._compact()
                    pos = self.rng.randint(1, len(self.rank) + 1)
                    self.rank.insert(pos - 1, 26)
                    self._compact()
                    self._log(f"【无中生有】Sunnydayorange(26) 复活于随机位置：第{pos}名")
                else:
                    self._log("【无中生有】本应复活，但 Sunny 已存活 → 仅记录触发（每局一次）")

    def next_turn(self):
        if getattr(self, "game_over", False):
            self._log("【提示】本局已结束，请点击【新开局】重新开始。")
            return
        self.turn += 1
        self.replay_frames = []
        self.replay_turn_id += 1
        self._log("")
        self._log(f"========== 【第{self.turn}回合开始】 ==========")

        # 回合开始：记录起始排名，用于钟无艳回合末判定“上升≥2”
        self.start_rank_snapshot = {cid: self.rank_no(cid) for cid in self.alive_ids()}

        # 回合开始清理：mls 每回合免疫标记
        for cid in self.alive_ids():
            self.roles[cid].status.mls_immune_used_this_turn = False
            self.roles[cid].status.focused = False
            self.roles[cid].status.guard_for = None
            self.roles[cid].status.guard_used = False
            self.roles[cid].mem["judged_this_turn"] = False

        # hewenx怨念爆发：在“下回合行动前”结算
        self.apply_hewenx_curse_preaction()

        # 本回合死亡清空
        self.deaths_this_turn = []

        # 1 世界规则
        self.step_world_rule()

        # 2 主动技能
        self.step_active_skills()

        # 3 死亡触发
        self.step_death_triggers()
        
        # 4 更新状态
        self.step_update_and_cleanup()

        # ✅ 先更新连续无人死亡计数
        if len(self.deaths_this_turn) == 0:
            self.no_death_streak += 1
        else:
            self.no_death_streak = 0

        # ✅ 再判断补刀
        self.step_world_bonus()

        self._log(f"========== 【第{self.turn}回合结束】 存活{len(self.alive_ids())}人；连续无人死亡={self.no_death_streak} ==========")
        # ★ 终局兜底：防止僵死
        alive = self.alive_ids()
        if len(alive) <= 3 and self.no_death_streak >= 2:
            target = alive[-1]
            self._log(f"【终局补刀】强制处决末位 {self.N(target)}（防止僵死）")
            self.kill(target, None, "终局强制补刀", bypass_shield=True)
            self.step_death_triggers()
            self._compact()
        # ---------- 胜利判定 ----------
        alive = self.alive_ids()
        if len(alive) == 1:
            winner = alive[0]
            self._log(f"🏆【胜利】{self.N(winner)} 活到最后，获得胜利！")
            self.game_over = True

    # =========================
    # 步骤1：世界规则
    # =========================

    def step_world_rule(self):
        alive = self.alive_ids()
        if len(alive) < 4:
            self._log("【世界规则】存活人数不足4，不触发")
            return

        # =========================================================
        # ① 先处决第4名（你要求：位于添加雷霆效果之前）
        # =========================================================
        target4 = alive[3]
        self._log(f"【世界规则】处决第4名：{self.N(target4)}")


        # 豆进天之父：豆进天死亡后，免疫一次世界处决（每局一次）
        if target4 == 20 and (not self.roles[11].alive) and (not self.roles[20].status.perma_disabled):
            st = self.roles[20].status
            if not st.father_world_immune_used:
                st.father_world_immune_used = True
                self._log("  · 豆进天之父：被动免疫一次世界规则处决（每局一次）")
            else:
                self.kill(target4, None, "世界规则处决", bypass_shield=False)
        else:
            self.kill(target4, None, "世界规则处决", bypass_shield=False)
        # 豆父被动：世界规则处决时+1（最多3次）
        # 注意：这里的“处决时”你原逻辑是无论处决谁，只要发生过处决就给豆父+1
        if (not self.roles[11].alive) and self.roles[20].alive and (not self.roles[20].status.perma_disabled):
            st = self.roles[20].status
            if st.father_world_boost_count < 3:
                st.father_world_boost_count += 1
                self._log("  · 豆进天之父：被动触发（世界规则处决时排名+1，计数+1）")
                self.move_by(20, -1, note="父子同心(被动)+1")

        # 处决可能造成死亡，先压缩一下
        self._compact()
        alive = self.alive_ids()
        if not alive:
            return

        # =========================================================
        # ② 再结算雷霆（第5/6/7名获得雷霆层数，满3立刻死亡）
        # =========================================================
        thunder_targets = []
        for idx in (4, 5, 6):  # 0-based: 第5/6/7名
            if idx < len(alive):
                thunder_targets.append(alive[idx])

        if thunder_targets:
            self._log("【世界规则】雷霆降临：第5/6/7名获得一层雷霆")
            for t in thunder_targets:
                if not self.roles[t].alive:
                    continue
                st = self.roles[t].status
                st.thunder += 1
                self._log(f"  · {self.N(t)} 雷霆层数={st.thunder}")
                if st.thunder >= 3:
                    self._log(f"  · 雷霆满3：{self.N(t)} 立刻死亡")
                    # “立刻死亡”无视护盾/挡刀
                    self.kill(t, None, "雷霆叠满3层处决", bypass_shield=False, bypass_guard=True)


        # 雷霆也可能造成死亡，最后再压缩一次
        self._compact()


    # =========================
    # 步骤2：主动技能
    # =========================

    def step_active_skills(self):
        alive = self.alive_ids()
        if self.turn == 1:
            order = alive[:]
            self.rng.shuffle(order)
            self._log("【主动技能】第1回合随机顺序")
        else:
            order = sorted(alive)
            self._log("【主动技能】从第2回合起按序号执行")

        for cid in order:
            if not self.roles[cid].alive:
                continue

            # 黄昏标记：每次发动主动后-1名
            # 注意：如果技能无法发动（封印/遗忘/永久失效），不算发动
            if not self.can_act(cid):
                why = "遗策" if self.roles[cid].status.perma_disabled else ("封印" if self.roles[cid].status.sealed > 0 else "遗忘")
                self._log(f"  · {self.N(cid)} 无法发动（{why}）")
                continue

            # 合议庭审判：被审判者当回合技能无效 —— 我们用 mem["judged_this_turn"]=True，在其行动时拦截
            if self.roles[cid].mem.get("judged_this_turn"):
                self._log(f"  · {self.N(cid)} 本回合被审判：技能无效")
                continue

            self._log(f"【{cid}. {self.N(cid)}】发动主动技能…")
            self.dispatch_active(cid)

            # 发动后：黄昏标记惩罚
            if self.roles[cid].status.dusk_mark > 0:
                self._log(f"  · 黄昏标记：{self.N(cid)} 因发动主动，排名下降1位")
                self.move_by(cid, +1, note="黄昏标记惩罚")

    def dispatch_active(self, cid: int):
        fn = {
            1: self.act_1,
            2: self.act_2,
            3: self.act_3,
            4: self.act_4,
            5: self.act_5,
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
            22: self.act_22,
            23: self.act_23,
            24: self.act_24,
            25: self.act_25,
            26: self.act_26,
        }[cid]
        fn()

    # =========================
    # 步骤3：死亡触发技能
    # =========================

    def step_death_triggers(self):
        if not self.deaths_this_turn:
            self._log("【死亡触发】本回合无死亡")
            return
        self._log("【死亡触发】按死亡顺序处理：")
        # 注意：死亡触发按死亡顺序；死亡触发里可能再杀人/复活
        i = 0
        while i < len(self.deaths_this_turn):
            rec = self.deaths_this_turn[i]
            i += 1
            v = rec.victim
            if v == 2:
                self.on_death_2()
            elif v == 7:
                self.on_death_7(rec.killer)
            elif v == 9:
                self.on_death_9()
            elif v == 14:
                self.on_death_14(rec.killer)
            elif v == 23:
                self.on_death_23()
            elif v == 5:
                self.on_death_5()

    # =========================
    # 步骤4：更新/清理 + 补刀
    # =========================

    def step_update_and_cleanup(self):
        self._compact()
        self.spread_corruption_and_check()

        # 状态衰减
        for cid in self.alive_ids():
            st = self.roles[cid].status
            # 临时护盾持续回合-1，到0清空临时层
            if st.shield_ttl > 0:
                st.shield_ttl -= 1
                if st.shield_ttl == 0:
                    st.shields = 0

            if st.sealed > 0:
                st.sealed -= 1
            if st.forgotten > 0:
                st.forgotten -= 1
            if st.cant_gain_shield_next > 0:
                st.cant_gain_shield_next -= 1

            # 回合结束清除集火/挡刀设置
            st.focused = False
            st.guard_for = None
            st.guard_used = False

        # 钟无艳巾帼护盾：回合结束若排名上升≥2位，50%得1盾（不可叠加，最多3次）；持盾被集火盾立即消失
        self.endcheck_zhongwuyan()


        # 豆进天天命所归（被动）：若排名在后30%则立即升至第一并获得1盾(2回合)
        self.check_doujintian_passive()

        # 牵寒逆流而上（被动）：若排名在后40%免疫下次技能效果并排名+1
        # 工程化：给一个标记 "qian_immune_next" 作为“免疫下次技能影响”
        self.check_qianhan_passive()

        # 钟无艳“持盾被集火护盾消失”：集火在回合末已清，这里按规则（若回合中被集火且有盾）应该立即消失
        # 工程化：我们在“设置集火时”就处理掉钟无艳的盾（见 act_7）

    def step_world_bonus(self):
        """
        补刀机制：
        - 若连续两回合无人死亡，则从第三回合开始额外处决最后一名（与第4名同时处决）
        - 当存活≤3 且连续2回合无人死亡：末位强制处决（无视免疫）
        """
        alive = self.alive_ids()
        if not alive:
            return

        if len(alive) <= 3 and self.no_death_streak >= 2:
            target = alive[-1]
            self._log(f"【补刀】存活≤3且连续2回合无人死亡：强制处决末位 {self.N(target)}（无视免疫）")
            self.kill(
                target,
                None,
                "强制补刀",
                bypass_shield=True,
                bypass_guard=True,
                bypass_revive=True
            )
            self.step_death_triggers()
            self._compact()
            return

        if self.no_death_streak >= 2 and len(alive) >= 4:
            target = alive[-1]
            self._log(f"【补刀】连续两回合无人死亡：额外处决末位 {self.N(target)}")
            self.kill(target, None, "世界规则补刀处决", bypass_shield=False)
            self.step_death_triggers()
            self._compact()

    # =========================
    # 被动/回合末检查
    # =========================

    def check_doujintian_passive(self):
        if not self.roles[11].alive or self.roles[11].status.perma_disabled:
            return
        alive = self.alive_ids()
        r = self.rank_no(11)
        if r is None:
            return
        # 后30%：rank > 70%*N
        if r > int(len(alive) * 0.7):
            self._log(f"  · 豆进天(11) 天命所归触发：从后30%升至第一并获得护盾1层(2回合)")
            # 移到第1名
            self.insert_rank(11, 1, note="天命所归升至第一")
            # 护盾1层，持续2回合（工程化：作为临时盾ttl=2）
            self.give_shield(11, 1, ttl=2, perm=False, note="天命所归护盾")

    def check_qianhan_passive(self):
        if not self.roles[6].alive or self.roles[6].status.perma_disabled:
            return
        alive = self.alive_ids()
        r = self.rank_no(6)
        if r is None:
            return
        # 后40%：rank > 60%*N
        if r > int(len(alive) * 0.6):
            if not self.roles[6].mem.get("qian_immune_next", False):
                self.roles[6].mem["qian_immune_next"] = True
                self._log("  · 牵寒(6) 逆流而上触发：免疫下次技能影响并排名+1")
                self.move_by(6, -1, note="逆流而上+1")

                # 寒锋逆雪：当逆流触发时，额外斩杀随机高于自身一人
                higher = [x for x in self.alive_ids() if self.rank_no(x) is not None and self.rank_no(x) < self.rank_no(6)]
                if higher:
                    t = self.rng.choice(higher)
                    if not self.is_mls_unselectable_by_active_kill(t):
                        self._log(f"  · 寒锋逆雪：斩杀高位随机目标 {self.N(t)}")
                        self.kill(t, 6, "寒锋逆雪条件斩杀")
                    else:
                        self._log("  · 寒锋逆雪：随机到mls(10)，无法被主动斩杀选中 → 失败")

    def endcheck_zhongwuyan(self):
        if not self.roles[21].alive or self.roles[21].status.perma_disabled:
            return
        st = self.roles[21].status
        start = self.start_rank_snapshot.get(21)
        now = self.rank_no(21)
        if start is None or now is None:
            return
        rise = start - now
        if rise >= 2 and st.zhong_triggers < 3:
            if st.total_shields() == 0:
                if self.rng.random() < 0.5:
                    st.zhong_triggers += 1
                    self.give_shield(21, 1, ttl=1, perm=False, note="巾帼护盾判定")
            else:
                # 不可叠加
                pass


    # =========================
    # hewenx 怨念爆发：下回合行动前结算
    # =========================

    def apply_hewenx_curse_preaction(self):
        # 找到带有“hewenx_curse”的凶手，判断排名是否“高于阈值”（数字更小）
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
                self.kill(cid, 7, "怨念爆发斩杀(护盾无效)", bypass_shield=True)
            self.roles[cid].status.hewenx_curse = None
        # 若这里产生死亡，等同于“本回合开始前死亡”，不触发本回合死亡触发（你原文写的是下回合行动前斩杀；这里仍记在日志中，但不进入本回合 deaths_this_turn）
        self._compact()

    # =========================
    # 26人技能实现：主动
    # =========================

    # 1 金逸阳：逆袭之光(每3回合必发) + 光影裁决联动斩杀
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
        front = alive[:max(1, len(alive)//2)]
        target = self.rng.choice([x for x in front if x != 1])
        old_rank = myr
        self.swap(1, target, note="逆袭之光")
        # 光影裁决：斩杀交换前自身原排名位置的角色
        self._compact()
        if old_rank <= len(self.rank):
            v = self.rank[old_rank - 1]
            if v != 1:
                self._log(f"  · 光影裁决：斩杀原第{old_rank}名位置的 {self.N(v)}")
                self.kill(v, 1, "光影裁决联动斩杀")

    # 2 潘乐一：厄运预兆 + 死亡触发遗志诅咒
    def act_2(self):
        """潘乐一（2）
        主动【讲冷笑话】：
        - 每回合：对“已携带霜冻”的角色，额外使其排名下降1名
        - 并为与自己排名相邻的两人施加【霜冻】（浅蓝色）
        说明：霜冻为持续状态；潘乐一死亡后，全场霜冻清空（见 on_death_2）。
        """
        alive = self.alive_ids()
        if len(alive) <= 1:
            self._log("  · 讲冷笑话：场上人数不足")
            return

        # ① 先结算：已霜冻者每回合下降1名（不包含潘乐一自身）
        frosted = [cid for cid in alive if cid != 2 and self.roles[cid].status.frost]
        if frosted:
            self._log("  · 讲冷笑话：霜冻结算（已霜冻者本回合下降1名）")
            for t in frosted:
                self.move_by(t, +1, note="霜冻结算-1")

        # ② 再对相邻两人施加霜冻（本回合新获得霜冻不立刻触发下降）
        alive2 = self.alive_ids()
        p = self.pos(2)
        if p is None:
            return
        neigh = []
        if p - 1 >= 0:
            neigh.append(alive2[p - 1])
        if p + 1 < len(alive2):
            neigh.append(alive2[p + 1])

        if not neigh:
            self._log("  · 讲冷笑话：无相邻目标")
            return

        self._log("  · 讲冷笑话：为相邻目标施加霜冻")
        for t in neigh[:2]:
            if t == 2 or (not self.roles[t].alive):
                continue
            if not self.roles[t].status.frost:
                self.roles[t].status.frost = True
                self._log(f"    - {self.N(t)} 获得【霜冻】")
            else:
                self._log(f"    - {self.N(t)} 已有【霜冻】")


    # 3 施沁皓：凌空决（主动斩杀高位，姚宇涛免疫；失败则自身-2）
    def act_3(self):
        myr = self.rank_no(3)
        if myr is None:
            return
        higher = [x for x in self.alive_ids() if self.rank_no(x) is not None and self.rank_no(x) < myr]
        if not higher:
            self._log("  · 凌空决：无更高排名目标")
            return
        target = self.rng.choice(higher)
        if target == 5:
            self._log("  · 凌空决：姚宇涛免疫 → 失败，自身下降2位")
            self.move_by(3, +2, note="凌空决失败惩罚")
            return
        if self.is_mls_unselectable_by_active_kill(target):
            self._log("  · 凌空决：目标为mls(10)绝对防御不可选 → 失败，自身下降2位")
            self.move_by(3, +2, note="凌空决失败惩罚")
            return
        # 若牵寒免疫下次技能影响
        if target == 6 and self.roles[6].mem.get("qian_immune_next"):
            self.roles[6].mem["qian_immune_next"] = False
            self._log("  · 凌空决：牵寒免疫下次技能影响 → 斩杀无效；自身下降2位")
            self.move_by(3, +2, note="凌空决失败惩罚")
            return
        self._log(f"  · 凌空决：斩杀更高位目标 {self.N(target)}")
        died = self.kill(target, 3, "凌空决主动斩杀")
        if not died:
            self._log("  · 凌空决：斩杀被抵挡（护盾/挡刀），自身下降2位")
            self.move_by(3, +2, note="凌空决失败惩罚")

    # 4 朱昊泽：绝息斩（每回合斩杀后3随机一人；集火必中）
    def act_4(self):
        alive = self.alive_ids()
        if len(alive) <= 1:
            self._log("  · 绝息斩：目标不足")
            return
        last3 = alive[-3:] if len(alive) >= 3 else alive
        focus = [x for x in last3 if self.roles[x].status.focused]
        target = focus[0] if focus else self.rng.choice(last3)
        self._log(f"  · 绝息斩：目标 {self.N(target)}" + ("（集火必中）" if focus else ""))
        self.kill(target, 4, "绝息斩随机斩杀")

    # 5 姚宇涛：君临天下（连续两回合第一）+ 死亡被动王者替身
    def act_5(self):
        r = self.roles[5]
        # 冷却
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 君临天下：冷却中")
            return
        # 连续第一计数
        if self.rank_no(5) == 1:
            r.mem["streak"] = r.mem.get("streak", 0) + 1
        else:
            r.mem["streak"] = 0
        if r.mem.get("streak", 0) >= 2:
            alive = self.alive_ids()
            last = alive[-1]
            self._log(f"  · 君临天下：斩杀末位 {self.N(last)} 并打乱其他角色排名（冷却2）")
            self.kill(last, 5, "君临天下强制斩杀末位")
            # 打乱除自己外
            others = [x for x in self.alive_ids() if x != 5]
            self.rng.shuffle(others)
            self.rank = [5] + others
            r.mem["cd"] = 2
        else:
            self._log("  · 君临天下：条件不满足（需连续两回合第一）")

    # 6 牵寒：主动无；被动已在回合末处理（逆流而上、寒锋逆雪）
    def act_6(self):
        self._log("  · 无主动技能（被动在回合末判定）")

    # 7 hewenx：下位集火（指定集火；20%自集火）
    def act_7(self):
        alive = self.alive_ids()
        target = self.rng.choice([x for x in alive if x != 7])
        self.roles[target].status.focused = True
        self._log(f"  · 下位集火：{self.N(target)} 被集火")
        if self.rng.random() < 0.2:
            self.roles[7].status.focused = True
            self._log("  · 20%判定：hewenx也被集火")
        # 钟无艳：持盾被集火则护盾立即消失
        if target == 21 and self.roles[21].status.total_shields() > 0:
            self.roles[21].status.shields = 0
            self.roles[21].status.shield_perm = 0
            self.roles[21].status.shield_ttl = 0
            self._log("  · 钟无艳持盾被集火：护盾立即消失（孤傲规则）")

    # 8 增进舒：日进千里（+1/+2轮换）+ 乘胜追击（无盾才斩）
    def act_8(self):
        step = 1 if (self.turn % 2 == 1) else 2
        old = self.pos(8)
        self.move_by(8, -step, note=f"日进千里+{step}")
        # 联动：发动前紧邻后位
        if old is None:
            return
        alive_now = self.alive_ids()
        if old + 1 < len(alive_now):
            target = alive_now[old + 1]
            if self.roles[target].status.total_shields() == 0:
                self._log(f"  · 乘胜追击：斩杀 {self.N(target)}（目标无护盾）")
                self.kill(target, 8, "乘胜追击联动斩杀")
            else:
                self._log("  · 乘胜追击：目标有护盾，无法斩杀")

    # 9 书法家：笔定乾坤(一次封印两人下回合主动) + 笔戮千秋(每两回合斩低位)
    def act_9(self):
        r = self.roles[9]
        if not r.mem.get("seal_used", False):
            alive = self.alive_ids()
            cand = [x for x in alive if x != 9]
            if len(cand) >= 2:
                a, b = self.rng.sample(cand, 2)
                self.roles[a].status.sealed = max(self.roles[a].status.sealed, 1)
                self.roles[b].status.sealed = max(self.roles[b].status.sealed, 1)
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
        target = self.rng.choice(lower)
        if self.is_mls_unselectable_by_active_kill(target):
            self._log("  · 笔戮千秋：随机到mls(10)不可选 → 失败")
        else:
            self._log(f"  · 笔戮千秋：斩杀 {self.N(target)}")
            self.kill(target, 9, "笔戮千秋主动斩杀")
        r.mem["kill_cd"] = 1

    # 10 mls：无主动（被动在 mls_try_immune / 绝对防御在选中时处理）
    def act_10(self):
        self._log("  · 无主动技能（绝对领域为被动）")

    # 11 豆进天：无主动（被动回合末处理）
    def act_11(self):
        self._log("  · 无主动技能（天命所归为被动）")

    # 12 放烟花：万象挪移·改（每回合释放 turn 次；每次随机与1人交换）
    def act_12(self):
        times = max(1, self.turn)  # 第3回合=3次
        self._log(f"  · 万象挪移：本回合连续释放 {times} 次")

        for k in range(times):
            alive = self.alive_ids()
            cand = [x for x in alive if x != 12]
            if not cand:
                self._log("  · 万象挪移：无可交换目标，后续施放停止")
                return

            target = self.rng.choice(cand)

            # mls 被动免疫：若目标为mls则免疫并替换目标
            # 注意：mls每回合只会触发一次免疫（由 mls_try_immune 的 this_turn 标记控制）
            if target == 10 and self.mls_try_immune(10, f"放烟花交换（第{k+1}次）"):
                pool = [x for x in cand if x != 10]
                if pool:
                    target = self.rng.choice(pool)
                else:
                    self._log("  · 万象挪移：场上仅剩mls可选且其免疫触发 → 本次施放无效")
                    continue

            self._log(f"  · 万象挪移（第{k+1}次）：与 {self.N(target)} 交换")
            self.swap(12, target, note=f"万象挪移第{k+1}次交换")

        # ✅ 已移除：若上升得1临时盾 + 双生复制护盾

    # 13 藕禄：祸福双生（发动时才绑定一次；之后只提示已绑定）
    def act_13(self):
        # 发动时才进行一次双生绑定（只绑一次）
        a, b = self.twin_pair
        if b == -1:
            alive = [cid for cid in self.alive_ids() if cid != 13]
            if not alive:
                self._log("  · 祸福双生：场上无可绑定目标")
                return
            partner = self.rng.choice(alive)
            self.twin_pair = (13, partner)
            self._log(f"  · 祸福双生：本回合绑定双生：藕禄(13) ↔ {self.N(partner)}")
            return

        self._log("  · 祸福双生：已绑定（被动生效中）")

    # 14 郑孑健：无主动（护盾消耗斩人已在 kill 中；死亡复活在 on_death_14）
    def act_14(self):
        self._log("  · 无主动技能（坚韧/血债在被动与死亡触发）")

    # 15 施博理：高位清算（随机杀高位1，成功再杀1，上限2）
    def act_15(self):
        if self.roles[15].status.perma_disabled:
            self._log("  · 高位清算：永久失效，无法发动")
            return
        myr = self.rank_no(15)
        if myr is None or myr == 1:
            self._log("  · 高位清算：无高位目标")
            return
        higher = [x for x in self.alive_ids() if self.rank_no(x) is not None and self.rank_no(x) < myr]
        t1 = self.rng.choice(higher)
        if self.is_mls_unselectable_by_active_kill(t1):
            self._log("  · 高位清算：随机到mls(10)不可选 → 失败")
            return
        self._log(f"  · 高位清算：斩杀 {self.N(t1)}")
        died = self.kill(t1, 15, "高位清算第1杀")
        if died:
            higher2 = [x for x in self.alive_ids() if self.rank_no(x) is not None and self.rank_no(x) < self.rank_no(15)]
            if higher2:
                t2 = self.rng.choice(higher2)
                if not self.is_mls_unselectable_by_active_kill(t2):
                    self._log(f"  · 追加清算：斩杀 {self.N(t2)}")
                    self.kill(t2, 15, "高位清算第2杀")

    # 16 合议庭：众意审判（后60%触发：1与随机后60%交换；被审判者当回合技能无效）
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
        target = self.rng.choice([x for x in tail if x != first])
        self._log(f"  · 众意审判：强制 {self.N(first)} 与 {self.N(target)} 交换；{self.N(first)} 本回合技能无效")
        self.roles[first].mem["judged_this_turn"] = True
        self.swap(first, target, note="众意审判交换")

    # 17 路济阳：时空跃迁(每两回合) + 护佑之盾 + 时空斩击联动
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

        # 工程化：随机插入“空位”=选择一个插入排名位置 1..n
        new_rank = self.rng.randint(1, n)
        self._log(f"  · 时空跃迁：插入第{new_rank}名位置（工程化解释：随机选择插入排名）")
        if new_rank == 1 or new_rank == n:
            self._log("  · 时空跃迁：插入最前/最后 → 自身死亡")
            self.kill(17, None, "时空跃迁自杀", bypass_shield=False)
            r.mem["cd"] = 2
            return
        self.insert_rank(17, new_rank, note="时空跃迁")

        # 护佑之盾：名单内随机两人加可持续护盾（perm）
        whitelist = [17,14,16,7,6,20,11,19,22]
        cand = [x for x in whitelist if self.roles[x].alive]
        if len(cand) >= 2:
            a, b = self.rng.sample(cand, 2)
            self.give_shield(a, 1, perm=True, note="增益：护佑之盾(可持续)")
            self.give_shield(b, 1, perm=True, note="增益：护佑之盾(可持续)")

        # 时空斩击：若跃迁后自身排名下降，则随机斩杀跃迁前高于自己的角色
        nowr = self.rank_no(17)
        if oldr is not None and nowr is not None and nowr > oldr:
            higher_before = [x for x in alive if self.rank_no(x) is not None and self.rank_no(x) < oldr and x != 17]
            if higher_before:
                t = self.rng.choice(higher_before)
                if not self.is_mls_unselectable_by_active_kill(t):
                    self._log(f"  · 时空斩击：跃迁后下降，斩杀跃迁前高位 {self.N(t)}")
                    self.kill(t, 17, "时空斩击联动斩杀")
                else:
                    self._log("  · 时空斩击：随机到mls(10)不可选 → 失败")
        r.mem["cd"] = 2

    # 18 更西部：秩序颠覆(每两回合：1与随机后50%交换) + 末位放逐联动
    def act_18(self):
        r = self.roles[18]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 秩序颠覆：冷却中")
            return
        alive = self.alive_ids()
        first = alive[0]
        back = alive[len(alive)//2:]
        target = self.rng.choice([x for x in back if x != first])
        self._log(f"  · 秩序颠覆：交换 {self.N(first)} 与 {self.N(target)}")
        self.swap(first, target, note="秩序颠覆")
        # 末位放逐：当交换成功后，若自身排名>10且有护盾，则可消耗1盾斩杀被换下来的原第一
        myr = self.rank_no(18)
        if myr is not None and myr > 10 and self.roles[18].status.total_shields() > 0:
            self.consume_shield_once(18)
            self._log(f"  · 末位放逐：消耗1层护盾，斩杀原第一 {self.N(first)}")
            self.kill(first, 18, "末位放逐联动斩杀")
        r.mem["cd"] = 2

    # 19 释延能：万象随机（50%复制其他角色主动技能）
    def act_19(self):
        if self.rng.random() >= 0.5:
            self._log("  · 万象随机：50%判定失败，无事发生")
            return
        pool = [i for i in self.alive_ids() if i != 19]
        # 工程化：只复制“有主动函数”的角色（1..26都有函数，但部分是“无主动”）
        pick = self.rng.choice(pool)
        self._log(f"  · 万象随机：复制 {self.N(pick)} 的主动逻辑（以释延能触发）")
        # 工程化：直接调用对应角色的 act_XX（效果由“技能本身”决定）
        self.dispatch_active(pick)

    # 20 豆进天之父：父子同心·改（豆进天存活主动斩杀概率；豆进天死后被动见世界规则）
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
        t = self.rng.choice(lower)
        if self.is_mls_unselectable_by_active_kill(t):
            self._log("  · 父子同心：随机到mls(10)不可选 → 失败")
            return
        p = 0.50 + (son - myr) * 0.05
        p = max(0.0, min(0.80, p))
        if self.rng.random() <= p:
            self._log(f"  · 父子同心：成功率{int(p*100)}%判定成功，斩杀 {self.N(t)} 并与豆进天交换")
            self.kill(t, 20, "父子同心斩杀")
            if self.roles[11].alive:
                self.swap(20, 11, note="父子同心成功后交换")
        else:
            self._log(f"  · 父子同心：成功率{int(p*100)}%判定失败")

    # 21 钟无艳：往事皆尘（每3回合）遗忘1回合；下回合无法获得护盾（孤傲增益免疫已在 give_shield）
    def act_21(self):
        r = self.roles[21]
        r.mem["counter"] = r.mem.get("counter", 0) + 1
        if r.mem["counter"] % 3 != 0:
            self._log("  · 往事皆尘：计数未到（每3回合）")
            return
        alive = self.alive_ids()
        target = self.rng.choice([x for x in alive if x != 21])
        # 对已受遗忘/封印目标无效
        if self.roles[target].status.sealed > 0 or self.roles[target].status.forgotten > 0:
            self._log("  · 往事皆尘：目标已封印/遗忘，无效")
            return
        self.roles[target].status.forgotten = max(self.roles[target].status.forgotten, 1)
        self._log(f"  · 往事皆尘：{self.N(target)} 遗忘主动技能1回合")
        self.roles[21].status.cant_gain_shield_next = 1
        self.twin_share_nonkill(target, "forget")

    # 22 众议院：冷静客观（每两回合）挡刀一次 + 可立即交换
    def act_22(self):
        r = self.roles[22]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 冷静客观：冷却中")
            return
        alive = self.alive_ids()
        target = self.rng.choice([x for x in alive if x != 22])
        self.roles[22].status.guard_for = target
        self._log(f"  · 冷静客观：为 {self.N(target)} 挡刀一次，并立即交换")
        self.swap(22, target, note="冷静客观交换")
        r.mem["cd"] = 2

    # 23 梅雨神：久旱逢甘霖（每两回合）斩杀连续存活≥2回合角色；死亡复活“死亡超过3回合”的人
    def act_23(self):
        r = self.roles[23]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 久旱逢甘霖：冷却中")
            return
        # 工程化：用 mem["alive_turns"] 统计连续存活回合（在 step_update_and_cleanup 里不做；这里简化：turn>=2视为满足，且被杀后重置）
        cand = []
        for cid in self.alive_ids():
            if cid == 23:
                continue
            # 连续存活≥2：工程化：cid.mem["alive_turns"]>=2
            t = self.roles[cid].mem.get("alive_turns", 0)
            if t >= 2:
                cand.append(cid)
        if not cand:
            self._log("  · 久旱逢甘霖：无连续存活≥2目标")
            r.mem["cd"] = 2
            return
        target = self.rng.choice(cand)
        if self.is_mls_unselectable_by_active_kill(target):
            self._log("  · 久旱逢甘霖：随机到mls(10)不可选 → 失败")
        else:
            self._log(f"  · 久旱逢甘霖：斩杀 {self.N(target)}")
            self.kill(target, 23, "久旱逢甘霖随机斩杀")
        r.mem["cd"] = 2

    # 24 左右脑：混乱更换（每两回合）使两名其他角色互换（不含自己）
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
        self.swap(a, b, note="混乱更换")
        r.mem["cd"] = 2

    # 25 找自称：无主动技能（祝福为被动叠加）
    def act_25(self):
        self._log("  · 无主动技能（祝福为被动叠加）")


    # 26 Sunnydayorange：第4回合触发【自我放逐】（自己移除自己）
    def act_26(self):
        if self.turn == 4:
            self._log("  · 【自我放逐】：Sunnydayorange(26) 自己移除自己")
            # 自我放逐：视为死亡（无击败者），无视挡刀；护盾是否可挡你没写，这里按“直接移除”=护盾无效
            self.kill(26, None, "自我放逐", bypass_shield=True, bypass_guard=True)
        else:
            self._log("  · 无主动技能（仅第4回合触发【自我放逐】）")

    # 10/11/13/14 等无主动已实现；但还有缺的：6/10/11/13/14 已覆盖；18/23/24/26 已覆盖

    # =========================
    # 其他角色主动：补齐缺口（已覆盖所有cid 1..26）
    # 这里只剩：10/11/13/14 已是无主动
    # =========================

    # =========================
    # 死亡触发：2/5/7/9/14/23/26
    # =========================

    def on_death_2(self):
        # 潘乐一死亡：清空全场霜冻
        cleared = 0
        for cid, r in self.roles.items():
            if r.status.frost:
                r.status.frost = False
                cleared += 1
        if cleared > 0:
            self._log(f"  · 潘乐一(2) 被击败：全场【霜冻】效果消失（清除{cleared}个）")
        else:
            self._log("  · 潘乐一(2) 被击败：场上无霜冻可清除")


    def on_death_7(self, killer: Optional[int]):
        if killer is None:
            self._log("  · hewenx怨念爆发：无有效凶手")
            return
        if not self.roles.get(killer) or not self.roles[killer].alive:
            self._log("  · hewenx怨念爆发：凶手不存活/无效")
            return
        # 阈值：hewenx死亡时排名（工程化：取其在rank里当时的位置；死亡后已移除，所以用 start_rank_snapshot 或记录死前rank）
        threshold = self.start_rank_snapshot.get(7, 999)
        self.roles[killer].status.hewenx_curse = {"killer": killer, "threshold_rank": threshold}
        self._log(f"  · hewenx怨念爆发：标记凶手 {self.N(killer)}，下回合行动前若排名高于阈值则斩杀（护盾无效）")

    def on_death_9(self):
        # 墨守·改：遗策(随机一人永久失效) + 留痕(随机一人下次目标随机)
        alive = self.alive_ids()
        if not alive:
            return
        a = self.rng.choice(alive)
        self.roles[a].status.perma_disabled = True
        self._log(f"  · 遗策：{self.N(a)} 本局技能永久失效")
        alive2 = [x for x in self.alive_ids() if x != a]
        if alive2:
            b = self.rng.choice(alive2)
            self.roles[b].status.next_target_random = True
            self._log(f"  · 留痕：{self.N(b)} 下次技能目标变为随机")

    def on_death_14(self, killer: Optional[int]):
        # 血债血偿：死亡时复活并杀死凶手，取代其位置，获得护盾（每局一次）
        st = self.roles[14].status
        if st.perma_disabled:
            return
        if self.roles[14].mem.get("revive_used"):
            self._log("  · 血债血偿：已用过，本次不触发")
            return
        if killer is None or not self.roles.get(killer) or not self.roles[killer].alive:
            self._log("  · 血债血偿：无有效存活凶手，不触发")
            return
        self.roles[14].mem["revive_used"] = True

        # 复活
        self.roles[14].alive = True
        self._log(f"  · 血债血偿：{self.N(14)} 复活并杀死凶手 {self.N(killer)}，取代其位置并获得护盾")
        # 反杀凶手（无视护盾？原文没写无视，这里按普通斩杀，可被护盾挡；如需无视改 bypass_shield=True）
        self.kill(killer, 14, "血债血偿反杀凶手", bypass_shield=False)

        # 取代位置：工程化做法：把14插入到凶手原位置（若凶手没死则不替换）
        self._compact()
        pk = self.pos(killer)
        if pk is not None and not self.roles[killer].alive:
            # killer还在rank里但标死会被compact移除，这里尽力插到 pk+1
            self.rank.insert(min(pk, len(self.rank)), 14)
        self._compact()
        self.give_shield(14, 1, perm=True, note="血债血偿护盾(可持续)")

    def on_death_23(self):
        # 死亡时自动复活一个死亡状态超过三回合的角色
        # 工程化：用 role.mem["dead_turn"] 记录死亡回合，若当前turn - dead_turn > 3 可复活
        cand = []
        for cid, r in self.roles.items():
            if cid == 23:
                continue
            if not r.alive and ("dead_turn" in r.mem) and (self.turn - r.mem["dead_turn"] > 3):
                cand.append(cid)
        if cand:
            t = self.rng.choice(cand)
            self.roles[t].alive = True
            self._log(f"  · 梅雨神死亡被动：复活 {self.N(t)}（死亡超过3回合）")
            # 复活后放到中位
            self._compact()
            mid = max(1, len(self.rank)//2 + 1)
            self.rank.insert(mid-1, t)
            self._compact()

    def on_death_5(self):
        # 王者替身：死亡时，若施沁皓存活且有护盾，则死亡效果转移给施沁皓，姚宇涛复活升至第一（每局一次）
        st = self.roles[5].status
        if st.perma_disabled:
            return
        if st.yao_substitute_used:
            return
        if self.roles[3].alive and self.roles[3].status.total_shields() > 0:
            st.yao_substitute_used = True
            # 消耗施沁皓一层护盾并让其承受“死亡效果转移”（工程化：直接斩杀施沁皓一次，护盾可挡已满足有盾）
            self._log("  · 王者替身：满足条件，死亡效果转移给施沁皓(3)，姚宇涛复活并升至第一（每局一次）")
            self.kill(3, 5, "王者替身转移死亡")
            # 复活姚宇涛并置顶
            self.roles[5].alive = True
            self._compact()
            if 5 not in self.rank:
                self.rank.insert(0, 5)
            else:
                self.insert_rank(5, 1, note="王者替身置顶")

    # =========================
    # 每回合存活计数（给梅雨神/连续存活判定用）
    # =========================

    def tick_alive_turns(self):
        for cid, r in self.roles.items():
            if r.alive:
                r.mem["alive_turns"] = r.mem.get("alive_turns", 0) + 1
            else:
                if "dead_turn" not in r.mem:
                    r.mem["dead_turn"] = self.turn


# =========================
# UI
# =========================

class UI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("神秘游戏 made by dian_mi")
        self.root.geometry("1100x720")

        # --- 一定要初始化这些 ---
        self.engine = Engine(seed=None)

        self.rank_row_widgets = {}
        self.rank_rows = []          # 行池：[{frame,name_lbl,tags_frame}, ...]
        self.row_cid_map = {}        # cid -> 行控件(frame)，供高亮/清除用
        self.prev_highlights = set()

        self.play_cursor = 0
        self.playing = False
        self.speed_var = tk.DoubleVar(value=0.25)

        self.revealed_lines = []
        self.revealed_hls = []
        self.revealed_victims = []
        self.current_snap = None
        self.current_highlights = set()
        self._flash_job = None

        # 字体
        self.font_rank = tkfont.Font(family="Microsoft YaHei UI", size=15, weight="normal")
        self.font_log  = tkfont.Font(family="Microsoft YaHei UI", size=14, weight="normal")
        self.font_log_bold = tkfont.Font(family="Microsoft YaHei UI", size=14, weight="bold")

        self._cid_pat = re.compile(r"\((\d{1,2})\)")

        self.color_thunder = "#0B3D91"  # 深蓝：雷霆
        self.color_frost   = "#7EC8FF"  # 浅蓝：霜冻
        self.color_pos     = "#D4AF37"
        self.color_neg     = "#E53935"
        self.color_purple  = "#8E44AD"
        self.pos_keywords = ("护盾", "祝福")
        self.neg_keywords = ("雷霆", "霜冻", "封印", "遗忘", "遗策", "黄昏", "留痕", "厄运", "禁盾", "集火", "孤傲")

        # --- 关键：必须 build + refresh ---
        self._build()
        self.refresh()

    def _set_game_over_buttons(self):
        # 结束局：禁止继续推进/播放，只留新开局
        try:
            self.btn_turn.config(state="disabled")
            self.btn_step.config(state="disabled")
            self.btn_auto.config(state="disabled")
            self.btn_pause.config(state="disabled")
        except Exception:
            pass


    def _set_rank_row(self, idx: int, left_text: str, status_parts: List[str], highlight: bool):
        bg = "#FFF2A8" if highlight else self.root.cget("bg")
        row = self.rank_rows[idx]["frame"]
        name_lbl = self.rank_rows[idx]["name"]
        tags_frame = self.rank_rows[idx]["tags"]

        row.configure(bg=bg)
        name_lbl.configure(text=left_text, bg=bg)

        # 清掉旧标签（只清标签，不销毁整行）
        for w in tags_frame.winfo_children():
            w.destroy()
        tags_frame.configure(bg=bg)

        for part in status_parts:
            part = part.strip()
            if not part:
                continue

            if part.startswith("雷霆"):
                fg = self.color_thunder
            elif part.startswith("霜冻"):
                fg = self.color_frost
            elif part.startswith("腐化"):
                fg = self.color_purple
            elif part.startswith(self.pos_keywords):
                fg = self.color_pos
            else:
                fg = self.color_neg

            tk.Label(tags_frame, text=f" {part} ", font=self.font_rank, fg=fg, bg=bg).pack(side="left", padx=2)

    def show_help(self):
        win = tk.Toplevel(self.root)
        win.title("游戏说明")
        win.geometry("700x500")

        text = tk.Text(win, wrap="word", font=("Microsoft YaHei UI", 12))
        text.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(win, command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.config(yscrollcommand=scrollbar.set)

        help_text = """
made by dian_mi
但是其实基本都是ChatGPT写的
欢迎大家游玩 
    """

        text.insert("1.0", help_text)
        text.config(state="disabled")


    def _build(self):
        self.main = ttk.Frame(self.root, padding=8)
        self.main.pack(fill=tk.BOTH, expand=True)

        self.main.columnconfigure(0, weight=3)
        self.main.columnconfigure(1, weight=2)
        self.main.rowconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=0)

        # 左：排名（单栏，大）
        self.left = ttk.Frame(self.main)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.left.columnconfigure(0, weight=1)
        self.left.rowconfigure(0, weight=1)

        # 单栏容器
        self.rank_frame = ttk.Frame(self.left)
        self.rank_frame.grid_columnconfigure(0, weight=1)

        # 预建最多26行，避免每次destroy重建导致闪跳
        for i in range(26):
            row = tk.Frame(self.rank_frame, bg=self.root.cget("bg"))
            row.grid(row=i, column=0, sticky="ew", pady=2)

            name_lbl = tk.Label(row, text="", anchor="w", font=self.font_rank, bg=self.root.cget("bg"))
            name_lbl.pack(side="left")

            tags_frame = tk.Frame(row, bg=self.root.cget("bg"))
            tags_frame.pack(side="left", padx=6)

            self.rank_rows.append({"frame": row, "name": name_lbl, "tags": tags_frame})
        self.rank_frame.grid(row=0, column=0, sticky="nsew")

        # 右：日志
        self.right = ttk.Frame(self.main)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.rowconfigure(0, weight=1)
        self.right.columnconfigure(0, weight=1)

        self.log_text = tk.Text(self.right, wrap="word", font=self.font_log)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.right, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.configure(state="disabled")

        # 底部按钮
        self.bottom = ttk.Frame(self.main)
        self.bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.bottom.columnconfigure(0, weight=1)


        # 左下角（用 grid 体系，避免 pack/grid 混用导致布局/闪退）
        left_box = ttk.Frame(self.bottom)
        left_box.grid(row=0, column=0, sticky="w")

        ttk.Button(left_box, text="说明", command=self.show_help).pack(side="left", padx=8)
        ttk.Button(left_box, text="新开局", command=self.on_new).pack(side="left", padx=8)



        self.btn_turn = ttk.Button(self.bottom, text="下一回合", command=self.on_build_turn)
        self.btn_turn.grid(row=0, column=1, padx=8)

        self.btn_step = ttk.Button(self.bottom, text="下一行", command=self.on_step_line)
        self.btn_step.grid(row=0, column=2, padx=8)

        self.btn_auto = ttk.Button(self.bottom, text="自动播放", command=self.on_auto_play)
        self.btn_auto.grid(row=0, column=3, padx=8)

        self.btn_pause = ttk.Button(self.bottom, text="暂停", command=self.on_pause)
        self.btn_pause.grid(row=0, column=4, padx=8)
        # 速度控制：0.1s ~ 2.0s
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

    def _render_rank_row(self, parent, text_left: str, status_parts: List[str], highlight: bool):
        row_bg = "#FFF2A8" if highlight else self.root.cget("bg")
        row = tk.Frame(parent, bg=row_bg)
        row.pack(fill="x", pady=2)

        name_lbl = tk.Label(row, text=text_left, anchor="w", font=self.font_rank, bg=row_bg)
        name_lbl.pack(side="left")

        tag_labels = []
        for part in status_parts:
            part = part.strip()
            if not part:
                continue

            if part.startswith("雷霆"):
                fg = self.color_thunder
            elif part.startswith("腐化"):
                fg = self.color_purple
            elif part.startswith(self.pos_keywords):
                fg = self.color_pos
            else:
                fg = self.color_neg

            tag = tk.Label(row, text=f" {part} ", font=self.font_rank, fg=fg, bg=row_bg)
            tag.pack(side="left", padx=2)
            tag_labels.append(tag)

        return row, name_lbl, tag_labels

    def on_new(self):
        self.engine.new_game()
        self.play_cursor = 0
        self.playing = False
        self.revealed_lines = []
        self.revealed_hls = []
        self.revealed_victims = []
        self.current_snap = None
        self.refresh()
        try:
            self.btn_turn.config(state="normal")
            self.btn_step.config(state="normal")
            self.btn_auto.config(state="normal")
            self.btn_pause.config(state="normal")
        except Exception:
            pass

    def on_build_turn(self):
        # 先结算一整回合，但不直接展示整回合结果
        self.engine.tick_alive_turns()
        self.engine.next_turn()



        self.play_cursor = 0
        self.playing = False
        self.revealed_lines = []
        self.revealed_hls = []
        self.revealed_victims = []
        self.current_snap = None

        # 默认先显示第一行，然后自动播放剩余行
        if self.engine.replay_frames:
            self.on_step_line()      # 显示第1行
            self.playing = True      # 开启播放
            self.on_step_line()      # 继续播放下一行（等同于自动播放）
        else:
            self.refresh()

    def on_step_line(self):
        frames = self.engine.replay_frames

        # 已经播完：此时如果 game_over，再禁用按钮
        if self.play_cursor >= len(frames):
            self.playing = False
            if getattr(self.engine, "game_over", False):
                self._set_game_over_buttons()
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
            self.root.after(delay_ms, self.on_step_line)


    def on_auto_play(self):
        if not self.engine.replay_frames:
            return
        self.playing = True
        self.on_step_line()

    def on_pause(self):
        self.playing = False

    def _parse_victim_cid(self, line: str) -> Optional[int]:
        # 死亡行："【死亡】名字(cid)..."
        if "【死亡】" in line:
            m = self._cid_pat.search(line)
            return int(m.group(1)) if m else None

        # 击杀行："【击杀】凶手(...) → 受害者(cid)..."
        if "【击杀】" in line:
            ids = [int(m.group(1)) for m in self._cid_pat.finditer(line)]
            if len(ids) >= 2:
                return ids[1]  # 第二个(cid)是受害者
            return None

        return None
        
    def _update_speed_label(self):
        try:
            v = float(self.speed_var.get())
        except Exception:
            v = 0.25
        self.speed_label.config(text=f"{v:.2f}s/行")


    def _clear_flash(self):
        self._flash_job = None
        if not self.current_snap:
            return

        # 把当前高亮的行恢复背景
        normal_bg = self.root.cget("bg")
        for cid in list(self.prev_highlights):
            row = self.row_cid_map.get(cid)
            if row:
                row.configure(bg=normal_bg)
                # 子控件也要一起改，否则里面label背景不变会“花”
                for child in row.winfo_children():
                    try:
                        child.configure(bg=normal_bg)
                    except Exception:
                        pass

        self.prev_highlights = set()

        snap = self.current_snap
        rank = snap["rank"]
        status_map = snap["status"]

        # 重建左侧，但不做高亮色
        for w in self.rank_frame.winfo_children():
            w.destroy()

        self.rank_row_widgets = {}  # cid -> row(Frame)

        for i, cid in enumerate(rank, start=1):
            info = status_map[cid]
            st = info["brief"]
            left_text = f"{i:>2}. {info['name']}({cid})"
            status_parts = st.split("；") if st else []

            # 注意：_render_rank_row 返回 (row, name_lbl, tag_labels)
            row, name_lbl, tag_labels = self._render_rank_row(
                self.rank_frame, left_text, status_parts, highlight=False
            )
            self.rank_row_widgets[cid] = row

        # 右侧日志照常渲染
        self.render_log_with_current_highlight(self.revealed_lines, self.revealed_hls)

    def refresh_replay_view_no_flash(self):
        snap = self.current_snap
        if not snap:
            self.refresh()
            return

        rank = snap["rank"]
        status_map = snap["status"]

        # 重新建立 cid -> 行frame 映射（供高亮用）
        self.row_cid_map = {}

        normal_bg = self.root.cget("bg")

        # 先把26行都“清空/隐藏内容”（但不destroy）
        for i in range(26):
            row = self.rank_rows[i]["frame"]
            name_lbl = self.rank_rows[i]["name"]
            tags_frame = self.rank_rows[i]["tags"]

            row.configure(bg=normal_bg)
            name_lbl.configure(text="", bg=normal_bg)

            for w in tags_frame.winfo_children():
                w.destroy()
            tags_frame.configure(bg=normal_bg)

        # 再填充存活排名
        for i, cid in enumerate(rank):
            info = status_map[cid]
            st = info["brief"]
            left_text = f"{i+1:>2}. {info['name']}({cid})"
            status_parts = st.split("；") if st else []

            self._set_rank_row(i, left_text, status_parts, highlight=False)
            self.row_cid_map[cid] = self.rank_rows[i]["frame"]

        # 右侧日志照常渲染
        self.render_log_with_current_highlight(self.revealed_lines, self.revealed_hls)

    def refresh_replay_view(self):
        snap = self.current_snap
        if not snap:
            self.refresh()
            return

        rank = snap["rank"]
        status_map = snap["status"]

        # 重新建立 cid -> 行frame 映射（供高亮用）
        self.row_cid_map = {}

        normal_bg = self.root.cget("bg")

        # 先把26行都清空（不destroy）
        for i in range(26):
            row = self.rank_rows[i]["frame"]
            name_lbl = self.rank_rows[i]["name"]
            tags_frame = self.rank_rows[i]["tags"]

            row.configure(bg=normal_bg)
            name_lbl.configure(text="", bg=normal_bg)

            for w in tags_frame.winfo_children():
                w.destroy()
            tags_frame.configure(bg=normal_bg)

        # 填充存活排名 + 高亮当前行涉及角色
        for i, cid in enumerate(rank):
            info = status_map[cid]
            st = info["brief"]
            left_text = f"{i+1:>2}. {info['name']}({cid})"
            status_parts = st.split("；") if st else []

            highlight = (cid in self.current_highlights)
            self._set_rank_row(i, left_text, status_parts, highlight=highlight)
            self.row_cid_map[cid] = self.rank_rows[i]["frame"]

        # 右侧日志渲染（最后一行加粗、死亡红名）
        self.render_log_with_current_highlight(self.revealed_lines, self.revealed_hls)


    def render_log_with_current_highlight(self, lines: List[str], hls: List[List[int]]):
        """
        - 所有行：若该行是【死亡】或【击杀】，则“被击败者名字(cid)”标红
        - 当前行（最后一行）：该行涉及的角色名(cid)加粗（直播感）
        """
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)

        # tag 配置（重复配置无害）
        self.log_text.tag_configure("hl_current", font=self.font_log_bold)
        self.log_text.tag_configure("victim_red", foreground="red")

        last_i = len(lines) - 1

        for i, line in enumerate(lines):
            start_idx = self.log_text.index(tk.INSERT)
            self.log_text.insert(tk.END, line + "\n")
            end_idx = self.log_text.index(tk.INSERT)

            # 1) 红名：被击败者
            victim_cid = None
            if i < len(self.revealed_victims):
                victim_cid = self.revealed_victims[i]
            if victim_cid is not None and victim_cid in self.engine.roles:
                token_v = f"{self.engine.roles[victim_cid].name}({victim_cid})"
                search_from = start_idx
                while True:
                    pos = self.log_text.search(token_v, search_from, stopindex=end_idx)
                    if not pos:
                        break
                    pos_end = f"{pos}+{len(token_v)}c"
                    self.log_text.tag_add("victim_red", pos, pos_end)
                    search_from = pos_end

            # 2) 当前行加粗：涉及角色
            if i == last_i and i < len(hls):
                for cid in hls[i]:
                    if cid not in self.engine.roles:
                        continue
                    token = f"{self.engine.roles[cid].name}({cid})"
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

    def on_next(self):
        # 回合推进前：更新连续存活/死亡回合计数（给梅雨神等使用）
        self.engine.tick_alive_turns()
        self.engine.next_turn()
        self.refresh()

    def refresh(self):
        # 使用“行池”，不要 destroy 预建的 26 行
        normal_bg = self.root.cget("bg")

        # 先清空26行显示
        for i in range(26):
            row = self.rank_rows[i]["frame"]
            name_lbl = self.rank_rows[i]["name"]
            tags_frame = self.rank_rows[i]["tags"]

            row.configure(bg=normal_bg)
            name_lbl.configure(text="", bg=normal_bg)

            for w in tags_frame.winfo_children():
                w.destroy()
            tags_frame.configure(bg=normal_bg)

        # 再填充存活排名
        alive = self.engine.alive_ids()
        self.row_cid_map = {}

        for i, cid in enumerate(alive):
            r = self.engine.roles[cid]
            st = r.status.brief()
            left_text = f"{i+1:>2}. {r.name}({cid})"
            status_parts = st.split("；") if st else []

            self._set_rank_row(i, left_text, status_parts, highlight=False)
            self.row_cid_map[cid] = self.rank_rows[i]["frame"]

        # 右侧日志（全量显示）
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "\n".join(self.engine.log))
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    UI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
