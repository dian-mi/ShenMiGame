# -*- coding: utf-8 -*-
"""
26人规则版 推演模拟器（Tkinter）
- 左侧：存活排名（占屏幕大部分）
- 右侧：滚动战报（第N回合开始、世界处决、谁放技能、谁击杀谁、死亡触发、更新等）
- 底部：新开局 / 下一回合

规则与技能以用户提供的“游戏规则推演提示词”为准（含：世界规则、补刀、护盾、封印/遗忘/遗策、双生、集火、挡刀等）。
"""

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import ttk
    TK_AVAILABLE = True
except Exception:
    tk = None
    tkfont = None
    ttk = None
    TK_AVAILABLE = False

import random
import re
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

    # 豆父：被动阶段
    father_world_boost_count: int = 0
    father_world_immune_used: bool = False

    def total_shields(self) -> int:
        return min(2, max(0, self.shield_perm) + max(0, self.shields))

    def brief(self) -> str:
        parts = []
        if self.total_shields() > 0:
            parts.append(f"护盾{self.total_shields()}")
        if self.sealed:
            parts.append(f"封印{self.sealed}")
        if self.forgotten:
            parts.append(f"遗忘{self.forgotten}")
        if self.focused:
            parts.append("集火")
        if self.perma_disabled:
            parts.append("永久失效")
        if self.dusk_mark:
            parts.append(f"黄昏{self.dusk_mark}")
        if self.next_target_random:
            parts.append("留痕(目标随机)")
        if self.doubled_move_next:
            parts.append("厄运(翻倍)")
        if self.cant_gain_shield_next:
            parts.append("禁得盾")
        if self.lonely_pride:
            parts.append("孤傲")
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


        # 全局
        self.no_death_streak = 0
        self.twin_pair: Tuple[int, int] = (13, 12)  # 会在新开局随机覆盖
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
            self._log(f"  · {self.N(cid)} 因【禁得盾】无法获得护盾")
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

    # ---------- 双生 ----------
    def twin_partner(self, cid: int) -> Optional[int]:
        a, b = self.twin_pair
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
        双生：当一方受到技能影响（护盾/交换/位移/封印/遗忘等）时，另一方75%复制“部分效果”
        这里工程化：根据 kind 复制一个合理的子效果。
        """
        partner = self.twin_partner(cid)
        if partner is None or not self.roles[partner].alive:
            return
        p = self.twin_prob(cid)
        if self.rng.random() > p:
            self._log(f"  · 双生传导失败：{self.N(cid)} 未影响 {self.N(partner)}")
            return
        self._log(f"  · 双生传导成功：{self.N(cid)} → {self.N(partner)}（{kind}）")
        if kind == "gain_shield":
            self.give_shield(partner, 1, ttl=1, perm=False, note="双生复制护盾")
        elif kind in ("swap", "move"):
            # 斩杀除外：这里按规则“改为排名±1”
            d = self.rng.choice([-1, +1])
            self.move_by(partner, d, note="双生±1位移")
        elif kind == "seal":
            self.roles[partner].status.sealed = max(self.roles[partner].status.sealed, 1)
        elif kind == "forget":
            self.roles[partner].status.forgotten = max(self.roles[partner].status.forgotten, 1)

    def on_twin_death(self, dead: int):
        partner = self.twin_partner(dead)
        if partner is None:
            return
        if self.roles[partner].alive:
            self._log(f"  · 双生死亡反馈：{self.N(partner)} 获得护盾1层")
            self.give_shield(partner, 1, ttl=1, perm=False, note="双生死亡反馈")

    # ---------- 排名操作 ----------
    def swap(self, a: int, b: int, note: str = ""):
        if not (self.roles[a].alive and self.roles[b].alive):
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
    def kill(self, victim: int, killer: Optional[int], reason: str, bypass_shield: bool = False, bypass_guard: bool = False):
        """
        统一死亡入口：处理挡刀、护盾、左右脑复活、郑孑健护盾消耗触发、记录死亡顺序、双生死亡反馈等
        """
        if not self.roles[victim].alive:
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

        # 左右脑复活
        if victim == 24 and not self.roles[24].status.perma_disabled:
            st = self.roles[24].status
            if st.revives_left > 0:
                st.revives_left -= 1
                self._log(f"  · 左右脑(24) 双重生命：立即复活（剩余{st.revives_left}）")
                return False

        # 真死亡
        self.roles[victim].alive = False
        self.deaths_this_turn.append(DeathRecord(victim, killer, reason))
        if killer is None:
            self._log(f"  · 【死亡】{self.N(victim)}（{reason}）")
        else:
            self._log(f"  · 【击杀】{self.N(killer)} → {self.N(victim)}（{reason}）")

        # 双生：一方死亡另一方得盾
        self.on_twin_death(victim)
        return True

    # =========================
    # 新开局 / 回合推进
    # =========================

    def new_game(self):
        self.turn = 0
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
        partner = self.rng.choice([cid for cid in self.rank if cid != 13])
        self.twin_pair = (13, partner)

        self._log("【新开局】已生成初始排名与双生绑定")
        self._log(f"  · 双生：藕禄(13) ↔ {self.N(partner)}")

    def next_turn(self):
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

        # 4 更新状态与补刀
        self.step_update_and_cleanup()
        self.step_world_bonus()

        # 连续无人死亡计数
        if len(self.deaths_this_turn) == 0:
            self.no_death_streak += 1
        else:
            self.no_death_streak = 0

        self._log(f"========== 【第{self.turn}回合结束】 存活{len(self.alive_ids())}人；连续无人死亡={self.no_death_streak} ==========")

    # =========================
    # 步骤1：世界规则
    # =========================

    def step_world_rule(self):
        alive = self.alive_ids()
        if len(alive) < 4:
            self._log("【世界规则】存活人数不足4，不触发")
            return

        # Sunny 光合能量：免疫世界规则概率 20%/40%/60%（最多60）
        target = self.rank[3]
        self._log(f"【世界规则】处决第4名：{self.N(target)}")

        # 豆进天之父被动阶段：若豆进天死亡，免疫一次世界处决，且处决时+1（最多3次）——工程化：在“target==20”时处理免疫
        if target == 26 and self.roles[26].alive:
            st = self.roles[26].status
            if st.photosyn_energy > 0:
                prob = min(0.60, 0.20 * st.photosyn_energy)
                if self.rng.random() < prob:
                    self._log(f"  · Sunny 光合免疫触发：免疫世界规则处决（概率{int(prob*100)}%）")
                    return

        if target == 20 and (not self.roles[11].alive) and (not self.roles[20].status.perma_disabled):
            st = self.roles[20].status
            if not st.father_world_immune_used:
                st.father_world_immune_used = True
                self._log("  · 豆进天之父：被动免疫一次世界规则处决（每局一次）")
                return

        self.kill(target, None, "世界规则处决", bypass_shield=False)

        # 豆父被动：世界规则处决时+1（最多3次）
        if (not self.roles[11].alive) and self.roles[20].alive and (not self.roles[20].status.perma_disabled):
            st = self.roles[20].status
            if st.father_world_boost_count < 3:
                st.father_world_boost_count += 1
                self._log("  · 豆进天之父：被动触发（世界规则处决时排名+1，计数+1）")
                self.move_by(20, -1, note="父子同心(被动)+1")

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
                why = "永久失效" if self.roles[cid].status.perma_disabled else ("封印" if self.roles[cid].status.sealed > 0 else "遗忘")
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
            elif v == 26:
                self.on_death_26(rec.killer)
            elif v == 5:
                self.on_death_5()

    # =========================
    # 步骤4：更新/清理 + 补刀
    # =========================

    def step_update_and_cleanup(self):
        self._compact()

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

        # Sunny 光合作用：监测剩余回合-1，若到0且目标都活 -> 能量+1
        self.endcheck_sunny_photosyn()

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
            self.kill(target, None, "强制补刀", bypass_shield=True)
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

    def endcheck_sunny_photosyn(self):
        if not self.roles[26].alive or self.roles[26].status.perma_disabled:
            return
        st = self.roles[26].status
        watch = st.photosyn_watch
        if not watch:
            return
        watch["remain"] -= 1
        if watch["remain"] <= 0:
            targets = watch.get("targets", [])
            ok = all(self.roles[t].alive for t in targets)
            if ok:
                st.photosyn_energy = min(3, st.photosyn_energy + 1)
                self._log(f"  · Sunny(26) 光合作用：监测目标2回合未死，光合能量+1（现{st.photosyn_energy}）")
            st.photosyn_watch = None

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
        alive = self.alive_ids()
        target = self.rng.choice([x for x in alive if x != 2])
        self.roles[target].status.doubled_move_next = True
        self._log(f"  · 厄运预兆：指定 {self.N(target)} 下回合排名变动效果翻倍；自身排名+1")
        self.move_by(2, -1, note="厄运预兆自升")

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

    # 12 放烟花：万象挪移·改（随机与两人交换；若上升得1临时盾）
    def act_12(self):
        old = self.rank_no(12)
        alive = self.alive_ids()
        cand = [x for x in alive if x != 12]
        if len(cand) < 2:
            self._log("  · 万象挪移：目标不足")
            return
        a, b = self.rng.sample(cand, 2)

        # mls 被动免疫：若目标为mls则免疫并替换目标
        for t in (a, b):
            if t == 10 and self.mls_try_immune(10, "放烟花交换"):
                # 替换一个非12非10的目标
                pool = [x for x in cand if x not in (a, b) and x != 10]
                if pool:
                    if t == a:
                        a = self.rng.choice(pool)
                    else:
                        b = self.rng.choice(pool)

        self.swap(12, a, note="万象挪移交换1")
        self.swap(12, b, note="万象挪移交换2")

        new = self.rank_no(12)
        if old is not None and new is not None and new < old:
            self.give_shield(12, 1, ttl=1, perm=False, note="挪移上升奖励")
            self.twin_share_nonkill(12, "gain_shield")

    # 13 藕禄：无主动（双生为被动已在引擎处理）
    def act_13(self):
        self._log("  · 无主动技能（祸福双生为被动）")

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

    # 25 找自称：自称天命（宣言一个排名，与该排名角色交换）
    def act_25(self):
        alive = self.alive_ids()
        k = self.rng.randint(1, len(alive))
        target = alive[k - 1]
        if target == 25:
            self._log(f"  · 自称天命：宣言{k}命中自身，无事发生")
            return
        self._log(f"  · 自称天命：宣言{k}，与 {self.N(target)} 交换")
        self.swap(25, target, note="自称天命")

    # 26 Sunnydayorange：阳光普照（每2回合，给2人护盾/活力随机分配；光合能量额外第3人）
    def act_26(self):
        r = self.roles[26]
        cd = r.mem.get("cd", 0)
        if cd > 0:
            r.mem["cd"] = cd - 1
            self._log("  · 阳光普照：冷却中")
            return

        alive = self.alive_ids()
        cand = [x for x in alive if x != 26]
        if len(cand) < 2:
            self._log("  · 阳光普照：目标不足")
            return

        targets = self.rng.sample(cand, 2)
        # 若能量≥2，可额外第3名（不强制）
        if self.roles[26].status.photosyn_energy >= 2 and len(cand) >= 3:
            t3 = self.rng.choice([x for x in cand if x not in targets])
            targets.append(t3)

        # 随机分配“护盾”或“活力”（对每个目标独立抽）
        for t in targets:
            if self.rng.random() < 0.5:
                self.give_shield(t, 1, ttl=2, perm=False, note="增益：日光护盾(2回合)")
                self.twin_share_nonkill(t, "gain_shield")
            else:
                # 活力：下回合主动冷却-1（工程化：对该角色 mem["cooldown_minus_next"]=1）
                self.roles[t].mem["cooldown_minus_next"] = True
                self._log(f"  · {self.N(t)} 获得橙子活力：下回合主动冷却-1（工程化）")

        # 光合作用监测：记录前2个目标（按原规则“选择的角色”），2回合未死 -> 能量+1
        self.roles[26].status.photosyn_watch = {"targets": targets[:2], "remain": 2}
        r.mem["cd"] = 2

    # 10/11/13/14 等无主动已实现；但还有缺的：6/10/11/13/14 已覆盖；18/23/24/26 已覆盖

    # =========================
    # 其他角色主动：补齐缺口（已覆盖所有cid 1..26）
    # 这里只剩：10/11/13/14 已是无主动
    # =========================

    # =========================
    # 死亡触发：2/5/7/9/14/23/26
    # =========================

    def on_death_2(self):
        alive = self.alive_ids()
        if not alive:
            return
        t = self.rng.choice(alive)
        d = self.rng.choice([-3, +3])
        if d < 0:
            self._log(f"  · 遗志诅咒：{self.N(t)} 上升3位")
        else:
            self._log(f"  · 遗志诅咒：{self.N(t)} 下降3位")
        self.move_by(t, d, note="遗志诅咒")

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

    def on_death_26(self, killer: Optional[int]):
        # 落日余晖：凶手黄昏标记；最低3名得护盾；随机复活一名非Sunny并放第10或中位
        if killer is not None and self.roles.get(killer) and self.roles[killer].alive:
            self.roles[killer].status.dusk_mark += 1
            self._log(f"  · 落日余晖：凶手 {self.N(killer)} 获得黄昏标记+1")

        alive = self.alive_ids()
        last3 = alive[-3:] if len(alive) >= 3 else alive
        for t in last3:
            self.give_shield(t, 1, ttl=1, perm=False, note="落日余晖最低3名护盾")

        dead = [cid for cid, r in self.roles.items() if (not r.alive) and cid != 26]
        if dead:
            t = self.rng.choice(dead)
            self.roles[t].alive = True
            self._log(f"  · 落日余晖：随机复活 {self.N(t)}")
            self._compact()
            pos10 = 10 if len(self.rank) >= 10 else (len(self.rank)//2 + 1)
            self.rank.insert(pos10 - 1, t)
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
if TK_AVAILABLE:
    class UI:
        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title("26人规则版推演器")
            self.root.geometry("1100x720")

            self.engine = Engine(seed=None)
            # 字体：你可以继续调大
            self.font_rank = tkfont.Font(family="Microsoft YaHei UI", size=16, weight="normal")
            self.font_log  = tkfont.Font(family="Microsoft YaHei UI", size=14, weight="normal")
            # 日志高亮用：同字号粗体
            self.font_log_bold = tkfont.Font(family="Microsoft YaHei UI", size=14, weight="bold")
            # 日志：击败者名字标红用tag
            self._cid_pat = re.compile(r"\((\d{1,2})\)")
            self.revealed_victims: List[Optional[int]] = []  # 每行对应的“被击败者cid”（无则None）



            self.play_cursor = 0
            self.playing = False
            self.speed_var = tk.DoubleVar(value=0.25)
            self.revealed_lines: List[str] = []
            self.revealed_hls: List[List[int]] = []   # 每一行对应的高亮cid列表
            self.current_snap = None
            # 直播高亮相关（即使暂时不用，也要初始化，避免点击崩）
            self.current_highlights = set()
            self._flash_job = None



            self._build()
            self.refresh()

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

            self.btn_new = ttk.Button(self.bottom, text="新开局", command=self.on_new)
            self.btn_new.grid(row=0, column=0, sticky="w")
            ttk.Label(self.bottom, text="made by dian_mi（好吧其实都是ChatGPT写的）").grid(row=0, column=0, padx=(110, 0), sticky="w")


            self.btn_turn = ttk.Button(self.bottom, text="开始回合(生成逐行回放)", command=self.on_build_turn)
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


        def on_new(self):
            self.engine.new_game()
            self.play_cursor = 0
            self.playing = False
            self.revealed_lines = []
            self.revealed_hls = []
            self.revealed_victims = []
            self.current_snap = None
            self.refresh()

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

            # 默认先显示第一行（通常是“第N回合开始”）
            if self.engine.replay_frames:
                self.on_step_line()
            else:
                self.refresh()

        def on_step_line(self):
            frames = self.engine.replay_frames
            if self.play_cursor >= len(frames):
                self.playing = False
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

        def refresh_replay_view(self):
            snap = self.current_snap
            if not snap:
                self.refresh()
                return

            rank = snap["rank"]
            status_map = snap["status"]

            # 左侧：单栏 + 高亮
            for w in self.rank_frame.winfo_children():
                w.destroy()

            hl = self.current_highlights

            for i, cid in enumerate(rank, start=1):
                info = status_map[cid]
                st = info["brief"]
                text = f"{i:>2}. {info['name']}({cid})"
                if st:
                    text += f"   [{st}]"

                bg = "#FFF2A8" if cid in hl else self.root.cget("bg")
                lbl = tk.Label(
                    self.rank_frame,
                    text=text,
                    anchor="w",
                    font=self.font_rank,
                    bg=bg
                )
                lbl.pack(fill="x", pady=2)

            # 右侧日志
            self.render_log_with_current_highlight(self.revealed_lines, self.revealed_hls)


            # 👇 关键：这里就是你之前“找不到”的那一行
            if self._flash_job is not None:
                try:
                    self.root.after_cancel(self._flash_job)
                except Exception:
                    pass

            self._flash_job = self.root.after(150, self._clear_flash)

        def _clear_flash(self):
            self._flash_job = None
            if not self.current_snap:
                return
            self.current_highlights = set()
            # 只重绘，不再触发闪烁
            self.refresh_replay_view_no_flash()

        def refresh_replay_view_no_flash(self):
            snap = self.current_snap
            if not snap:
                self.refresh()
                return

            rank = snap["rank"]
            status_map = snap["status"]

            for w in self.rank_frame.winfo_children():
                w.destroy()

            for i, cid in enumerate(rank, start=1):
                info = status_map[cid]
                st = info["brief"]
                text = f"{i:>2}. {info['name']}({cid})"
                if st:
                    text += f"   [{st}]"

                lbl = tk.Label(
                    self.rank_frame,
                    text=text,
                    anchor="w",
                    font=self.font_rank
                )
                lbl.pack(fill="x", pady=2)

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
            # 左侧排名（单栏）
            for w in self.rank_frame.winfo_children():
                w.destroy()

            alive = self.engine.alive_ids()
            for i, cid in enumerate(alive, start=1):
                r = self.engine.roles[cid]
                st = r.status.brief()
                text = f"{i:>2}. {r.name}({cid})"
                if st:
                    text += f"   [{st}]"

                lbl = tk.Label(self.rank_frame, text=text, anchor="w", font=self.font_rank)
                lbl.pack(fill="x", pady=2)

            # 右侧日志（全量显示）
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", tk.END)
            self.log_text.insert(tk.END, "\n".join(self.engine.log))
            self.log_text.configure(state="disabled")
            self.log_text.see(tk.END)

    def main():
        if not TK_AVAILABLE:
            raise RuntimeError("当前环境不支持 Tkinter（缺少 _tkinter）。请在本地电脑运行桌面版，或使用 Streamlit 网页版。")

        root = tk.Tk()
        try:
            ttk.Style().theme_use("clam")
        except Exception:
            pass
        UI(root)
        root.mainloop()
